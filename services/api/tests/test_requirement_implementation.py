from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, ValidationError

from app.main import app
from app.api.v1.requirements import require_requirement_idempotency_key
from app.modules.requirements.service import DIMENSIONS, RequirementService, _canonical_hash, _empty_content
from app.platform.errors import ApiError
from app.platform.sprint2_contract import SPRINT2_SCHEMAS


class _Result:
    def __init__(self, rows=None, *, rowcount: int = 0, lastrowid: int | None = None):
        self.rows = rows or []
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _ScriptedDB:
    """Small auditable repository fake; it records SQL facts and restores snapshots on rollback."""

    def __init__(self):
        now = datetime.now(UTC).replace(tzinfo=None)
        self.tables = {
            "project_version": [{"id": 7, "project_id": 3, "row_version": 1}],
            "project_member": [{"project_id": 3, "user_id": 10, "role_code": "owner", "row_version": 1, "status": "active"}],
            "requirement": [], "requirement_version": [], "audit": [], "outbox": [], "idempotency": [],
            "ai_result": [], "ai_task": [],
        }
        self.next_requirement = 100
        self.next_version = 200
        self.calls: list[tuple[str, dict]] = []
        self.now = now
        self.fail_on_outbox = False

    @contextmanager
    def transaction(self):
        snapshot = copy.deepcopy(self.tables)
        ids = (self.next_requirement, self.next_version)
        try:
            yield self
        except Exception:
            self.tables = snapshot
            self.next_requirement, self.next_version = ids
            raise

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.calls.append((sql, params.copy()))
        if sql.startswith("SELECT ar.*"):
            result_id = str(params["result_id"])
            result = next((r for r in self.tables["ai_result"] if str(r["id"]) == result_id), None)
            if not result:
                return _Result([])
            task = next((r for r in self.tables["ai_task"] if str(r["id"]) == str(result.get("task_id"))), {})
            return _Result([{**task, **result, "task_public_id": task.get("task_public_id"), "task_target_snapshot_hash": task.get("target_snapshot_hash")}])
        if sql.startswith("INSERT IGNORE INTO idempotency_record"):
            found = next((r for r in self.tables["idempotency"] if (r["user_id"], r["endpoint_key"], r["idempotency_key"]) == (params["user_id"], params["endpoint"], params["key"])), None)
            if found:
                return _Result(rowcount=0)
            self.tables["idempotency"].append({"user_id": params["user_id"], "endpoint_key": params["endpoint"], "idempotency_key": params["key"], "request_hash": params["digest"], "status": "in_progress", "response_ref": None})
            return _Result(rowcount=1)
        if "SELECT request_hash,status,response_ref FROM idempotency_record" in sql:
            row = next((r for r in self.tables["idempotency"] if (r["user_id"], r["endpoint_key"], r["idempotency_key"]) == (params["user_id"], params["endpoint"], params["key"])), None)
            return _Result([row] if row else [])
        if sql.startswith("UPDATE idempotency_record"):
            row = next(r for r in self.tables["idempotency"] if (r["user_id"], r["endpoint_key"], r["idempotency_key"]) == (params["user_id"], params["endpoint"], params["key"]))
            row.update(status="completed", response_ref=params["ref"])
            return _Result(rowcount=1)
        if sql.startswith("SELECT id,project_id,row_version FROM project_version"):
            return _Result([r for r in self.tables["project_version"] if r["id"] == params["id"]])
        if sql.startswith("SELECT id,project_id FROM project_version"):
            return _Result([r for r in self.tables["project_version"] if r["id"] == params["id"]])
        if "SELECT role_code" in sql:
            rows = [r for r in self.tables["project_member"] if r["project_id"] == params["project_id"] and r["user_id"] == params["user_id"] and r["status"] == "active"]
            return _Result(rows)
        if sql.startswith("SELECT * FROM requirement_version WHERE id="):
            target = params.get("id", params.get("vid"))
            return _Result([r for r in self.tables["requirement_version"] if str(r["id"]) == str(target)])
        if sql.startswith("SELECT * FROM requirement_version WHERE requirement_id="):
            rows = [
                r for r in self.tables["requirement_version"]
                if str(r["requirement_id"]) == str(params["requirement_id"]) and r["is_effective"]
            ]
            return _Result(sorted(rows, key=lambda r: r["id"], reverse=True)[:1])
        if sql.startswith("SELECT * FROM requirement WHERE project_version_id="):
            rows = [r for r in self.tables["requirement"] if r["project_version_id"] == params["version_id"]]
            if "status" in params:
                rows = [r for r in rows if r["status"] == params["status"]]
            return _Result(sorted(rows, key=lambda r: (r["updated_at"], r["id"]), reverse=True))
        if sql.startswith("SELECT * FROM requirement WHERE id="):
            target = params.get("id", params.get("rid", params.get("requirement_id")))
            return _Result([r for r in self.tables["requirement"] if str(r["id"]) == str(target)])
        if sql.startswith("SELECT version_no FROM requirement_version"):
            rows = [r for r in self.tables["requirement_version"] if r["requirement_id"] == params["rid"]]
            return _Result(sorted(rows, key=lambda r: r["id"], reverse=True)[:1])
        if sql.startswith("INSERT INTO requirement ("):
            rid = self.next_requirement; self.next_requirement += 1
            self.tables["requirement"].append({"id": rid, "project_version_id": params["version_id"], "title": params["title"], "source_type": "manual", "priority": "normal", "status": "draft", "current_version_id": None, "row_version": 1, "updated_at": params["now"]})
            return _Result(rowcount=1, lastrowid=rid)
        if sql.startswith("INSERT INTO requirement_version"):
            vid = self.next_version; self.next_version += 1
            content = json.loads(params["content"]) if isinstance(params["content"], str) else params["content"]
            self.tables["requirement_version"].append({"id": vid, "requirement_id": params["rid"], "source_version_id": params.get("source"), "version_no": params.get("version_no", "1"), "content_format": params.get("format", "json"), "content_json": content, "content_hash": params.get("hash", params.get("content_hash")), "confirmation_status": "draft", "unresolved_count": params.get("unresolved", 0), "risk_acceptance_json": json.loads(params["risk"]) if params.get("risk") else None, "created_from_ai_result_id": None, "is_effective": 0, "created_at": params["now"]})
            return _Result(rowcount=1, lastrowid=vid)
        if sql.startswith("UPDATE requirement SET current_version_id"):
            row = next(r for r in self.tables["requirement"] if r["id"] == params["rid"])
            row["current_version_id"] = params["vid"]
            return _Result(rowcount=1)
        if sql.startswith("UPDATE requirement SET title="):
            row = next(r for r in self.tables["requirement"] if r["id"] == params["rid"])
            row.update(title=params["title"], current_version_id=params["vid"], row_version=row["row_version"] + 1, updated_at=params["now"])
            return _Result(rowcount=1)
        if sql.startswith("UPDATE requirement_version SET is_effective=0"):
            count = 0
            for row in self.tables["requirement_version"]:
                if row["requirement_id"] == params["rid"] and row["is_effective"] and row["id"] != params["vid"]:
                    row["is_effective"] = 0
                    count += 1
            return _Result(rowcount=count)
        if sql.startswith("UPDATE requirement_version SET confirmation_status='confirmed'"):
            row = next((r for r in self.tables["requirement_version"] if r["id"] == params["vid"] and r["requirement_id"] == params["rid"]), None)
            if not row:
                return _Result(rowcount=0)
            value = params.get("risk", "[]")
            row.update(confirmation_status="confirmed", is_effective=1, risk_acceptance_json=json.loads(value) if isinstance(value, str) else value)
            return _Result(rowcount=1)
        if sql.startswith("UPDATE requirement SET status='effective'"):
            row = next((r for r in self.tables["requirement"] if r["id"] == params["rid"] and r["current_version_id"] == params["vid"] and r["row_version"] == params["expected"]), None)
            if not row:
                return _Result(rowcount=0)
            row.update(status="effective", row_version=row["row_version"] + 1, updated_at=params["now"])
            return _Result(rowcount=1)
        if sql.startswith("INSERT INTO operation_audit_log"):
            self.tables["audit"].append(params.copy()); return _Result(rowcount=1)
        if sql.startswith("INSERT INTO business_event_outbox"):
            if self.fail_on_outbox:
                raise RuntimeError("outbox dependency failed")
            self.tables["outbox"].append(params.copy()); return _Result(rowcount=1)
        raise AssertionError(f"Unhandled SQL: {sql}")


