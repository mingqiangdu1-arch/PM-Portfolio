from __future__ import annotations
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
import hashlib
import json
import re
import uuid
from typing import Any, Callable

from app.domain.task_state import TaskStatus, transition

RETENTION_CLASS = "ai_runtime"
EXPIRES_AT = None
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

def _event_result_status(status: str) -> str:
    if status == "failed": return "failed"
    if status in {"blocked", "quality_blocked", "stale_target"}: return "blocked"
    if status == "cancelled": return "cancelled"
    if status == "expired": return "expired"
    if status == "partial_result": return "partial"
    return "success"

def _is_duplicate_key(exc: Exception) -> bool:
    return bool(getattr(exc, "args", ())) and exc.args[0] == 1062

def _json_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value

def _content_hash(value: Any) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_public_id: str
    user_id: str
    project_id: str
    project_version_id: str
    target_object_id: str
    target_object_version_id: str
    target_snapshot_hash: str
    command_id: str
    trace_id: str
    status: str = "queued"
    failure_code: str | None = None
    result_ref: str | None = None
    module: str = "product_design"
    task_type: str = "requirement.clarify"
    target_object_type: str = "requirement"
    db_id: int | None = None

class IdempotencyConflict(ValueError): pass

@dataclass
class InMemoryTaskRepository:
    tasks: dict[str, TaskRecord] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)
    contexts: list[dict[str, Any]] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    outbox: list[dict[str, Any]] = field(default_factory=list)
    bundle: dict[str, Any] | None = None
    def create_task(self, task: TaskRecord) -> TaskRecord:
        previous = self.tasks.get(task.task_public_id)
        if previous:
            keys = ("user_id", "project_id", "project_version_id", "target_object_id", "target_object_version_id", "target_snapshot_hash", "command_id")
            if any(getattr(previous, key) != getattr(task, key) for key in keys): raise IdempotencyConflict("task_public_id replay conflicts with immutable task facts")
            return previous
        self.tasks[task.task_public_id] = task
        return task
    def get_task(self, task_public_id: str) -> TaskRecord | None: return self.tasks.get(task_public_id)
    def update_status(self, task_public_id: str, status: str, *, failure_code: str | None = None) -> None:
        task = self.tasks[task_public_id]
        transition(TaskStatus(task.status), TaskStatus(status))
        self.tasks[task_public_id] = replace(task, status=status, failure_code=failure_code)
    def record_context(self, row: dict[str, Any]) -> None: self.contexts.append(dict(row))
    def record_call(self, row: dict[str, Any]) -> int: self.calls.append(dict(row)); return len(self.calls)
    def record_result(self, row: dict[str, Any]) -> int:
        value = dict(row)
        value.setdefault("ai_result_id", len(self.results) + 1)
        self.results.append(value)
        return value["ai_result_id"]
    def list_result_refs(self, task_public_id: str) -> list[dict[str, Any]]:
        return [{key: str(row[key]) if key in {"ai_result_id", "ai_call_id"} else row[key] for key in ("ai_result_id", "ai_call_id", "result_no", "status", "target_snapshot_hash", "content_ref", "content_fingerprint")}
                for row in self.results if row.get("task_public_id") == task_public_id]
    def record_outbox(self, row: dict[str, Any]) -> None: self.outbox.append(dict(row))
    def record_task_event(self, task: TaskRecord, *, event_name: str, status: str, failure_code: str | None = None, call_id: int | None = None, result_id: int | None = None, payload: dict[str, Any] | None = None) -> None:
        body = dict(payload or {})
        body.setdefault("task_status", status)
        result_status = _event_result_status(status)
        if result_status == "failed" and not failure_code:
            failure_code = "AI_RUNTIME_FAILED"
        event = {"schema_version": "0.1.3", "event_id": str(uuid.uuid4()), "event_name": event_name, "occurred_at": datetime.now(UTC).isoformat(), "module": "ai", "result_status": result_status, "source_type": "worker", "privacy_class": "internal_id", "user_id": task.user_id, "project_id": task.project_id, "project_version_id": task.project_version_id, "ai_task_id": str(task.db_id) if task.db_id is not None else None, "ai_call_id": str(call_id) if call_id is not None else None, "ai_result_id": str(result_id) if result_id is not None else None, "failure_code": failure_code, "trace_id": task.trace_id, "command_id": task.command_id, "payload_json": body}
        self.outbox.append(event)
    def mark_status_with_event(self, task_public_id: str, status: str, *, failure_code: str | None = None, event_name: str | None = None) -> None:
        task = self.tasks[task_public_id]
        transition(TaskStatus(task.status), TaskStatus(status))
        self.tasks[task_public_id] = replace(task, status=status, failure_code=failure_code)
        self.record_task_event(self.tasks[task_public_id], event_name=event_name or f"ai.task.{status}", status=status, failure_code=failure_code)
    def resolve_bundle(self, cursor: Any | None = None, **_: Any) -> dict[str, Any]:
        if self.bundle is None:
            raise RuntimeError("FORMAL_MOCK bundle missing from unit-test double")
        return dict(self.bundle)
    def create_call(self, task: TaskRecord, bundle: dict[str, Any], *, capability_fingerprint: str) -> int:
        return self.record_call({"task_public_id": task.task_public_id, "bundle": dict(bundle), "capability_fingerprint": capability_fingerprint, "status": "started"})
    def persist_failure(self, task: TaskRecord, call_id: int, execution: Any, *, status: str = "quality_blocked", failure_code: str = "RESULT_QUALITY_BLOCKED", call_succeeded: bool | None = None) -> None:
        self.update_status(task.task_public_id, status, failure_code=failure_code)
        succeeded = status == "quality_blocked" if call_succeeded is None else call_succeeded
        self.calls[call_id - 1]["status"] = "succeeded" if succeeded else "failed"
        self.calls[call_id - 1]["failure_code"] = None if succeeded else failure_code
        self.record_task_event(task, event_name=f"ai.task.{status}", status=status, failure_code=failure_code, call_id=call_id)
    def persist_success(self, task: TaskRecord, call_id: int, context: Any, execution: Any, key: str, fingerprint: str) -> None:
        self.update_status(task.task_public_id, "ready")
        self.calls[call_id - 1]["status"] = "succeeded"
        provider_response = getattr(execution, "provider_response", None)
        if provider_response:
            self.calls[call_id - 1]["provider_response"] = dict(provider_response)
        self.contexts.extend(dict(item) for item in execution.context_snapshot["sources"])
        self.record_result({"task_public_id": task.task_public_id, "ai_call_id": call_id, "result_no": 1, "status": "ready", "target_snapshot_hash": task.target_snapshot_hash, "content_ref": key, "content_fingerprint": fingerprint})
        self.tasks[task.task_public_id] = replace(self.tasks[task.task_public_id], result_ref=key)
        self.record_task_event(task, event_name="ai.task.ready", status="ready", call_id=call_id)
        self.record_task_event(task, event_name="ai.result.generated", status="ready", call_id=call_id, result_id=len(self.results), payload={"candidate_only": True, "result_id": str(len(self.results)), "content_fingerprint": fingerprint, "target_snapshot_hash": task.target_snapshot_hash})

