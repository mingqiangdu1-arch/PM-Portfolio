from __future__ import annotations
from hashlib import sha256
import json
import re
from typing import Any

class ObjectWriteError(RuntimeError): pass

def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def build_result_key(*, prefix: str, project_id: str, task_public_id: str, ai_call_id: str, result_no: int, content_fingerprint: str) -> str:
    safe = prefix.strip("/")
    if safe != "ai-results" and not safe.startswith("ai-results/"):
        raise ValueError("result prefix must stay under ai-results/")
    if any(part in {"", ".", ".."} for part in safe.split("/")):
        raise ValueError("result prefix contains an unsafe segment")
    for value in (project_id, task_public_id, ai_call_id):
        if not re.fullmatch(r"[A-Za-z0-9._-]+", value) or value in {".", ".."}:
            raise ValueError("result key contains an unsafe identifier")
    if result_no < 1 or not re.fullmatch(r"[a-f0-9]{64}", content_fingerprint):
        raise ValueError("result key metadata is invalid")
    return f"{safe}/{project_id}/{task_public_id}/{ai_call_id}/{result_no}-{content_fingerprint}.json"

class S3ResultObjectStore:
    """Write-once result objects. The S3 client is injected for unit tests."""
    def __init__(self, client: Any, *, bucket: str, prefix: str = "ai-results/") -> None:
        self.client, self.bucket, self.prefix = client, bucket, prefix
    def put_result(self, *, project_id: str, task_public_id: str, ai_call_id: str, result_no: int, content: dict[str, Any]) -> tuple[str, str]:
        body = canonical_json(content)
        fingerprint = sha256(body).hexdigest()
        key = build_result_key(prefix=self.prefix, project_id=project_id, task_public_id=task_public_id, ai_call_id=ai_call_id, result_no=result_no, content_fingerprint=fingerprint)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            status = getattr(exc, "response", {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status != 404 and not isinstance(exc, FileNotFoundError):
                raise ObjectWriteError("object head failed") from exc
        else:
            self.verify_result(key=key, content_fingerprint=fingerprint)
            return key, fingerprint
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType="application/json", Metadata={"sha256": fingerprint}, IfNoneMatch="*")
            return key, fingerprint
        except Exception as exc:
            # A race is safe only if the existing object is byte-identical.
            try:
                self.verify_result(key=key, content_fingerprint=fingerprint)
                return key, fingerprint
            except Exception: pass
            raise ObjectWriteError("write-once result object failed") from exc
    def verify_result(self, *, key: str, content_fingerprint: str) -> None:
        try:
            head = self.client.head_object(Bucket=self.bucket, Key=key)
            stored = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        except Exception as exc: raise ObjectWriteError("result object missing") from exc
        if head.get("Metadata", {}).get("sha256") != content_fingerprint: raise ObjectWriteError("result object hash mismatch")
        body = stored.read() if hasattr(stored, "read") else stored
        if not isinstance(body, bytes) or sha256(body).hexdigest() != content_fingerprint:
            raise ObjectWriteError("result object body hash mismatch")