class RequirementImplementationTests(unittest.TestCase):
    def setUp(self):
        self.db = _ScriptedDB()
        self.service = RequirementService()
        self._readonly_patch = patch("app.modules.requirements.service.readonly", self.db.transaction)
        self._readonly_patch.start()
        self.addCleanup(self._readonly_patch.stop)

    def _create_requirement_for_confirmation(self, *, key: str = "confirm-seed") -> tuple[int, int]:
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            created = self.service.create(
                version_id=7,
                user_id=10,
                payload={"title": "confirm", "raw_input": "raw", "source_refs": []},
                key=key,
                trace_id="trace-confirm-seed",
            )
        return int(created["requirement"]["id"]), int(created["current_version"]["id"])

    def test_create_route_is_registered_and_idempotency_dependency_is_422(self):
        paths: set[tuple[str, str, bool]] = set()
        def walk(items):
            for route in items:
                if hasattr(route, "methods"):
                    paths.update((method, route.path, route.include_in_schema) for method in route.methods)
                if getattr(route, "routes", None):
                    walk(route.routes)
                if getattr(route, "original_router", None) is not None:
                    walk(route.original_router.routes)
        walk(app.routes)
        self.assertIn(("GET", "/api/v1/project-versions/{version_id}/requirements", False), paths)
        self.assertIn(("POST", "/api/v1/project-versions/{version_id}/requirements", False), paths)
        self.assertIn(("GET", "/api/v1/requirements/{requirement_id}", False), paths)
        self.assertIn(("PATCH", "/api/v1/requirement-versions/{version_id}", False), paths)
        self.assertIn(("POST", "/api/v1/requirement-versions/{version_id}:confirm", False), paths)
        with self.assertRaises(ApiError) as raised:
            asyncio.run(require_requirement_idempotency_key(None))
        self.assertEqual((raised.exception.code, raised.exception.http_status), ("VALIDATION_ERROR", 422))

    def test_create_route_reads_idempotency_key_from_header(self):
        response_data = {"requirement": {"id": "100"}, "current_version": {"id": "200"}}
        with (
            patch("app.api.v1.requirements.auth_service.authenticate", return_value={"id": 10}),
            patch("app.api.v1.requirements.service.create_requirement", return_value=response_data) as create,
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/v1/project-versions/7/requirements",
                headers={"Authorization": "Bearer test", "Idempotency-Key": "route-key"},
                json={"title": "t", "raw_input": "raw", "source_refs": []},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], response_data)
        self.assertEqual(create.call_args.kwargs["key"], "route-key")

        with (
            patch("app.api.v1.requirements.auth_service.authenticate", return_value={"id": 10}),
            TestClient(app) as client,
        ):
            missing = client.post(
                "/api/v1/project-versions/7/requirements",
                headers={"Authorization": "Bearer test"},
                json={"title": "t", "raw_input": "raw", "source_refs": []},
            )
        self.assertEqual(missing.status_code, 422)
        self.assertEqual(missing.json()["code"], "VALIDATION_ERROR")

    def test_list_route_binds_auth_version_status_and_needs_no_idempotency_key(self):
        response_data = {"items": [{"id": "100"}], "next_cursor": None, "has_more": False}
        with (
            patch("app.api.v1.requirements.auth_service.authenticate", return_value={"id": 10}),
            patch("app.api.v1.requirements.service.list_requirements", return_value=response_data) as list_requirements,
            TestClient(app) as client,
        ):
            response = client.get(
                "/api/v1/project-versions/7/requirements?status=draft",
                headers={"Authorization": "Bearer test"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], response_data)
        self.assertEqual(list_requirements.call_args.kwargs, {"version_id": 7, "user_id": 10, "status": "draft"})

    def test_confirm_route_binds_body_header_auth_and_trace(self):
        response_data = {"effective_version": {"id": "200"}, "gate_result": "passed"}
        with (
            patch("app.api.v1.requirements.auth_service.authenticate", return_value={"id": 10}),
            patch("app.api.v1.requirements.service.confirm", return_value=response_data) as confirm,
            TestClient(app) as client,
        ):
            response = client.post(
                "/api/v1/requirement-versions/200:confirm",
                headers={"Authorization": "Bearer test", "Idempotency-Key": "confirm-route-key"},
                json={"expected_version": 1, "risk_acceptances": []},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], response_data)
        self.assertEqual(confirm.call_args.kwargs["version_id"], 200)
        self.assertEqual(confirm.call_args.kwargs["user_id"], 10)
        self.assertEqual(confirm.call_args.kwargs["key"], "confirm-route-key")
        self.assertEqual(confirm.call_args.kwargs["payload"], {"expected_version": 1, "risk_acceptances": []})

    def test_get_route_binds_public_requirement_id(self):
        response_data = {
            "requirement": {"id": "100"},
            "current_version": {"id": "200"},
            "effective_version": None,
            "permissions": {"roles": ["owner"]},
        }
        with (
            patch("app.api.v1.requirements.auth_service.authenticate", return_value={"id": 10}),
            patch("app.api.v1.requirements.service.get_requirement", return_value=response_data) as get,
            TestClient(app) as client,
        ):
            response = client.get(
                "/api/v1/requirements/100",
                headers={"Authorization": "Bearer test"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], response_data)
        self.assertEqual(get.call_args.kwargs, {"requirement_id": 100, "user_id": 10})

    def test_create_returned_requirement_id_reads_current_and_effective_baseline(self):
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            created = self.service.create(
                version_id=7,
                user_id=10,
                payload={"title": "baseline", "raw_input": "raw", "source_refs": []},
                key="get-seed",
                trace_id="trace-get",
            )
        requirement_id = int(created["requirement"]["id"])
        current = self.db.tables["requirement_version"][0]
        current["is_effective"] = 1
        current["content_json"]["baseline"]["assumptions"] = ["confirmed baseline"]
        self.db.calls.clear()

        with patch("app.modules.requirements.service.readonly", self.db.transaction):
            result = self.service.get_requirement(requirement_id=requirement_id, user_id=10)

        requirement_lookups = [
            params for sql, params in self.db.calls
            if sql.startswith("SELECT * FROM requirement WHERE id=:requirement_id")
        ]
        self.assertEqual(requirement_lookups, [{"requirement_id": requirement_id}])
        self.assertEqual(result["requirement"]["id"], str(requirement_id))
        self.assertEqual(result["current_version"]["id"], created["current_version"]["id"])
        self.assertEqual(result["effective_version"]["id"], created["current_version"]["id"])
        self.assertEqual(result["requirement"]["effective_version_id"], created["current_version"]["id"])
        self.assertEqual(
            result["current_version"]["content_json"]["baseline"]["assumptions"],
            ["confirmed baseline"],
        )

    def test_get_requirement_hides_non_member_and_missing_resource(self):
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            created = self.service.create(
                version_id=7,
                user_id=10,
                payload={"title": "private", "raw_input": "raw", "source_refs": []},
                key="get-private",
                trace_id="trace-private",
            )
        requirement_id = int(created["requirement"]["id"])
        with patch("app.modules.requirements.service.readonly", self.db.transaction):
            with self.assertRaises(ApiError) as non_member:
                self.service.get_requirement(requirement_id=requirement_id, user_id=99)
            with self.assertRaises(ApiError) as missing:
                self.service.get_requirement(requirement_id=999999, user_id=10)
        self.assertEqual((non_member.exception.code, non_member.exception.http_status), ("RESOURCE_NOT_FOUND", 404))
        self.assertEqual((missing.exception.code, missing.exception.http_status), ("RESOURCE_NOT_FOUND", 404))

    def test_list_requirements_is_scoped_ordered_summarized_and_read_only(self):
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            first = self.service.create(
                version_id=7,
                user_id=10,
                payload={"title": "older", "raw_input": "raw", "source_refs": []},
                key="list-first",
                trace_id="trace-list-first",
            )
            second = self.service.create(
                version_id=7,
                user_id=10,
                payload={"title": "newer", "raw_input": "raw", "source_refs": []},
                key="list-second",
                trace_id="trace-list-second",
            )
        self.db.tables["requirement"][0]["updated_at"] = datetime(2026, 8, 1)
        self.db.tables["requirement"][1]["status"] = "effective"
        self.db.tables["project_version"].append({"id": 8, "project_id": 3, "row_version": 1})
        self.db.tables["requirement"].append(
            {
                "id": 999,
                "project_version_id": 8,
                "title": "other version",
                "source_type": "manual",
                "priority": "normal",
                "status": "draft",
                "current_version_id": None,
                "row_version": 1,
                "updated_at": datetime(2026, 8, 2),
            }
        )
        before = copy.deepcopy(self.db.tables)
        self.db.calls.clear()

        with patch("app.modules.requirements.service.readonly", self.db.transaction):
            result = self.service.list_requirements(version_id=7, user_id=10)
            filtered = self.service.list_requirements(version_id=7, user_id=10, status="effective")

        self.assertEqual([item["id"] for item in result["items"]], [second["requirement"]["id"], first["requirement"]["id"]])
        self.assertEqual(set(result["items"][0]), {"id", "project_version_id", "title", "source_type", "priority", "status", "current_version_id", "effective_version_id", "updated_at", "version"})
        self.assertEqual((result["next_cursor"], result["has_more"]), (None, False))
        self.assertEqual([item["id"] for item in filtered["items"]], [second["requirement"]["id"]])
        list_calls = [(sql, params) for sql, params in self.db.calls if sql.startswith("SELECT * FROM requirement WHERE project_version_id=:version_id")]
        self.assertEqual(len(list_calls), 2)
        self.assertIn("ORDER BY updated_at DESC, id DESC", list_calls[0][0])
        self.assertEqual(list_calls[1][1], {"version_id": 7, "status": "effective"})
        self.assertEqual(self.db.tables, before)
        self.assertFalse(any(sql.startswith(("INSERT", "UPDATE", "DELETE")) for sql, _ in self.db.calls))

    def test_list_requirements_hides_missing_version_and_non_member(self):
        with patch("app.modules.requirements.service.readonly", self.db.transaction):
            with self.assertRaises(ApiError) as missing:
                self.service.list_requirements(version_id=999999, user_id=10)
            with self.assertRaises(ApiError) as non_member:
                self.service.list_requirements(version_id=7, user_id=99)
        self.assertEqual((missing.exception.code, missing.exception.http_status), ("RESOURCE_NOT_FOUND", 404))
        self.assertEqual((non_member.exception.code, non_member.exception.http_status), ("RESOURCE_NOT_FOUND", 404))

    def test_confirm_success_replaces_effective_version_and_emits_exact_facts(self):
        requirement_id, version_id = self._create_requirement_for_confirmation()
        current = self.db.tables["requirement_version"][0]
        previous = copy.deepcopy(current)
        previous.update(id=version_id - 1, confirmation_status="confirmed", is_effective=1)
        self.db.tables["requirement_version"].insert(0, previous)
        before_audit = len(self.db.tables["audit"])
        before_outbox = len(self.db.tables["outbox"])

        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            result = self.service.confirm(
                version_id=version_id,
                user_id=10,
                payload={"expected_version": 1, "risk_acceptances": []},
                key="confirm-success",
                trace_id="trace-confirm-success",
            )

        requirement = self.db.tables["requirement"][0]
        self.assertEqual(result["gate_result"], "passed")
        self.assertEqual(result["effective_version"]["id"], str(version_id))
        self.assertEqual((result["effective_version"]["confirmation_status"], result["effective_version"]["is_effective"]), ("confirmed", True))
        self.assertEqual((requirement["status"], requirement["current_version_id"], requirement["row_version"]), ("effective", version_id, 2))
        self.assertFalse(previous["is_effective"])
        self.assertEqual(current["risk_acceptance_json"], [])
        self.assertEqual(len(self.db.tables["audit"]), before_audit + 1)
        self.assertEqual(self.db.tables["audit"][-1]["operation"], "requirement.version.confirmed")
        self.assertEqual(len(self.db.tables["outbox"]), before_outbox + 1)
        outbox = self.db.tables["outbox"][-1]
        envelope = json.loads(outbox["payload"])
        self.assertEqual(outbox["aggregate_version"], 2)
        self.assertEqual(envelope["event_name"], "requirement.version.confirmed")
        self.assertNotIn("ingested_at", envelope)
        self.assertEqual(
            envelope["payload_json"],
            {
                "requirement_version_id": str(version_id),
                "requirement_version_no": "1",
                "content_hash": current["content_hash"],
                "confirmation_status": "confirmed",
                "gate_result": "passed",
                "accepted_risk_count": 0,
                "unresolved_count": 0,
            },
        )
        self.assertEqual(
            set(envelope["payload_json"]),
            {"requirement_version_id", "requirement_version_no", "content_hash", "confirmation_status", "gate_result", "accepted_risk_count", "unresolved_count"},
        )

    def test_confirm_same_key_replay_and_fresh_key_noop_do_not_duplicate_side_effects(self):
        _, version_id = self._create_requirement_for_confirmation()
        payload = {"expected_version": 1, "risk_acceptances": []}
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            first = self.service.confirm(version_id=version_id, user_id=10, payload=payload, key="confirm-replay", trace_id="trace-confirm-first")
        counts = (len(self.db.tables["audit"]), len(self.db.tables["outbox"]), self.db.tables["requirement"][0]["row_version"])
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            replay = self.service.confirm(version_id=version_id, user_id=10, payload=payload, key="confirm-replay", trace_id="trace-confirm-replay")
            noop = self.service.confirm(version_id=version_id, user_id=10, payload={"expected_version": 2, "risk_acceptances": []}, key="confirm-fresh", trace_id="trace-confirm-noop")
        self.assertEqual(replay, first)
        self.assertEqual(noop["gate_result"], "passed")
        self.assertEqual((len(self.db.tables["audit"]), len(self.db.tables["outbox"]), self.db.tables["requirement"][0]["row_version"]), counts)
        completed = [row for row in self.db.tables["idempotency"] if row["idempotency_key"] in {"confirm-replay", "confirm-fresh"}]
        self.assertEqual([row["status"] for row in completed], ["completed", "completed"])

        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            with self.assertRaises(ApiError) as conflict:
                self.service.confirm(version_id=version_id, user_id=10, payload={"expected_version": 2, "risk_acceptances": []}, key="confirm-replay", trace_id="trace-confirm-conflict")
        self.assertEqual((conflict.exception.code, conflict.exception.http_status), ("IDEMPOTENCY_CONFLICT", 409))

    def test_confirm_guards_current_version_owner_expected_version_and_existence(self):
        _, version_id = self._create_requirement_for_confirmation()
        payload = {"expected_version": 1, "risk_acceptances": []}
        requirement = self.db.tables["requirement"][0]
        requirement["current_version_id"] = version_id + 1
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            with self.assertRaises(ApiError) as non_current:
                self.service.confirm(version_id=version_id, user_id=10, payload=payload, key="confirm-non-current", trace_id="trace-non-current")
        self.assertEqual((non_current.exception.code, non_current.exception.http_status), ("VERSION_CONFLICT", 409))
        requirement["current_version_id"] = version_id

        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            with self.assertRaises(ApiError) as stale:
                self.service.confirm(version_id=version_id, user_id=10, payload={"expected_version": 2, "risk_acceptances": []}, key="confirm-stale", trace_id="trace-stale")
        self.assertEqual((stale.exception.code, stale.exception.http_status), ("VERSION_CONFLICT", 409))

        self.db.tables["project_member"][0]["role_code"] = "reviewer"
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            with self.assertRaises(ApiError) as forbidden:
                self.service.confirm(version_id=version_id, user_id=10, payload=payload, key="confirm-forbidden", trace_id="trace-forbidden")
        self.assertEqual((forbidden.exception.code, forbidden.exception.http_status), ("FORBIDDEN", 403))
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            with self.assertRaises(ApiError) as missing:
                self.service.confirm(version_id=999999, user_id=10, payload=payload, key="confirm-missing", trace_id="trace-missing")
        self.assertEqual((missing.exception.code, missing.exception.http_status), ("RESOURCE_NOT_FOUND", 404))

    def _link_trusted_ai(self, version_id: int, *, unresolved: list[str], blockers: list[str] | None = None, quality: dict | None = None):
        version = next(row for row in self.db.tables["requirement_version"] if row["id"] == version_id)
        requirement = next(row for row in self.db.tables["requirement"] if row["id"] == version["requirement_id"])
        target_hash = version["content_hash"]
        baseline_dimension = {"confirmed_facts": ["fact"], "source_refs": [], "deferred_items": [], "not_applicable_items": []}
        ai_content = {
            "schema_version": "0.2.0", "task_public_id": "task-confirm", "task_type": "requirement.clarify",
            "target_snapshot_hash": target_hash, "mode": "auto", "round_no": 0, "result_kind": "baseline", "status": "ready",
            "dimensions": {dimension: {"status": "complete", "reasons": ["reviewed"], "missing_items": [], "source_refs": []} for dimension in DIMENSIONS},
            "assessment": None, "questions": [],
            "baseline": {"dimensions": {dimension: dict(baseline_dimension) for dimension in DIMENSIONS}, "assumptions": [], "unresolved_items": unresolved},
            "convergence": {"should_finish": True, "finish_reason": "no_new_high_value_question", "next_round_no": None},
            "quality": quality or {"format_status": "passed", "traceability_status": "passed", "safety_status": "passed", "major_error": False, "blocker_codes": blockers or [], "required_items_total": 8, "required_items_met": 8},
        }
        result_id = 501
        self.db.tables["ai_task"] = [{"id": 601, "task_public_id": "task-confirm", "target_object_id": requirement["id"], "target_object_version_id": version_id, "target_snapshot_hash": target_hash}]
        self.db.tables["ai_result"] = [{"id": result_id, "task_id": 601, "status": "ready", "content_json": ai_content, "content_fingerprint": _canonical_hash(ai_content), "target_snapshot_hash": target_hash, "target_object_id": requirement["id"], "target_object_version_id": version_id}]
        version["created_from_ai_result_id"] = result_id
        self.service.content_reader = lambda _ref: ai_content
        return ai_content

    def test_confirm_passed_with_risk_uses_trusted_ai_and_exact_outbox_facts(self):
        _, version_id = self._create_requirement_for_confirmation()
        version = self.db.tables["requirement_version"][0]
        version["content_json"]["baseline"]["unresolved_items"] = ["one", "two"]
        version["unresolved_count"] = 2
        self._link_trusted_ai(version_id, unresolved=["one", "two"])
        risks = [{"missing_item_code": hashlib.sha256(item.encode()).hexdigest(), "impact": "low", "reason": f"accept {item}"} for item in ["one", "two"]]
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            result = self.service.confirm(version_id=version_id, user_id=10, payload={"expected_version": 1, "risk_acceptances": risks}, key="risk-pass", trace_id="trace-risk")
        self.assertEqual(result["gate_result"], "passed_with_risk")
        envelope = json.loads(self.db.tables["outbox"][-1]["payload"])
        self.assertEqual(
            set(envelope["payload_json"]),
            {"requirement_version_id", "requirement_version_no", "content_hash", "confirmation_status", "gate_result", "accepted_risk_count", "unresolved_count"},
        )
        self.assertEqual(envelope["payload_json"]["accepted_risk_count"], 2)
        self.assertEqual(envelope["payload_json"]["unresolved_count"], 2)
        serialized = json.dumps(envelope)
        self.assertNotIn("reason", serialized)
        self.assertNotIn("one", serialized)
        self.assertNotIn("two", serialized)

    def test_confirm_rejects_blocker_quality_and_invalid_acceptance_shapes(self):
        _, version_id = self._create_requirement_for_confirmation()
        version = self.db.tables["requirement_version"][0]
        version["content_json"]["baseline"]["unresolved_items"] = ["blocker", "other"]
        version["unresolved_count"] = 2
        blocker = hashlib.sha256("blocker".encode()).hexdigest()
        self._link_trusted_ai(version_id, unresolved=["blocker", "other"], blockers=[blocker])
        risks = [{"missing_item_code": blocker, "impact": "low", "reason": "accepted"}, {"missing_item_code": hashlib.sha256("other".encode()).hexdigest(), "impact": "low", "reason": "accepted"}]
        with patch("app.modules.requirements.service.transaction", self.db.transaction), self.assertRaises(ApiError) as raised:
            self.service.confirm(version_id=version_id, user_id=10, payload={"expected_version": 1, "risk_acceptances": risks}, key="blocker", trace_id="trace")
        self.assertEqual(raised.exception.code, "RISK_ACCEPTANCE_INVALID")

        for label, bad_risks in {
            "missing": [],
            "unmatched": [{"missing_item_code": "0" * 64, "impact": "low", "reason": "x"}],
            "duplicate": [{"missing_item_code": blocker, "impact": "low", "reason": "x"}, {"missing_item_code": blocker, "impact": "low", "reason": "y"}],
            "extra": [{"missing_item_code": blocker, "impact": "low", "reason": "x"}, {"missing_item_code": hashlib.sha256("other".encode()).hexdigest(), "impact": "medium", "reason": "y"}],
        }.items():
            with self.subTest(label=label):
                self.db.tables["ai_result"][0]["content_json"]["quality"]["blocker_codes"] = []
                self.db.tables["ai_result"][0]["content_fingerprint"] = _canonical_hash(self.db.tables["ai_result"][0]["content_json"])
                with patch("app.modules.requirements.service.transaction", self.db.transaction), self.assertRaises(ApiError):
                    self.service.confirm(version_id=version_id, user_id=10, payload={"expected_version": 1, "risk_acceptances": bad_risks}, key=f"bad-{label}", trace_id="trace")

    def test_confirm_rejects_no_quality_malformed_and_nfc_or_blank_unresolved(self):
        _, version_id = self._create_requirement_for_confirmation()
        version = self.db.tables["requirement_version"][0]
        version["content_json"]["baseline"]["unresolved_items"] = ["e\u0301", "é"]
        version["unresolved_count"] = 2
        snapshot = copy.deepcopy(self.db.tables)
        with patch("app.modules.requirements.service.transaction", self.db.transaction), self.assertRaises(ApiError):
            self.service.confirm(version_id=version_id, user_id=10, payload={"expected_version": 1, "risk_acceptances": []}, key="nfc", trace_id="trace")
        self.assertEqual(self.db.tables, snapshot)
        version["content_json"]["baseline"]["unresolved_items"] = ["  "]
        version["unresolved_count"] = 1
        with patch("app.modules.requirements.service.transaction", self.db.transaction), self.assertRaises(ApiError):
            self.service.confirm(version_id=version_id, user_id=10, payload={"expected_version": 1, "risk_acceptances": []}, key="blank", trace_id="trace")

        def assert_bad_quality(label: str, mutate):
            _, candidate_id = self._create_requirement_for_confirmation(key=f"quality-{label}")
            candidate = self.db.tables["requirement_version"][-1]
            candidate["content_json"]["baseline"]["unresolved_items"] = ["needs review"]
            candidate["unresolved_count"] = 1
            ai_content = self._link_trusted_ai(candidate_id, unresolved=["needs review"])
            mutate(ai_content)
            self.db.tables["ai_result"][0]["content_fingerprint"] = _canonical_hash(ai_content)
            before = copy.deepcopy(self.db.tables)
            code = hashlib.sha256("needs review".encode()).hexdigest()
            payload = {"expected_version": 1, "risk_acceptances": [{"missing_item_code": code, "impact": "low", "reason": "accept"}]}
            with patch("app.modules.requirements.service.transaction", self.db.transaction):
                with self.assertRaises(ApiError) as raised:
                    self.service.confirm(version_id=candidate_id, user_id=10, payload=payload, key=f"quality-{label}-confirm", trace_id="trace")
            self.assertEqual((raised.exception.code, raised.exception.http_status), ("RISK_ACCEPTANCE_INVALID", 422))
            self.assertEqual(self.db.tables, before)

        assert_bad_quality("missing", lambda content: content.pop("quality"))
        assert_bad_quality("malformed", lambda content: content["quality"].update(blocker_codes=["not-a-digest"]))
        assert_bad_quality("unmapped", lambda content: content["quality"].update(blocker_codes=["f" * 64]))

    def test_confirm_locks_requirement_before_addressed_version(self):
        _, version_id = self._create_requirement_for_confirmation()
        self.db.calls.clear()
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            self.service.confirm(version_id=version_id, user_id=10, payload={"expected_version": 1, "risk_acceptances": []}, key="lock-order", trace_id="trace")
        lock_calls = [sql for sql, _ in self.db.calls if "FOR UPDATE" in sql and ("requirement WHERE id" in sql or "requirement_version WHERE id" in sql)]
        self.assertGreaterEqual(len(lock_calls), 2)
        self.assertIn("requirement WHERE id", lock_calls[0])
        self.assertIn("requirement_version WHERE id", lock_calls[1])

    def test_confirm_rolls_back_business_fact_audit_idempotency_and_outbox(self):
        _, version_id = self._create_requirement_for_confirmation()
        snapshot = copy.deepcopy(self.db.tables)
        self.db.fail_on_outbox = True
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            with self.assertRaises(RuntimeError):
                self.service.confirm(version_id=version_id, user_id=10, payload={"expected_version": 1, "risk_acceptances": []}, key="confirm-rollback", trace_id="trace-confirm-rollback")
        self.assertEqual(self.db.tables, snapshot)

    def test_create_success_writes_all_facts_and_preserves_raw_unicode(self):
        raw = "  Unicode\u00a0需求\n"
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            result = self.service.create(version_id=7, user_id=10, payload={"title": "原样标题", "raw_input": raw, "source_refs": []}, key="create-key", trace_id="trace-1")
        req = self.db.tables["requirement"][0]; ver = self.db.tables["requirement_version"][0]
        self.assertEqual(result["current_version"]["content_json"]["raw_input"], raw)
        self.assertEqual(result["current_version"]["content_json"]["raw_input_ref"]["label"], "原样标题")
        self.assertEqual(ver["content_json"]["raw_input_ref"]["content_hash"], hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(req["current_version_id"], ver["id"])
        self.assertEqual(self.db.tables["outbox"][0]["aggregate_version"], 1)
        self.assertEqual(len(self.db.tables["audit"]), 1)
        envelope = json.loads(self.db.tables["outbox"][0]["payload"])
        self.assertEqual(set(envelope), {"schema_version", "event_id", "event_name", "occurred_at", "producer", "module", "result_status", "source_type", "privacy_class", "user_id", "project_id", "project_version_id", "object_type", "object_id", "object_version_id", "trace_id", "command_id", "payload_json"})
        self.assertNotIn("ingested_at", envelope)

    def test_create_replay_conflict_and_transaction_rollback(self):
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            first = self.service.create(version_id=7, user_id=10, payload={"title": "t", "raw_input": "one", "source_refs": []}, key="same-key", trace_id="t")
            replay = self.service.create(version_id=7, user_id=10, payload={"title": "t", "raw_input": "one", "source_refs": []}, key="same-key", trace_id="t")
            self.assertEqual(first, replay)
            with self.assertRaises(ApiError) as raised:
                self.service.create(version_id=7, user_id=10, payload={"title": "t", "raw_input": "two", "source_refs": []}, key="same-key", trace_id="t")
            self.assertEqual(raised.exception.code, "IDEMPOTENCY_CONFLICT")
            before = copy.deepcopy(self.db.tables)
            self.db.fail_on_outbox = True
            with self.assertRaises(RuntimeError):
                self.service.create(version_id=7, user_id=10, payload={"title": "t", "raw_input": "bad", "source_refs": []}, key="rollback", trace_id="t")
            self.assertEqual(self.db.tables, before)

    def test_create_and_revise_reject_unknown_request_fields(self):
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            with self.assertRaises(ApiError) as raised:
                self.service.create(
                    version_id=7,
                    user_id=10,
                    payload={"title": "t", "raw_input": "raw", "source_refs": [], "contract_escape": True},
                    key="unknown-create",
                    trace_id="t",
                )
            self.assertEqual((raised.exception.code, raised.exception.http_status), ("VALIDATION_ERROR", 422))
            created = self.service.create(
                version_id=7,
                user_id=10,
                payload={"title": "t", "raw_input": "raw", "source_refs": []},
                key="known-create",
                trace_id="t",
            )
            with self.assertRaises(ApiError) as raised:
                self.service.revise(
                    version_id=int(created["current_version"]["id"]),
                    user_id=10,
                    payload={"expected_version": 1, "contract_escape": True},
                    trace_id="t",
                )
            self.assertEqual((raised.exception.code, raised.exception.http_status), ("VALIDATION_ERROR", 422))

    def test_create_schema_rejects_source_ref_extra_or_missing_fields_without_writes(self):
        malformed_refs = [
            {
                "source_type": "manual",
                "source_id": "source-1",
                "source_version_id": None,
                "content_hash": "a" * 64,
            },
            {
                "source_type": "manual",
                "source_id": "source-1",
                "source_version_id": None,
                "content_hash": "a" * 64,
                "label": "source",
                "contract_escape": True,
            },
        ]
        for index, source_ref in enumerate(malformed_refs):
            with self.subTest(index=index):
                before = copy.deepcopy(self.db.tables)
                with patch("app.modules.requirements.service.transaction", self.db.transaction):
                    with self.assertRaises(ApiError) as raised:
                        self.service.create(
                            version_id=7,
                            user_id=10,
                            payload={"title": "t", "raw_input": "raw", "source_refs": [source_ref]},
                            key=f"bad-source-{index}",
                            trace_id="t",
                        )
                self.assertEqual((raised.exception.code, raised.exception.http_status), ("VALIDATION_ERROR", 422))
                self.assertEqual(self.db.tables, before)

    def test_revise_recursively_rejects_nested_contract_violations_and_rolls_back(self):
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            created = self.service.create(
                version_id=7,
                user_id=10,
                payload={"title": "t", "raw_input": "raw", "source_refs": []},
                key="nested-create",
                trace_id="t",
            )
        version_id = int(created["current_version"]["id"])
        valid_content = created["current_version"]["content_json"]
        assessment = {
            "assessment_version": "0.2.0",
            "dimensions": {
                dimension: {"status": "complete", "missing_items": [], "source_refs": []}
                for dimension in DIMENSIONS
            },
            "complexity_band": "low",
            "complexity_reason": "bounded scope",
            "recommended_mode": "auto",
            "missing_dimensions": [],
            "source_refs": [],
            "ai_result_id": "result-1",
        }
        round_data = {
            "round_no": 1,
            "ai_task_id": "task-1",
            "ai_result_id": "result-1",
            "questions": [
                {
                    "question_id": "question-1",
                    "dimension": "goal",
                    "question_text": "What outcome is required?",
                    "reason": "Confirm the goal",
                    "source_refs": [],
                }
            ],
            "answers": [{"question_id": "question-1", "answer": "A confirmed outcome"}],
        }

        invalid_contents: list[tuple[str, dict]] = []

        invalid = copy.deepcopy(valid_content)
        invalid["clarification"]["assessment"] = {**assessment, "contract_escape": True}
        invalid_contents.append(("assessment additional property", invalid))

        invalid = copy.deepcopy(valid_content)
        invalid_assessment = {**assessment, "recommended_mode": "unbounded"}
        invalid["clarification"]["assessment"] = invalid_assessment
        invalid_contents.append(("assessment enum", invalid))

        invalid = copy.deepcopy(valid_content)
        invalid_round = copy.deepcopy(round_data)
        invalid_round["questions"][0]["contract_escape"] = True
        invalid["clarification"]["rounds"] = [invalid_round]
        invalid_contents.append(("question additional property", invalid))

        invalid = copy.deepcopy(valid_content)
        invalid_round = copy.deepcopy(round_data)
        invalid_round["answers"][0]["contract_escape"] = True
        invalid["clarification"]["rounds"] = [invalid_round]
        invalid_contents.append(("answer additional property", invalid))

        invalid = copy.deepcopy(valid_content)
        invalid_round = copy.deepcopy(round_data)
        invalid_round["round_no"] = 6
        invalid["clarification"]["rounds"] = [invalid_round]
        invalid_contents.append(("round maximum", invalid))

        invalid = copy.deepcopy(valid_content)
        invalid_round = copy.deepcopy(round_data)
        invalid_round["questions"] = []
        invalid["clarification"]["rounds"] = [invalid_round]
        invalid_contents.append(("round questions minimum items", invalid))

        invalid = copy.deepcopy(valid_content)
        invalid_round = copy.deepcopy(round_data)
        invalid_round["questions"] = invalid_round["questions"] * 4
        invalid["clarification"]["rounds"] = [invalid_round]
        invalid_contents.append(("round questions maximum items", invalid))

        invalid = copy.deepcopy(valid_content)
        invalid_round = copy.deepcopy(round_data)
        invalid_round["questions"][0]["question_text"] = ""
        invalid["clarification"]["rounds"] = [invalid_round]
        invalid_contents.append(("question minimum length", invalid))

        invalid = copy.deepcopy(valid_content)
        invalid["baseline"]["dimensions"]["goal"]["source_refs"] = [
            {
                "source_type": "manual",
                "source_id": "source-1",
                "source_version_id": None,
                "content_hash": "b" * 64,
            }
        ]
        invalid_contents.append(("nested SourceRef missing property", invalid))

        invalid = copy.deepcopy(valid_content)
        invalid["baseline"]["dimensions"]["goal"]["confirmed_facts"] = "not-an-array"
        invalid_contents.append(("baseline internal type", invalid))

        draft_validator = Draft202012Validator(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$ref": "#/components/schemas/RequirementContent",
                "components": {"schemas": SPRINT2_SCHEMAS},
            }
        )
        draft_validator.validate(valid_content)
        before = copy.deepcopy(self.db.tables)
        for label, invalid_content in invalid_contents:
            with self.subTest(label=label):
                with self.assertRaises(ValidationError):
                    draft_validator.validate(invalid_content)
                with patch("app.modules.requirements.service.transaction", self.db.transaction):
                    with self.assertRaises(ApiError) as raised:
                        self.service.revise(
                            version_id=version_id,
                            user_id=10,
                            payload={"expected_version": 1, "content_json": invalid_content},
                            trace_id="t",
                        )
                self.assertEqual((raised.exception.code, raised.exception.http_status), ("VALIDATION_ERROR", 422))
                self.assertEqual(raised.exception.message, "Request does not match the frozen schema")
                self.assertEqual(self.db.tables, before)

    def test_same_key_on_different_project_version_is_not_replayed(self):
        self.db.tables["project_version"].append({"id": 8, "project_id": 3, "row_version": 1})
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            first = self.service.create(version_id=7, user_id=10, payload={"title": "t", "raw_input": "same", "source_refs": []}, key="cross-version", trace_id="t")
            second = self.service.create(version_id=8, user_id=10, payload={"title": "t", "raw_input": "same", "source_refs": []}, key="cross-version", trace_id="t")
        self.assertNotEqual(first["requirement"]["id"], second["requirement"]["id"])

    def test_owner_only_returns_not_found_for_non_member_and_forbidden_for_reviewer(self):
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            with self.assertRaises(ApiError) as raised:
                self.service.create(version_id=7, user_id=99, payload={"title": "t", "raw_input": "x", "source_refs": []}, key="no-member", trace_id="t")
            self.assertEqual(raised.exception.http_status, 404)
            self.db.tables["project_member"][0]["role_code"] = "reviewer"
            with self.assertRaises(ApiError) as raised:
                self.service.create(version_id=7, user_id=10, payload={"title": "t", "raw_input": "x", "source_refs": []}, key="reviewer", trace_id="t")
            self.assertEqual(raised.exception.http_status, 403)

    def test_revise_creates_new_version_without_overwriting_raw_input(self):
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            created = self.service.create(version_id=7, user_id=10, payload={"title": "old", "raw_input": "原始", "source_refs": []}, key="rev-create", trace_id="t")
            old_id = int(created["current_version"]["id"])
            revised = self.service.revise(version_id=old_id, user_id=10, payload={"expected_version": 1, "title": "new"}, trace_id="t")
        self.assertEqual(revised["source_version_id"], str(old_id))
        self.assertEqual(revised["version_no"], "2")
        self.assertEqual(revised["content_json"]["raw_input"], "原始")
        self.assertEqual(self.db.tables["outbox"][-1]["aggregate_version"], 2)
        self.assertEqual(len(self.db.tables["requirement_version"]), 2)
        self.assertEqual(self.db.tables["requirement_version"][0]["content_json"]["raw_input"], "原始")

    def test_revise_expected_version_and_raw_input_conflicts(self):
        with patch("app.modules.requirements.service.transaction", self.db.transaction):
            created = self.service.create(version_id=7, user_id=10, payload={"title": "old", "raw_input": "原始", "source_refs": []}, key="rev-conflict", trace_id="t")
            old_id = int(created["current_version"]["id"])
            with self.assertRaises(ApiError) as raised:
                self.service.revise(version_id=old_id, user_id=10, payload={"expected_version": 2}, trace_id="t")
            self.assertEqual(raised.exception.code, "VERSION_CONFLICT")
            with self.assertRaises(ApiError) as raised:
                self.service.revise(version_id=old_id, user_id=10, payload={"expected_version": 1, "content_json": {"raw_input": "different"}}, trace_id="t")
            self.assertEqual(raised.exception.code, "VALIDATION_ERROR")
            with self.assertRaises(ApiError) as raised:
                self.service.revise(version_id=old_id, user_id=10, payload={"expected_version": 1, "content_json": {"clarification": {}, "baseline": {}}}, trace_id="t")
            self.assertEqual(raised.exception.code, "VALIDATION_ERROR")
            invalid_extra, _ = _empty_content("原始", requirement_id=100, title="old")
            invalid_extra["contract_escape"] = True
            with self.assertRaises(ApiError) as raised:
                self.service.revise(version_id=old_id, user_id=10, payload={"expected_version": 1, "content_json": invalid_extra}, trace_id="t")
            self.assertEqual(raised.exception.code, "VALIDATION_ERROR")

    def test_set_clarification_mode_persists_new_version_and_resets_confirmation(self):
        with patch("app.modules.requirements.service.transaction", self.db.transaction), patch("app.modules.requirements.service.readonly", self.db.transaction):
            created = self.service.create(version_id=7, user_id=10, payload={"title": "t", "raw_input": "raw", "source_refs": []}, key="mode-seed", trace_id="t")
            version_id = int(created["current_version"]["id"])
            updated = self.service.set_clarification_mode(version_id=version_id, user_id=10, payload={"mode": "deep", "expected_version": 1}, key="mode-command", trace_id="t")
        self.assertEqual(updated["content_json"]["clarification"]["mode"], "deep")
        self.assertFalse(updated["content_json"]["clarification"]["continue_deep_confirmed"])
        self.assertEqual(len(self.db.tables["requirement_version"]), 2)

    def test_deep_round_three_confirmation_persists_true_and_replay_is_read_only(self):
        with patch("app.modules.requirements.service.transaction", self.db.transaction), patch("app.modules.requirements.service.readonly", self.db.transaction):
            created = self.service.create(version_id=7, user_id=10, payload={"title": "t", "raw_input": "raw", "source_refs": []}, key="answers-seed", trace_id="t")
            version_id = int(created["current_version"]["id"])
            version_row = self.db.tables["requirement_version"][0]
            content = version_row["content_json"]
            content["clarification"]["mode"] = "deep"
            content["clarification"]["rounds"] = [
                {
                    "round_no": round_no,
                    "ai_task_id": f"task-{round_no}",
                    "ai_result_id": f"result-{round_no}",
                    "questions": [{"question_id": f"q-{round_no}", "dimension": "goal", "question_text": "What outcome?", "reason": "Clarify goal", "source_refs": []}],
                    "answers": [{"question_id": f"q-{round_no}", "answer": "An outcome"}],
                }
                for round_no in (1, 2, 3)
            ]
            version_row["content_hash"] = _canonical_hash(content)
            payload = {"round_no": 3, "answers": [{"question_id": "q-3", "answer": "Confirmed outcome"}], "finish_now": False, "continue_deep_confirmed": True, "expected_version": 1}
            updated = self.service.submit_clarification_answers(version_id=version_id, user_id=10, payload=payload, key="answers-command", trace_id="t")
            version_count, audit_count, outbox_count = len(self.db.tables["requirement_version"]), len(self.db.tables["audit"]), len(self.db.tables["outbox"])
            replay = self.service.submit_clarification_answers(version_id=version_id, user_id=10, payload=payload, key="answers-command", trace_id="t")
        self.assertTrue(updated["requirement_version"]["content_json"]["clarification"]["continue_deep_confirmed"])
        self.assertEqual(replay["requirement_version"]["id"], updated["requirement_version"]["id"])
        self.assertEqual(len(self.db.tables["requirement_version"]), version_count)
        self.assertEqual(len(self.db.tables["audit"]), audit_count)
        self.assertEqual(len(self.db.tables["outbox"]), outbox_count)

    def test_clarification_idempotency_endpoint_isolated_by_version(self):
        self.db.tables["project_version"].append({"id": 8, "project_id": 3, "row_version": 1})
        with patch("app.modules.requirements.service.transaction", self.db.transaction), patch("app.modules.requirements.service.readonly", self.db.transaction):
            first = self.service.create(version_id=7, user_id=10, payload={"title": "one", "raw_input": "raw", "source_refs": []}, key="iso-seed-1", trace_id="t")
            second = self.service.create(version_id=8, user_id=10, payload={"title": "two", "raw_input": "raw", "source_refs": []}, key="iso-seed-2", trace_id="t")
            mode_one = self.service.set_clarification_mode(version_id=int(first["current_version"]["id"]), user_id=10, payload={"mode": "deep", "expected_version": 1}, key="same-mode-key", trace_id="t")
            mode_two = self.service.set_clarification_mode(version_id=int(second["current_version"]["id"]), user_id=10, payload={"mode": "deep", "expected_version": 1}, key="same-mode-key", trace_id="t")
        self.assertNotEqual(mode_one["id"], mode_two["id"])

    def test_content_shape(self):
        content, digest = _empty_content("raw", requirement_id=42, title="title")
        self.assertEqual(set(content["baseline"]["dimensions"]), set(DIMENSIONS))
        self.assertEqual(content["clarification"]["rounds"], [])
        self.assertEqual(len(digest), 64)
