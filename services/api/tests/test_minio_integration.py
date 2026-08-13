from __future__ import annotations

import hashlib
import os
import unittest
import urllib.error
import urllib.request
import uuid
from urllib.parse import quote, urlsplit, urlunsplit

from app.platform.storage import S3ObjectStorage, S3Signer, checksum_sha256_base64


MINIO_ENDPOINT = os.getenv("MINIO_TEST_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_TEST_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_TEST_SECRET_KEY")


@unittest.skipUnless(
    MINIO_ENDPOINT and MINIO_ACCESS_KEY and MINIO_SECRET_KEY,
    "MinIO integration credentials are not configured",
)
class MinioObjectFinalizationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        assert MINIO_ENDPOINT and MINIO_ACCESS_KEY and MINIO_SECRET_KEY
        cls.bucket = f"sprint1-runtime-{uuid.uuid4().hex[:16]}"
        cls.signer = S3Signer(
            endpoint=MINIO_ENDPOINT,
            bucket=cls.bucket,
            region="us-east-1",
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
        )
        cls.store = S3ObjectStorage(cls.signer)
        cls._request("PUT", "")

    @classmethod
    def tearDownClass(cls) -> None:
        for object_key in ("final/object.txt", "temporary/object.txt"):
            try:
                cls._request("DELETE", object_key)
            except (OSError, urllib.error.HTTPError):
                pass
        try:
            cls._request("DELETE", "")
        except (OSError, urllib.error.HTTPError):
            pass

    @classmethod
    def _request(
        cls,
        method: str,
        object_key: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        signed = cls.signer.presign(
            method=method,
            object_key=object_key,
            expires_seconds=60,
            required_headers=headers,
        )
        request = urllib.request.Request(
            signed.url,
            data=data,
            method=method,
            headers=signed.required_headers,
        )
        with urllib.request.urlopen(request, timeout=10):
            pass

    def test_native_checksum_conditional_copy_and_final_key_write_denial(self) -> None:
        temporary_key = "temporary/object.txt"
        final_key = "final/object.txt"
        payload = b"sprint-1-minio-native-checksum"
        checksum_hex = hashlib.sha256(payload).hexdigest()
        checksum_base64 = checksum_sha256_base64(checksum_hex)
        upload_headers = {
            "content-type": "text/plain",
            "x-amz-checksum-sha256": checksum_base64,
        }
        upload = self.signer.presign(
            method="PUT",
            object_key=temporary_key,
            expires_seconds=60,
            required_headers=upload_headers,
        )
        with urllib.request.urlopen(
            urllib.request.Request(
                upload.url,
                data=payload,
                method="PUT",
                headers=upload.required_headers,
            ),
            timeout=10,
        ):
            pass

        source = self.store.head(temporary_key)
        self.assertEqual(source.checksum_sha256, checksum_base64)
        self.assertTrue(source.etag)

        stale_copy_headers = {
            "x-amz-copy-source": quote(
                f"/{self.bucket}/{temporary_key}", safe="/"
            ),
            "x-amz-copy-source-if-match": '"stale-etag"',
            "x-amz-checksum-algorithm": "SHA256",
        }
        stale_copy = self.signer.presign(
            method="PUT",
            object_key="final/stale.txt",
            expires_seconds=60,
            required_headers=stale_copy_headers,
        )
        with self.assertRaises(urllib.error.HTTPError) as stale_error:
            urllib.request.urlopen(
                urllib.request.Request(
                    stale_copy.url,
                    method="PUT",
                    headers=stale_copy.required_headers,
                ),
                timeout=10,
            )
        self.assertEqual(stale_error.exception.code, 412)

        finalized = self.store.finalize(
            temporary_key=temporary_key,
            final_key=final_key,
            expected_size=len(payload),
            expected_content_type="text/plain",
            expected_checksum_hex=checksum_hex,
        )
        self.assertEqual(finalized.object_key, final_key)
        self.assertTrue(finalized.storage_version_id)
        self.assertEqual(self.store.head(final_key).checksum_sha256, checksum_base64)

        parsed = urlsplit(upload.url)
        tampered_path = f"/{quote(self.bucket)}/{quote(final_key, safe='/')}"
        tampered_url = urlunsplit(
            (parsed.scheme, parsed.netloc, tampered_path, parsed.query, parsed.fragment)
        )
        with self.assertRaises(urllib.error.HTTPError) as tampered_error:
            urllib.request.urlopen(
                urllib.request.Request(
                    tampered_url,
                    data=payload,
                    method="PUT",
                    headers=upload.required_headers,
                ),
                timeout=10,
            )
        self.assertEqual(tampered_error.exception.code, 403)

        anonymous_url = (
            f"{MINIO_ENDPOINT.rstrip('/')}/{quote(self.bucket)}/"
            f"{quote(final_key, safe='/')}"
        )
        with self.assertRaises(urllib.error.HTTPError) as anonymous_error:
            urllib.request.urlopen(
                urllib.request.Request(
                    anonymous_url,
                    data=payload,
                    method="PUT",
                    headers=upload_headers,
                ),
                timeout=10,
            )
        self.assertEqual(anonymous_error.exception.code, 403)
        self.assertEqual(self.store.head(final_key).checksum_sha256, checksum_base64)
