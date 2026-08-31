import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from unittest.mock import patch

from app.main import app
from app.modules.sprint1.service import Sprint1Service
from app.platform.errors import ApiError


class Sprint1ImplementationTests(unittest.TestCase):
    def test_compose_provisions_browser_upload_endpoint_and_bucket(self) -> None:
        root = Path(__file__).resolve().parents[3]
        base = (root / "infra" / "compose" / "compose.yaml").read_text(encoding="utf-8")
        local = (root / "infra" / "compose" / "compose.local.yaml").read_text(encoding="utf-8")
        production = (root / "infra" / "compose" / "compose.production.yaml").read_text(encoding="utf-8")
        self.assertIn("minio-init:", base)
        self.assertIn("mc mb --ignore-existing", base)
        self.assertIn("OBJECT_STORAGE_PUBLIC_ENDPOINT: http://localhost:", local)
        self.assertIn("OBJECT_STORAGE_PUBLIC_ENDPOINT:", production)

    def test_frozen_contract_paths_have_runtime_routes(self) -> None:
        def walk(routes: list[object]) -> set[tuple[str, str]]:
            found: set[tuple[str, str]] = set()
            for route in routes:
                path = getattr(route, "path", None)
                methods = getattr(route, "methods", None)
                if path and methods:
                    found.update((method, path) for method in methods)
                nested = getattr(route, "routes", None)
                if nested:
                    found.update(walk(list(nested)))
                original_router = getattr(route, "original_router", None)
                if original_router is not None:
                    found.update(walk(list(original_router.routes)))
            return found

        runtime = walk(list(app.routes))
        required = {
            ("POST", "/api/v1/auth/register"),
            ("POST", "/api/v1/auth/login"),
            ("POST", "/api/v1/auth/refresh"),
            ("POST", "/api/v1/auth/logout"),
            ("GET", "/api/v1/session"),
            ("POST", "/api/v1/projects"),
            ("POST", "/api/v1/projects/{project_id}/versions/{version_id}:set-working"),
            ("POST", "/api/v1/projects/{project_id}/versions:derive"),
            ("GET", "/api/v1/project-versions/{left_id}:compare"),
            ("POST", "/api/v1/files/uploads"),
            ("GET", "/api/v1/projects/{project_id}/files"),
            ("POST", "/api/v1/files/uploads/{upload_id}:complete"),
            ("POST", "/api/v1/file-versions/{version_id}:download"),
            ("GET", "/internal/v1/health"),
        }
        self.assertTrue(required.issubset(runtime), required - runtime)

    def test_refresh_replay_commits_family_revoke_before_error(self) -> None:
        source = inspect.getsource(Sprint1Service.refresh)
        self.assertIn("replay_detected = True", source)
        self.assertGreater(source.index("if replay_detected:"), source.index("with transaction()"))
        self.assertIn("WHERE token_family_id=:family", source)

    def test_critical_commands_write_transactional_audit(self) -> None:
        for method_name in (
            "create_project",
            "set_working",
            "derive_version",
            "project_lifecycle",
            "init_upload",
            "complete_upload",
            "create_relation",
            "archive_file",
        ):
            source = inspect.getsource(getattr(Sprint1Service, method_name))
            self.assertIn("with transaction()", source, method_name)
            self.assertIn("_audit(", source, method_name)

    def test_only_commands_with_frozen_canonical_events_write_outbox(self) -> None:
        for method_name in (
            "create_project",
            "set_working",
            "derive_version",
            "project_lifecycle",
            "init_upload",
            "complete_upload",
        ):
            source = inspect.getsource(getattr(Sprint1Service, method_name))
            self.assertIn("_outbox(", source, method_name)

        # 0.1.3 has no canonical file-relation event. Do not invent one merely
        # to satisfy a structural test; audit and the business fact still share
        # the same transaction.
        self.assertNotIn("_outbox(", inspect.getsource(Sprint1Service.create_relation))

    def test_upload_endpoint_key_never_contains_signed_upload_token(self) -> None:
        for method_name in ("complete_upload", "abort_upload"):
            source = inspect.getsource(getattr(Sprint1Service, method_name))
            self.assertIn("{upload_id}", source, method_name)
            self.assertNotIn("/{upload_id}:complete\"", source, method_name)
            self.assertNotIn("/{upload_id}:abort\"", source, method_name)

    def test_abort_rejects_non_pending_terminal_state(self) -> None:
        source = inspect.getsource(Sprint1Service.abort_upload)
        self.assertIn("already in terminal state", source)
        self.assertIn("_idempotency_lookup", source)

    def test_browser_upload_signatures_use_the_public_endpoint(self) -> None:
        service = Sprint1Service()
        service.settings = SimpleNamespace(
            object_storage_access_key="access-key",
            object_storage_secret_key="secret-key",
            object_storage_endpoint="http://minio:9000",
            object_storage_public_endpoint="https://files.example.test",
            object_storage_bucket="product-files",
            object_storage_region="us-east-1",
        )

        browser_url = service._signer(public=True).presign(method="PUT", object_key="projects/1/file").url
        internal_url = service._signer().presign(method="HEAD", object_key="projects/1/file").url

        self.assertEqual(urlsplit(browser_url).netloc, "files.example.test")
        self.assertEqual(urlsplit(internal_url).netloc, "minio:9000")

    def test_file_input_validation_is_explicit_before_storage(self) -> None:
        source = inspect.getsource(Sprint1Service.init_upload)
        self.assertIn("FILE_TOO_LARGE", source)
        self.assertIn("The selected file is empty", source)
        self.assertLess(source.index("FILE_TOO_LARGE"), source.index("with transaction()"))

    def test_registration_accepts_eight_characters_and_rejects_seven(self) -> None:
        service = Sprint1Service()
        with self.assertRaises(ApiError) as weak:
            service.register(email="user@example.test", password="1234567", display_name="User", trace_id="trace")
        self.assertEqual(weak.exception.code, "WEAK_PASSWORD")
        with patch("app.modules.sprint1.service.transaction", side_effect=RuntimeError("validation passed")):
            with self.assertRaisesRegex(RuntimeError, "validation passed"):
                service.register(email="user@example.test", password="12345678", display_name="User", trace_id="trace")
