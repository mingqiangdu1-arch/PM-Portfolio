from __future__ import annotations

import re


MAX_UPLOAD_SIZE_BYTES = 52_428_800
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def validate_upload_facts(*, size_bytes: int, checksum_sha256: str) -> bool:
    return 1 <= size_bytes <= MAX_UPLOAD_SIZE_BYTES and bool(
        SHA256_PATTERN.fullmatch(checksum_sha256)
    )


def storage_failure_allows_existing_business_crud() -> bool:
    return True


def relation_uses_immutable_file_version() -> bool:
    return True
