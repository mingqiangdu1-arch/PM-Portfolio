import unittest

from app.main import app
from tests.asgi_client import request


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_liveness_uses_standard_envelope_and_trace_header(self) -> None:
        response = await request(app, "/health/live")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload), {"code", "message", "data", "trace_id"})
        self.assertEqual(payload["code"], "OK")
        self.assertEqual(payload["data"]["status"], "live")
        self.assertEqual(response.headers["x-trace-id"], payload["trace_id"])

    async def test_safe_request_id_is_reused_as_trace_id(self) -> None:
        trace_id = "request-12345678"
        response = await request(app, "/api/v1/health", {"X-Request-ID": trace_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["trace_id"], trace_id)

    async def test_unsafe_request_id_is_replaced(self) -> None:
        response = await request(app, "/health/ready", {"X-Request-ID": "bad header"})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()["trace_id"], "bad header")
        self.assertEqual(len(response.json()["trace_id"]), 32)

    async def test_unknown_path_uses_standard_error_envelope(self) -> None:
        response = await request(app, "/api/v1/not-implemented")
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(set(payload), {"code", "message", "details", "trace_id"})
        self.assertEqual(payload["code"], "NOT_FOUND")

    async def test_health_is_intentionally_public(self) -> None:
        response = await request(app, "/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("www-authenticate", response.headers)
