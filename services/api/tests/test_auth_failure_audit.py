from __future__ import annotations

import unittest
from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import patch

from app.modules.sprint1.service import _record_auth_failure


class AuthenticationFailureAuditTests(unittest.TestCase):
    def test_login_failure_uses_independent_audit_transaction_without_pii(self) -> None:
        connection = object()

        @contextmanager
        def independent_transaction() -> Iterator[object]:
            yield connection

        with (
            patch(
                "app.modules.sprint1.service.transaction",
                side_effect=independent_transaction,
            ) as transaction,
            patch("app.modules.sprint1.service._audit") as audit,
            patch("app.modules.sprint1.service._identity_event") as identity_event,
        ):
            _record_auth_failure(
                operation="auth.login",
                event_name="identity.session.login_failed",
                failure_code="INVALID_CREDENTIALS",
                trace_id="trace-auth-failure",
            )

        transaction.assert_called_once_with()
        audit.assert_called_once()
        values: dict[str, Any] = audit.call_args.kwargs
        self.assertIsNone(values["actor_user_id"])
        self.assertEqual(values["object_type"], "auth_attempt")
        self.assertEqual(values["result_status"], "failed")
        self.assertEqual(values["failure_code"], "INVALID_CREDENTIALS")
        self.assertEqual(values["metadata"], {"reason_class": "credentials_rejected"})
        serialized = repr(values).casefold()
        for forbidden in ("email", "password", "user_agent", "cookie", "token"):
            self.assertNotIn(forbidden, serialized)

        identity_event.assert_called_once()
        event_values = identity_event.call_args.kwargs
        self.assertEqual(event_values["result_status"], "failed")
        self.assertEqual(event_values["failure_code"], "INVALID_CREDENTIALS")
