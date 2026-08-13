from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable
from hashlib import sha256
import json

class BundleResolutionError(RuntimeError): pass
@dataclass(frozen=True, slots=True)
class FormalMockBundle:
    provider_id: int; model_id: int; profile_id: int; skill_version_id: int; prompt_version_id: int; template_version_id: int; context_strategy_version_id: int; fingerprint: str

KEYS = {"provider_code":"formal_mock", "model_code":"requirement-clarifier-v1", "profile_name":"portfolio-p1-formal-mock", "skill_name":"requirement.clarify", "prompt_name":"requirement.clarify.formal_mock", "template_name":"requirement.clarify.result.0.2", "context_strategy_name":"requirement.clarify.raw-input-only", "version_no":"0.2.0"}

def resolve_formal_mock(rows: Iterable[dict[str, Any]]) -> FormalMockBundle:
    matches = []
    for row in rows:
        if all(row.get(key) == value for key, value in KEYS.items()) and row.get("active") is True and row.get("current") is True:
            matches.append(row)
    if len(matches) != 1: raise BundleResolutionError("FORMAL_MOCK bundle missing, duplicate, inactive or non-current")
    row = matches[0]
    names = ("provider_id", "model_id", "profile_id", "skill_version_id", "prompt_version_id", "template_version_id", "context_strategy_version_id")
    if any(not isinstance(row.get(name), int) or row[name] <= 0 for name in names): raise BundleResolutionError("FORMAL_MOCK bundle foreign keys incomplete")
    hash_keys = ("skill_content_hash", "prompt_content_hash", "template_content_hash", "context_strategy_content_hash")
    hashes = [row.get(key) for key in hash_keys]
    if all(value is None for value in hashes):
        hashes = [row.get("content_hash")]
    if any(not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value) for value in hashes):
        raise BundleResolutionError("FORMAL_MOCK content hash invalid")
    fingerprint = sha256(json.dumps({"keys": {key: row.get(key) for key in sorted(KEYS)}, "ids": {name: row[name] for name in names}, "hashes": hashes}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return FormalMockBundle(*(row[name] for name in names), fingerprint)
