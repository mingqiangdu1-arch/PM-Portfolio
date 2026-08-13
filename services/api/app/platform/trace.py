from __future__ import annotations

import contextvars
import re
import secrets

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


TRACE_HEADER = "X-Trace-ID"
REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_trace_id", default="unbound"
)


def new_trace_id() -> str:
    return secrets.token_hex(16)


class TraceMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        candidate = headers.get(REQUEST_ID_HEADER.lower().encode("ascii"), b"").decode(
            "ascii", errors="ignore"
        )
        trace_id = candidate if _SAFE_ID.fullmatch(candidate) else new_trace_id()
        token = current_trace_id.set(trace_id)
        scope.setdefault("state", {})["trace_id"] = trace_id

        async def send_with_trace(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers[TRACE_HEADER] = trace_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_trace)
        finally:
            current_trace_id.reset(token)
