from __future__ import annotations

import base64
import hashlib
import hmac
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping
from urllib.parse import quote, urlencode, urlsplit

from app.platform.errors import ApiError


@dataclass(frozen=True, slots=True)
class SignedObjectRequest:
    url: str
    method: str
    expires_at: datetime
    required_headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class ObjectFacts:
    object_key: str
    size_bytes: int
    content_type: str
    checksum_sha256: str
    etag: str
    version_id: str | None


@dataclass(frozen=True, slots=True)
class FinalizedObject:
    object_key: str
    storage_version_id: str
    checksum_sha256: str


class S3Signer:
    def __init__(self, *, endpoint: str, bucket: str, region: str, access_key: str, secret_key: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key

    @staticmethod
    def _sign(key: bytes, value: str) -> bytes:
        return hmac.new(key, value.encode(), hashlib.sha256).digest()

    def presign(
        self,
        *,
        method: str,
        object_key: str,
        expires_seconds: int = 900,
        required_headers: dict[str, str] | None = None,
    ) -> SignedObjectRequest:
        now = datetime.now(UTC)
        date = now.strftime("%Y%m%d")
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        host = urlsplit(self.endpoint).netloc
        scope = f"{date}/{self.region}/s3/aws4_request"
        path = f"/{quote(self.bucket)}/{quote(object_key, safe='/')}"
        signed = {key.lower().strip(): value.strip() for key, value in (required_headers or {}).items()}
        signed["host"] = host
        signed_header_names = ";".join(sorted(signed))
        canonical_headers = "".join(f"{key}:{signed[key]}\n" for key in sorted(signed))
        query = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key}/{scope}",
            "X-Amz-Date": timestamp,
            "X-Amz-Expires": str(expires_seconds),
            "X-Amz-SignedHeaders": signed_header_names,
        }
        canonical_query = urlencode(sorted(query.items()), quote_via=quote)
        canonical = "\n".join([method, path, canonical_query, canonical_headers, signed_header_names, "UNSIGNED-PAYLOAD"])
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256",
            timestamp,
            scope,
            hashlib.sha256(canonical.encode()).hexdigest(),
        ])
        date_key = self._sign(("AWS4" + self.secret_key).encode(), date)
        region_key = self._sign(date_key, self.region)
        service_key = self._sign(region_key, "s3")
        signing_key = self._sign(service_key, "aws4_request")
        query["X-Amz-Signature"] = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
        from datetime import timedelta

        return SignedObjectRequest(
            url=f"{self.endpoint}{path}?{urlencode(sorted(query.items()), quote_via=quote)}",
            method=method,
            expires_at=now + timedelta(seconds=expires_seconds),
            required_headers={key: value for key, value in signed.items() if key != "host"},
        )


def checksum_sha256_base64(checksum_hex: str) -> str:
    try:
        return base64.b64encode(bytes.fromhex(checksum_hex)).decode("ascii")
    except ValueError as exc:
        raise ApiError(
            code="CHECKSUM_MISMATCH",
            message="SHA-256 checksum must be a 64-character hexadecimal value",
            http_status=409,
        ) from exc


class S3ObjectStorage:
    """Small S3-compatible transport used only for object finalization.

    Clients upload to a temporary key with an S3-validated checksum. Completion
    conditionally copies that exact object to a server-only final key and then
    persists the final key plus the immutable object-store version/ETag.
    """

    def __init__(self, signer: S3Signer) -> None:
        self.signer = signer

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str | None:
        return next((value for key, value in headers.items() if key.lower() == name.lower()), None)

    def head(self, object_key: str) -> ObjectFacts:
        signed = self.signer.presign(
            method="HEAD",
            object_key=object_key,
            expires_seconds=60,
            required_headers={"x-amz-checksum-mode": "ENABLED"},
        )
        request = urllib.request.Request(
            signed.url,
            method="HEAD",
            headers=signed.required_headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                headers = dict(response.headers.items())
                size = int(self._header(headers, "Content-Length") or "-1")
                content_type = (self._header(headers, "Content-Type") or "").split(";", 1)[0]
                checksum = self._header(headers, "x-amz-checksum-sha256") or ""
                etag = self._header(headers, "ETag") or ""
                version_id = self._header(headers, "x-amz-version-id")
        except (OSError, urllib.error.URLError, ValueError) as exc:
            raise ApiError(
                code="STORAGE_UNAVAILABLE",
                message="Object storage verification failed",
                http_status=503,
            ) from exc
        if not checksum or not etag:
            raise ApiError(
                code="CHECKSUM_MISMATCH",
                message="Object storage did not return a verifiable content checksum",
                http_status=409,
            )
        return ObjectFacts(object_key, size, content_type, checksum, etag, version_id)

    def finalize(
        self,
        *,
        temporary_key: str,
        final_key: str,
        expected_size: int,
        expected_content_type: str,
        expected_checksum_hex: str,
    ) -> FinalizedObject:
        expected_checksum = checksum_sha256_base64(expected_checksum_hex)
        source = self.head(temporary_key)
        if (
            source.size_bytes != expected_size
            or source.content_type != expected_content_type
            or source.checksum_sha256 != expected_checksum
        ):
            raise ApiError(
                code="CHECKSUM_MISMATCH",
                message="Stored object facts do not match upload initialization",
                http_status=409,
            )

        copy_source = quote(
            f"/{self.signer.bucket}/{temporary_key}",
            safe="/",
        )
        if source.version_id:
            copy_source += "?versionId=" + quote(source.version_id, safe="")
        copy_headers = {
            "x-amz-copy-source": copy_source,
            "x-amz-copy-source-if-match": source.etag,
            "x-amz-checksum-algorithm": "SHA256",
        }
        signed_copy = self.signer.presign(
            method="PUT",
            object_key=final_key,
            expires_seconds=60,
            required_headers=copy_headers,
        )
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    signed_copy.url,
                    method="PUT",
                    headers=signed_copy.required_headers,
                ),
                timeout=10,
            ):
                pass
        except (OSError, urllib.error.URLError) as exc:
            raise ApiError(
                code="STORAGE_UNAVAILABLE",
                message="Object storage finalization failed",
                http_status=503,
            ) from exc

        final = self.head(final_key)
        if (
            final.size_bytes != expected_size
            or final.content_type != expected_content_type
            or final.checksum_sha256 != expected_checksum
        ):
            raise ApiError(
                code="CHECKSUM_MISMATCH",
                message="Final object failed immutable checksum verification",
                http_status=409,
            )
        storage_version_id = final.version_id or final.etag.strip('"')
        if not storage_version_id:
            raise ApiError(
                code="STORAGE_UNAVAILABLE",
                message="Object storage did not return an immutable object identifier",
                http_status=503,
            )
        return FinalizedObject(final_key, storage_version_id, expected_checksum_hex)
