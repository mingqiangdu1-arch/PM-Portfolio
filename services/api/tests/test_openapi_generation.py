from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[3]
OPENAPI = ROOT / "packages" / "contracts" / "openapi" / "openapi.json"


def test_generated_openapi_uses_canonical_utf8_lf_bytes() -> None:
    raw = OPENAPI.read_bytes()
    runtime = app.openapi()
    canonical = (
        json.dumps(runtime, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    assert b"\r\n" not in raw
    assert json.loads(raw) == runtime
    assert raw == canonical
    assert hashlib.sha256(raw).digest() == hashlib.sha256(canonical).digest()
