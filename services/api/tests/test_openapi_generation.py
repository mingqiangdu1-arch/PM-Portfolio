from __future__ import annotations

import hashlib
import json
import subprocess
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
    # Git stores this artifact with LF (see .gitattributes), while a Windows
    # checkout may expose CRLF bytes to Python despite the normalized Git blob.
    # Validate the frozen artifact bytes after the platform line-ending
    # normalization instead of treating checkout mechanics as a contract drift.
    normalized = raw.replace(b"\r\n", b"\n")
    git_blob = subprocess.check_output(
        ["git", "show", "HEAD:packages/contracts/openapi/openapi.json"],
        cwd=ROOT,
    )

    assert b"\r" not in normalized
    assert b"\r\n" not in git_blob
    assert json.loads(normalized) == runtime
    assert json.loads(git_blob) == runtime
    assert normalized == canonical
    assert git_blob == canonical
    assert hashlib.sha256(git_blob).digest() == hashlib.sha256(canonical).digest()
