from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum


REFRESH_TOKEN_TTL = timedelta(days=7)


class RefreshDecision(StrEnum):
    ROTATE = "rotate"
    REJECT = "reject"
    REVOKE_FAMILY = "revoke_family"


@dataclass(frozen=True, slots=True)
class RefreshTokenState:
    hash_matches: bool
    expired: bool
    revoked: bool
    rotated: bool


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def decide_refresh(state: RefreshTokenState) -> RefreshDecision:
    if not state.hash_matches or state.expired or state.revoked:
        return RefreshDecision.REJECT
    if state.rotated:
        return RefreshDecision.REVOKE_FAMILY
    return RefreshDecision.ROTATE


def refresh_rotation_creates_successor_row() -> bool:
    return True


def replay_revocation_scope() -> str:
    return "token_family_id"