class MySQLTaskRepository:
    """Minimal PyMySQL DB-API repository; all writes are one transaction."""
    def __init__(self, connection_factory: Callable[[], Any]): self.connection_factory = connection_factory
    def create_task(self, task: TaskRecord) -> TaskRecord:
        conn = self.connection_factory(); cur = conn.cursor()
        try:
            cur.execute("SELECT id,task_public_id,user_id,project_id,project_version_id,module,task_type,target_object_type,target_object_id,target_object_version_id,target_snapshot_hash,command_id,trace_id,status,failure_code FROM ai_task WHERE task_public_id=%s FOR UPDATE", (task.task_public_id,))
            row = cur.fetchone()
            if row:
                existing = self._row(row)
                conn.rollback()
                keys = ("user_id", "project_id", "project_version_id", "target_object_id", "target_object_version_id", "target_snapshot_hash", "command_id")
                if any(getattr(existing, key) != getattr(task, key) for key in keys): raise IdempotencyConflict("task_public_id replay conflicts with immutable task facts")
                return existing
            now = datetime.now(UTC)
            cur.execute("INSERT INTO ai_task (created_at,updated_at,row_version,retention_class,expires_at,task_public_id,user_id,project_id,project_version_id,module,task_type,target_object_type,target_object_id,target_object_version_id,target_snapshot_hash,status,queued_at,trace_id,command_id) VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (now, now, RETENTION_CLASS, EXPIRES_AT, task.task_public_id, task.user_id, task.project_id, task.project_version_id, task.module, task.task_type, task.target_object_type, task.target_object_id, task.target_object_version_id, task.target_snapshot_hash, task.status, now, task.trace_id, task.command_id))
            task = replace(task, db_id=getattr(cur, "lastrowid", None))
            conn.commit(); return task
        except Exception as exc:
            conn.rollback()
            if _is_duplicate_key(exc):
                cur.execute("SELECT id,task_public_id,user_id,project_id,project_version_id,module,task_type,target_object_type,target_object_id,target_object_version_id,target_snapshot_hash,command_id,trace_id,status,failure_code FROM ai_task WHERE task_public_id=%s", (task.task_public_id,))
                existing_row = cur.fetchone()
                if existing_row is None:
                    raise
                existing = self._row(existing_row)
                keys = ("user_id", "project_id", "project_version_id", "target_object_id", "target_object_version_id", "target_snapshot_hash", "command_id")
                if any(getattr(existing, key) != getattr(task, key) for key in keys):
                    raise IdempotencyConflict("task_public_id replay conflicts with immutable task facts") from exc
                return existing
            raise
        finally: cur.close(); conn.close()

    def resolve_bundle(
        self,
        cursor: Any | None = None,
        *,
        provider_code: str = "formal_mock",
        model_code: str = "requirement-clarifier-v1",
        profile_name: str = "portfolio-p1-formal-mock",
        prompt_name: str = "requirement.clarify.formal_mock",
    ) -> dict[str, Any]:
        own = cursor is None
        conn = self.connection_factory() if own else None
        if own: cursor = conn.cursor()
        cursor.execute(
            "SELECT m.id model_id,m.provider_code,m.model_code,pp.id profile_id,pp.profile_name,"
            "pp.config_version runtime_config_version,sv.id skill_version_id,sv.content_hash skill_content_hash,"
            "sv.rule_text skill_rule_text,"
            "pv.id prompt_version_id,pv.content_hash prompt_content_hash,tv.id template_version_id,"
            "pv.system_prompt,pv.user_template,pv.variables_json prompt_variables_json,"
            "tv.content_hash template_content_hash,tv.content template_content,csv.id context_strategy_version_id,"
            "csv.content_hash context_strategy_content_hash,csv.required_context_json,csv.optional_context_json,"
            "csv.limit_config_json,csv.compression_policy_json "
            "FROM model_catalog m JOIN provider_profile pp ON pp.provider_code=m.provider_code "
            "JOIN skill s ON s.name=%s AND s.status='active' AND s.archived_at IS NULL "
            "JOIN skill_version sv ON sv.skill_id=s.id AND sv.version_no=%s AND sv.is_current=1 AND s.current_version_id=sv.id "
            "JOIN prompt p ON p.skill_version_id=sv.id AND p.name=%s AND p.status='active' AND p.archived_at IS NULL "
            "JOIN prompt_version pv ON pv.prompt_id=p.id AND pv.version_no=%s AND pv.is_current=1 AND p.current_version_id=pv.id "
            "JOIN template t ON t.name=%s AND t.status='active' AND t.archived_at IS NULL "
            "JOIN template_version tv ON tv.template_id=t.id AND tv.version_no=%s AND tv.is_current=1 AND t.current_version_id=tv.id "
            "JOIN context_strategy cs ON cs.name=%s AND cs.task_type=%s AND cs.status='active' AND cs.archived_at IS NULL "
            "JOIN context_strategy_version csv ON csv.context_strategy_id=cs.id AND csv.skill_version_id=sv.id AND csv.version_no=%s AND csv.is_current=1 AND cs.current_version_id=csv.id "
            "WHERE m.provider_code=%s AND m.model_code=%s AND m.status='active' "
            "AND m.archived_at IS NULL AND pp.profile_name=%s AND pp.status='active' AND pp.archived_at IS NULL AND pp.user_id IS NULL",
            ("requirement.clarify", "0.2.0", prompt_name, "0.2.0",
             "requirement.clarify.result.0.2", "0.2.0", "requirement.clarify.raw-input-only",
             "requirement.clarify", "0.2.0", provider_code, model_code,
             profile_name),
        )
        rows = cursor.fetchall()
        if len(rows) != 1:
            if own: cursor.close(); conn.close()
            raise RuntimeError("AI capability bundle missing, duplicate or inactive")
        names = ("model_id", "provider_code", "model_code", "profile_id", "profile_name", "runtime_config_version", "skill_version_id", "skill_content_hash", "skill_rule_text", "prompt_version_id", "prompt_content_hash", "template_version_id", "system_prompt", "user_template", "prompt_variables_json", "template_content_hash", "template_content", "context_strategy_version_id", "context_strategy_content_hash", "required_context_json", "optional_context_json", "limit_config_json", "compression_policy_json")
        row = rows[0] if isinstance(rows[0], dict) else dict(zip(names, rows[0]))
        hashes = [row.get(name) for name in ("skill_content_hash", "prompt_content_hash", "template_content_hash", "context_strategy_content_hash")]
        if any(not isinstance(value, str) or not _HEX64.fullmatch(value) for value in hashes):
            if own: cursor.close(); conn.close()
            raise RuntimeError("AI capability bundle content hash invalid")
        ids = ("model_id", "profile_id", "skill_version_id", "prompt_version_id", "template_version_id", "context_strategy_version_id")
        if any(not isinstance(row.get(name), int) or row[name] <= 0 for name in ids):
            if own: cursor.close(); conn.close()
            raise RuntimeError("AI capability bundle foreign keys incomplete")
        recomputed = (
            _content_hash(row.get("skill_rule_text")),
            _content_hash({"system_prompt":row.get("system_prompt"),"user_template":row.get("user_template"),"variables_json":_json_value(row.get("prompt_variables_json"))}),
            _content_hash(row.get("template_content")),
            _content_hash({"required":_json_value(row.get("required_context_json")),"optional":_json_value(row.get("optional_context_json")),"limits":_json_value(row.get("limit_config_json")),"compression":_json_value(row.get("compression_policy_json"))}),
        )
        if tuple(hashes) != recomputed:
            if own: cursor.close(); conn.close()
            raise RuntimeError("AI capability bundle content hash drift")
        payload = {key: row.get(key) for key in ("provider_code", "model_code", "profile_name", "skill_version_id", "prompt_version_id", "template_version_id", "context_strategy_version_id", "skill_content_hash", "prompt_content_hash", "template_content_hash", "context_strategy_content_hash", "runtime_config_version")}
        row.update({"provider_id": row["provider_code"], "fingerprint": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "content_hashes": tuple(hashes), "runtime_config_version": row.get("runtime_config_version") or "0.2.0"})
        if own: cursor.close(); conn.close()
        return row

    def create_call(self, task: TaskRecord, bundle: dict[str, Any], *, capability_fingerprint: str) -> int:
        conn = self.connection_factory(); cur = conn.cursor(); now = datetime.now(UTC)
        try:
            cur.execute("SELECT COALESCE(MAX(sequence_no),0)+1 AS next_sequence_no FROM ai_call WHERE ai_task_id=%s FOR UPDATE", (task.db_id,))
            sequence_row = cur.fetchone(); sequence = sequence_row["next_sequence_no"] if isinstance(sequence_row, dict) else sequence_row[0]
            cur.execute("INSERT INTO ai_call (created_at,updated_at,row_version,retention_class,expires_at,ai_task_id,sequence_no,provider_profile_id,model_catalog_id,skill_version_id,prompt_version_id,context_strategy_version_id,template_version_id,runtime_config_version,capability_fingerprint,status,started_at,cost_source) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (now, now, 1, RETENTION_CLASS, EXPIRES_AT, task.db_id, sequence, bundle["profile_id"], bundle["model_id"], bundle["skill_version_id"], bundle["prompt_version_id"], bundle["context_strategy_version_id"], bundle["template_version_id"], bundle.get("runtime_config_version") or "0.2.0", capability_fingerprint, "started", now, "unavailable"))
            call_id = cur.lastrowid; conn.commit(); return call_id
        except Exception: conn.rollback(); raise
        finally: cur.close(); conn.close()

    def persist_failure(self, task: TaskRecord, call_id: int, execution: Any, *, status: str = "quality_blocked", failure_code: str = "RESULT_QUALITY_BLOCKED", call_succeeded: bool | None = None) -> None:
        conn = self.connection_factory(); cur = conn.cursor()
        try:
            now = datetime.now(UTC)
            cur.execute("SELECT status FROM ai_task WHERE id=%s FOR UPDATE", (task.db_id,))
            current_row = cur.fetchone(); current = current_row["status"] if isinstance(current_row, dict) else current_row[0]
            transition(TaskStatus(current), TaskStatus(status))
            succeeded = status == "quality_blocked" if call_succeeded is None else call_succeeded
            call_status = "succeeded" if succeeded else "failed"
            call_failure_code = None if call_status == "succeeded" else failure_code
            cur.execute("UPDATE ai_call SET status=%s,failure_code=%s,finished_at=%s,updated_at=%s,row_version=row_version+1 WHERE id=%s", (call_status, call_failure_code, now, now, call_id))
            cur.execute("UPDATE ai_task SET status=%s,failure_code=%s,finished_at=%s,updated_at=%s,row_version=row_version+1 WHERE id=%s", (status, failure_code, now, now, task.db_id))
            self._insert_outbox(cur, task, event_name=f"ai.task.{status}", result_status=("blocked" if status in {"quality_blocked", "stale_target"} else "failed"), failure_code=failure_code, task_status=status, now=now, ai_call_id=call_id)
            conn.commit()
        except Exception: conn.rollback(); raise
        finally: cur.close(); conn.close()

    def persist_success(self, task: TaskRecord, call_id: int, context: Any, execution: Any, key: str, fingerprint: str) -> None:
        conn = self.connection_factory(); cur = conn.cursor(); now = datetime.now(UTC)
        try:
            quality = execution.result.get("quality", {})
            cur.execute("SELECT status FROM ai_task WHERE id=%s FOR UPDATE", (task.db_id,))
            current_row = cur.fetchone(); current = current_row["status"] if isinstance(current_row, dict) else current_row[0]
            transition(TaskStatus(current), TaskStatus.READY)
            provider_response = getattr(execution, "provider_response", None) or {}
            content_summary = (
                f"{provider_response.get('provider')}/{provider_response.get('model')} candidate"
                if provider_response
                else "FORMAL_MOCK candidate"
            )
            cur.execute("INSERT INTO ai_result (created_at,retention_class,expires_at,ai_call_id,result_no,target_snapshot_hash,content_ref,content_summary,content_fingerprint,format_status,required_items_total,required_items_met,traceability_status,safety_status,major_error,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (now, RETENTION_CLASS, EXPIRES_AT, call_id, 1, task.target_snapshot_hash, key, content_summary, fingerprint, quality.get("format_status", "passed"), quality.get("required_items_total", 0), quality.get("required_items_met", 0), quality.get("traceability_status", "passed"), quality.get("safety_status", "passed"), bool(quality.get("major_error", False)), "ready"))
            result_id = cur.lastrowid
            for index, source in enumerate(execution.context_snapshot["sources"], 1):
                source_id = str(source["source_id"])
                if not source_id.isdigit() or int(source_id) <= 0:
                    raise ValueError("P1 source_id is not persistence-compatible")
                source_version_id = source.get("source_version_id")
                if source_version_id is not None and (not str(source_version_id).isdigit() or int(source_version_id) <= 0):
                    raise ValueError("P1 source_version_id is not persistence-compatible")
                cur.execute("INSERT INTO ai_context_usage (created_at,retention_class,expires_at,ai_call_id,sequence_no,source_type,source_id,source_version_id,retrieval_method,candidate_rank,relevance_score,was_injected,exclusion_reason,content_fingerprint,content_summary,token_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (now, RETENTION_CLASS, EXPIRES_AT, call_id, index, source["source_type"], int(source_id), int(source_version_id) if source_version_id is not None else None, "direct", None, None, bool(source["was_injected"]), source.get("exclusion_reason"), source["content_fingerprint"], None, source.get("token_count")))
            usage = provider_response.get("usage", {}) if provider_response else {}
            cur.execute(
                "UPDATE ai_call SET status=%s,provider_request_id=%s,input_tokens=%s,output_tokens=%s,"
                "billed_tokens=%s,estimated_cost=%s,currency_code=%s,cost_source=%s,finished_at=%s,"
                "updated_at=%s,row_version=row_version+1 WHERE id=%s",
                (
                    "succeeded",
                    provider_response.get("provider_request_id"),
                    usage.get("input_tokens"),
                    usage.get("output_tokens"),
                    usage.get("billed_tokens"),
                    usage.get("estimated_cost"),
                    usage.get("currency_code"),
                    usage.get("cost_source", "unavailable"),
                    now,
                    now,
                    call_id,
                ),
            )
            cur.execute("UPDATE ai_task SET status=%s,finished_at=%s,updated_at=%s,row_version=row_version+1 WHERE id=%s", ("ready", now, now, task.db_id))
            self._insert_outbox(cur, task, event_name="ai.task.ready", result_status="success", task_status="ready", now=now, ai_call_id=call_id, ai_result_id=result_id)
            self._insert_outbox(cur, task, event_name="ai.result.generated", result_status="success", now=now, ai_call_id=call_id, ai_result_id=result_id, result_payload={"candidate_only": True, "result_id": str(result_id), "content_fingerprint": fingerprint, "target_snapshot_hash": task.target_snapshot_hash})
            conn.commit()
        except Exception: conn.rollback(); raise
        finally: cur.close(); conn.close()

    @staticmethod
    def _insert_outbox(cur: Any, task: TaskRecord, *, event_name: str, result_status: str, now: datetime, task_status: str | None = None, failure_code: str | None = None, ai_call_id: int | None = None, ai_result_id: int | None = None, result_payload: dict[str, Any] | None = None) -> None:
        if event_name.startswith("ai.task.") and task_status is None:
            raise ValueError("AI task events require task_status")
        if result_status == "failed" and not failure_code:
            raise ValueError("failed events require failure_code")
        payload: dict[str, Any] = dict(result_payload or {})
        if task_status is not None:
            payload["task_status"] = task_status
        envelope: dict[str, Any] = {
            "schema_version": "0.1.3", "event_id": str(uuid.uuid4()), "event_name": event_name,
            "occurred_at": now.isoformat(), "module": "ai", "result_status": result_status,
            "source_type": "worker", "privacy_class": "internal_id", "user_id": task.user_id,
            "project_id": task.project_id, "project_version_id": task.project_version_id,
            "object_type": task.target_object_type, "object_id": task.target_object_id,
            "object_version_id": task.target_object_version_id, "ai_task_id": str(task.db_id) if task.db_id is not None else None,
            "trace_id": task.trace_id, "command_id": task.command_id, "failure_code": failure_code,
            "payload_json": payload,
        }
        if ai_call_id is not None: envelope["ai_call_id"] = str(ai_call_id)
        if ai_result_id is not None: envelope["ai_result_id"] = str(ai_result_id)
        cur.execute(
            "INSERT INTO ai_event_outbox (event_id,aggregate_type,aggregate_id,aggregate_version,event_name,schema_version,payload_json,publish_status,attempt_count,next_attempt_at,published_at,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (envelope["event_id"], "ai_task", task.db_id, 1, event_name, "0.1.3", json.dumps(envelope, ensure_ascii=False, separators=(",", ":")), "pending", 0, None, None, now),
        )

    def get_task(self, task_public_id: str) -> TaskRecord | None:
        conn = self.connection_factory(); cur = conn.cursor()
        try:
            cur.execute("SELECT id,task_public_id,user_id,project_id,project_version_id,module,task_type,target_object_type,target_object_id,target_object_version_id,target_snapshot_hash,command_id,trace_id,status,failure_code FROM ai_task WHERE task_public_id=%s", (task_public_id,))
            row = cur.fetchone()
            if not row:
                return None
            task = self._row(row)
            cur.execute("SELECT ar.content_ref FROM ai_result ar JOIN ai_call ac ON ac.id=ar.ai_call_id WHERE ac.ai_task_id=%s ORDER BY ar.result_no DESC LIMIT 1", (task.db_id,))
            result = cur.fetchone()
            if result:
                task = replace(task, result_ref=(result.get("content_ref") if isinstance(result, dict) else result[0]))
            return task
        finally: cur.close(); conn.close()

    def list_result_refs(self, task_public_id: str) -> list[dict[str, Any]]:
        conn = self.connection_factory(); cur = conn.cursor()
        try:
            cur.execute(
                "SELECT ar.id ai_result_id,ar.ai_call_id,ar.result_no,ar.status,ar.target_snapshot_hash,"
                "ar.content_ref,ar.content_fingerprint FROM ai_result ar "
                "JOIN ai_call ac ON ac.id=ar.ai_call_id JOIN ai_task at ON at.id=ac.ai_task_id "
                "WHERE at.task_public_id=%s ORDER BY ar.result_no,ar.id",
                (task_public_id,),
            )
            rows = cur.fetchall()
            return [{
                "ai_result_id": str(row["ai_result_id"]),
                "ai_call_id": str(row["ai_call_id"]),
                "result_no": row["result_no"],
                "status": row["status"],
                "target_snapshot_hash": row["target_snapshot_hash"],
                "content_ref": row["content_ref"],
                "content_fingerprint": row["content_fingerprint"],
            } for row in rows]
        finally: cur.close(); conn.close()

    @staticmethod
    def _row(row: Any) -> TaskRecord:
        def contract_id(value: Any) -> str | None:
            return None if value is None else str(value)

        if isinstance(row, dict):
            return TaskRecord(
                task_public_id=row["task_public_id"], user_id=contract_id(row["user_id"]), project_id=contract_id(row["project_id"]),
                project_version_id=contract_id(row["project_version_id"]), target_object_id=contract_id(row["target_object_id"]),
                target_object_version_id=contract_id(row["target_object_version_id"]), target_snapshot_hash=row["target_snapshot_hash"],
                command_id=row["command_id"], trace_id=row["trace_id"], status=row["status"],
                failure_code=row.get("failure_code"), module=row.get("module", "product_design"), task_type=row.get("task_type", "requirement.clarify"), target_object_type=row.get("target_object_type", "requirement"), db_id=row.get("id"),
            )
        if len(row) >= 15:
            return TaskRecord(row[1], contract_id(row[2]), contract_id(row[3]), contract_id(row[4]), contract_id(row[8]), contract_id(row[9]), row[10], row[11], row[12], row[13], row[14], module=row[5], task_type=row[6], target_object_type=row[7], db_id=row[0])
        return TaskRecord(*row)
    def update_status(self, task_public_id: str, status: str, *, failure_code: str | None = None) -> None:
        conn = self.connection_factory(); cur = conn.cursor()
        try:
            now = datetime.now(UTC)
            cur.execute("SELECT status FROM ai_task WHERE task_public_id=%s FOR UPDATE", (task_public_id,))
            row = cur.fetchone()
            if not row: raise RuntimeError("AI task fact missing")
            current = row["status"] if isinstance(row, dict) else row[0]
            transition(TaskStatus(current), TaskStatus(status))
            started_at = now if status == "preparing" else None
            cur.execute("UPDATE ai_task SET status=%s,failure_code=%s,started_at=COALESCE(started_at,%s),updated_at=%s,row_version=row_version+1 WHERE task_public_id=%s", (status, failure_code, started_at, now, task_public_id)); conn.commit()
        except Exception: conn.rollback(); raise
        finally: cur.close(); conn.close()

    def mark_status_with_event(self, task_public_id: str, status: str, *, failure_code: str | None = None, event_name: str | None = None) -> None:
        task = self.get_task(task_public_id)
        if task is None:
            raise RuntimeError("AI task fact missing")
        conn = self.connection_factory(); cur = conn.cursor(); now = datetime.now(UTC)
        try:
            cur.execute("SELECT status FROM ai_task WHERE id=%s FOR UPDATE", (task.db_id,))
            current_row = cur.fetchone(); current = current_row["status"] if isinstance(current_row, dict) else current_row[0]
            transition(TaskStatus(current), TaskStatus(status))
            cur.execute("UPDATE ai_task SET status=%s,failure_code=%s,finished_at=%s,updated_at=%s,row_version=row_version+1 WHERE id=%s", (status, failure_code, now, now, task.db_id))
            self._insert_outbox(cur, task, event_name=event_name or f"ai.task.{status}", result_status=_event_result_status(status), task_status=status, failure_code=failure_code, now=now)
            conn.commit()
        except Exception:
            conn.rollback(); raise
        finally:
            cur.close(); conn.close()
