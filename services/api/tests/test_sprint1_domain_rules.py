import unittest

from app.modules.files.domain import (
    MAX_UPLOAD_SIZE_BYTES,
    relation_uses_immutable_file_version,
    storage_failure_allows_existing_business_crud,
    validate_upload_facts,
)
from app.modules.identity.domain import (
    REFRESH_TOKEN_TTL,
    RefreshDecision,
    RefreshTokenState,
    decide_refresh,
    normalize_email,
    refresh_rotation_creates_successor_row,
    replay_revocation_scope,
)
from app.modules.projects.domain import (
    admin_can_bypass_project_membership,
    derived_version_becomes_working_implicitly,
    is_allowed,
    is_expected_version,
)


class IdentityDomainTests(unittest.TestCase):
    def test_email_is_normalized_and_refresh_lifetime_is_seven_days(self) -> None:
        self.assertEqual(normalize_email("  User@Example.COM "), "user@example.com")
        self.assertEqual(REFRESH_TOKEN_TTL.days, 7)

    def test_refresh_rotation_and_replay_are_distinct(self) -> None:
        valid = RefreshTokenState(True, False, False, False)
        replay = RefreshTokenState(True, False, False, True)
        revoked = RefreshTokenState(True, False, True, False)
        self.assertEqual(decide_refresh(valid), RefreshDecision.ROTATE)
        self.assertEqual(decide_refresh(replay), RefreshDecision.REVOKE_FAMILY)
        self.assertEqual(decide_refresh(revoked), RefreshDecision.REJECT)
        self.assertTrue(refresh_rotation_creates_successor_row())
        self.assertEqual(replay_revocation_scope(), "token_family_id")


class AuthorizationDomainTests(unittest.TestCase):
    def test_owner_only_commands_and_default_deny(self) -> None:
        self.assertTrue(is_allowed(["owner"], "version:set-working"))
        self.assertFalse(is_allowed(["reviewer"], "version:set-working"))
        self.assertFalse(is_allowed(["owner"], "undefined:action"))

    def test_multi_role_is_union_and_admin_has_no_implicit_project_bypass(self) -> None:
        self.assertTrue(is_allowed(["reviewer", "tester"], "file:upload"))
        self.assertFalse(admin_can_bypass_project_membership())

    def test_optimistic_lock_and_derive_do_not_change_working_version_implicitly(self) -> None:
        self.assertTrue(is_expected_version(3, 3))
        self.assertFalse(is_expected_version(4, 3))
        self.assertFalse(derived_version_becomes_working_implicitly())


class FileDomainTests(unittest.TestCase):
    def test_size_checksum_and_failure_boundaries(self) -> None:
        self.assertTrue(validate_upload_facts(size_bytes=1, checksum_sha256="a" * 64))
        self.assertTrue(
            validate_upload_facts(size_bytes=MAX_UPLOAD_SIZE_BYTES, checksum_sha256="0" * 64)
        )
        self.assertFalse(
            validate_upload_facts(
                size_bytes=MAX_UPLOAD_SIZE_BYTES + 1, checksum_sha256="0" * 64
            )
        )
        self.assertFalse(validate_upload_facts(size_bytes=1, checksum_sha256="not-a-hash"))
        self.assertTrue(storage_failure_allows_existing_business_crud())
        self.assertTrue(relation_uses_immutable_file_version())
