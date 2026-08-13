import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from app.platform.errors import ApiError
from app.platform.security import (
    decode_hs256,
    encode_hs256,
    hash_refresh_token,
    issue_access_token,
)
from app.platform.storage import (
    ObjectFacts,
    S3ObjectStorage,
    S3Signer,
    checksum_sha256_base64,
)
from app.internal_api.health import require_health_service


class JwtSecurityTests(unittest.TestCase):
    def test_access_jwt_contains_session_and_rejects_tampering(self) -> None:
        token, claims = issue_access_token(
            **{
                "user_id": 7,
                "session_id": "session-1",
                "secret": "test-only-" + "secret",
                "ttl_seconds": 900,
            }
        )
        payload = decode_hs256(token, "test-only-secret", audience="business-api")
        self.assertEqual(payload["sub"], "7")
        self.assertEqual(payload["sid"], "session-1")
        self.assertEqual(payload["jti"], claims.jti)
        with self.assertRaises(ApiError):
            decode_hs256(token + "x", "test-only-secret", audience="business-api")

    def test_expired_or_wrong_audience_jwt_is_rejected(self) -> None:
        token = encode_hs256(
            {"aud": "other", "exp": int(time.time()) + 30}, "test-only-secret"
        )
        with self.assertRaises(ApiError):
            decode_hs256(token, "test-only-secret", audience="business-api")

    def test_refresh_token_is_only_represented_by_hash(self) -> None:
        raw = "refresh-secret-value"
        digest = hash_refresh_token(raw)
        self.assertNotEqual(digest, raw)
        self.assertEqual(len(digest), 64)

    def test_ai_api_internal_health_identity_matches_r3(self) -> None:
        now = int(time.time())
        accepted = encode_hs256(
            {
                "iss": "ai-api",
                "sub": "ai-api",
                "aud": "business-api",
                "scope": "health",
                "jti": "jti-test",
                "iat": now,
                "exp": now + 60,
            },
            "internal-test-key",
        )
        wrong_scope = encode_hs256(
            {
                "iss": "ai-api",
                "sub": "ai-api",
                "aud": "business-api",
                "scope": "health:read",
                "jti": "jti-wrong-scope",
                "iat": now,
                "exp": now + 60,
            },
            "internal-test-key",
        )
        settings = SimpleNamespace(
            **{"internal_service_jwt_secret": "internal-" + "test-key"}
        )
        with patch("app.internal_api.health.get_settings", return_value=settings):
            claims = require_health_service(f"Bearer {accepted}")
            self.assertEqual((claims["iss"], claims["sub"], claims["scope"]), ("ai-api", "ai-api", "health"))
            with self.assertRaises(ApiError) as raised:
                require_health_service(f"Bearer {wrong_scope}")
            self.assertEqual(raised.exception.http_status, 403)

    def test_service_jwt_rejects_missing_jti_future_iat_and_excessive_ttl(self) -> None:
        now = int(time.time())
        base = {
            "iss": "ai-api",
            "sub": "ai-api",
            "aud": "business-api",
            "scope": "health",
            "jti": "jti-test",
            "iat": now,
            "exp": now + 60,
        }
        invalid = [
            {key: value for key, value in base.items() if key != "jti"},
            {**base, "iat": now + 120, "exp": now + 180},
            {**base, "exp": now + 301},
            {**base, "exp": now},
        ]
        for claims in invalid:
            with self.subTest(claims=claims):
                token = encode_hs256(claims, "internal-test-key")
                with self.assertRaises(ApiError):
                    decode_hs256(
                        token,
                        "internal-test-key",
                        audience="business-api",
                        require_jti=True,
                        max_ttl_seconds=300,
                        clock_skew_seconds=30,
                    )

    def test_internal_health_rejects_wrong_fixed_subject(self) -> None:
        now = int(time.time())
        settings = SimpleNamespace(internal_service_jwt_secret="internal-" + "test-key")
        for issuer, subject in (("ai-api", "ai-worker"), ("monitoring", "prometheus")):
            token = encode_hs256(
                {
                    "iss": issuer,
                    "sub": subject,
                    "aud": "business-api",
                    "scope": "health",
                    "jti": f"{issuer}-jti",
                    "iat": now,
                    "exp": now + 60,
                },
                "internal-test-key",
            )
            with patch("app.internal_api.health.get_settings", return_value=settings):
                with self.assertRaises(ApiError) as raised:
                    require_health_service(f"Bearer {token}")
                self.assertEqual(raised.exception.http_status, 401)


class S3SigningTests(unittest.TestCase):
    def test_presign_is_method_object_and_header_bound_without_secret_leak(self) -> None:
        signer = S3Signer(
            **{
                "endpoint": "http://minio:9000",
                "bucket": "product-files",
                "region": "us-east-1",
                "access_key": "access-key",
                "secret" + "_key": "do-not-" + "leak",
            }
        )
        signed = signer.presign(
            method="PUT",
            object_key="projects/1/files/2/object",
            required_headers={
                "content-type": "text/plain",
                "x-amz-checksum-sha256": checksum_sha256_base64("a" * 64),
            },
        )
        query = parse_qs(urlsplit(signed.url).query)
        self.assertEqual(signed.method, "PUT")
        self.assertIn("X-Amz-Signature", query)
        self.assertEqual(
            query["X-Amz-SignedHeaders"][0], "content-type;host;x-amz-checksum-sha256"
        )
        self.assertNotIn("do-not-leak", signed.url)
        self.assertEqual(
            signed.required_headers["x-amz-checksum-sha256"],
            checksum_sha256_base64("a" * 64),
        )

    def test_finalize_uses_native_checksum_conditional_copy_and_final_identity(self) -> None:
        signer = S3Signer(
            endpoint="http://minio:9000",
            bucket="product-files",
            region="us-east-1",
            access_key="access-key",
            secret_key="test-" + "secret-key",
        )
        store = S3ObjectStorage(signer)
        checksum_hex = "b" * 64
        checksum_b64 = checksum_sha256_base64(checksum_hex)
        source = ObjectFacts("temporary", 4, "text/plain", checksum_b64, '"source-etag"', "v1")
        final = ObjectFacts("final", 4, "text/plain", checksum_b64, '"final-etag"', "v2")
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with (
            patch.object(store, "head", side_effect=[source, final]),
            patch("app.platform.storage.urllib.request.urlopen", return_value=response) as request,
        ):
            result = store.finalize(
                temporary_key="temporary",
                final_key="final",
                expected_size=4,
                expected_content_type="text/plain",
                expected_checksum_hex=checksum_hex,
            )
        sent = request.call_args.args[0]
        headers = {key.lower(): value for key, value in sent.header_items()}
        self.assertEqual(headers["x-amz-copy-source-if-match"], '"source-etag"')
        self.assertIn("versionId=v1", headers["x-amz-copy-source"])
        self.assertNotIn("x-amz-meta-sha256", headers)
        self.assertEqual((result.object_key, result.storage_version_id), ("final", "v2"))

    def test_finalize_rejects_forged_metadata_without_copying(self) -> None:
        signer = S3Signer(
            endpoint="http://minio:9000",
            bucket="product-files",
            region="us-east-1",
            access_key="access-key",
            secret_key="test-" + "secret-key",
        )
        store = S3ObjectStorage(signer)
        forged = ObjectFacts(
            "temporary",
            4,
            "text/plain",
            checksum_sha256_base64("c" * 64),
            '"etag"',
            None,
        )
        with (
            patch.object(store, "head", return_value=forged),
            patch("app.platform.storage.urllib.request.urlopen") as request,
            self.assertRaises(ApiError) as raised,
        ):
            store.finalize(
                temporary_key="temporary",
                final_key="final",
                expected_size=4,
                expected_content_type="text/plain",
                expected_checksum_hex="d" * 64,
            )
        self.assertEqual(raised.exception.code, "CHECKSUM_MISMATCH")
        request.assert_not_called()
