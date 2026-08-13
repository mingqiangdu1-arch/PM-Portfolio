from __future__ import annotations

from enum import StrEnum
from typing import Iterable


class ProjectRole(StrEnum):
    OWNER = "owner"
    REVIEWER = "reviewer"
    IMPLEMENTER = "implementer"
    TESTER = "tester"


class ProjectAction(StrEnum):
    VIEW = "project:view"
    CREATE = "project:create"
    UPDATE = "project:update"
    ARCHIVE = "project:archive"
    RESTORE = "project:restore"
    MANAGE_MEMBERS = "project:manage-members"
    VIEW_HISTORY = "version:view-history"
    SET_WORKING_VERSION = "version:set-working"
    DERIVE_VERSION = "version:derive"
    UPLOAD_FILE = "file:upload"
    DOWNLOAD_FILE = "file:download"
    RELATE_FILE = "file:relate"


ROLE_ACTIONS: dict[ProjectRole, frozenset[ProjectAction]] = {
    ProjectRole.OWNER: frozenset(ProjectAction),
    ProjectRole.REVIEWER: frozenset(
        {
            ProjectAction.VIEW,
            ProjectAction.VIEW_HISTORY,
            ProjectAction.UPLOAD_FILE,
            ProjectAction.DOWNLOAD_FILE,
            ProjectAction.RELATE_FILE,
        }
    ),
    ProjectRole.IMPLEMENTER: frozenset(
        {
            ProjectAction.VIEW,
            ProjectAction.VIEW_HISTORY,
            ProjectAction.UPLOAD_FILE,
            ProjectAction.DOWNLOAD_FILE,
            ProjectAction.RELATE_FILE,
        }
    ),
    ProjectRole.TESTER: frozenset(
        {
            ProjectAction.VIEW,
            ProjectAction.VIEW_HISTORY,
            ProjectAction.UPLOAD_FILE,
            ProjectAction.DOWNLOAD_FILE,
            ProjectAction.RELATE_FILE,
        }
    ),
}


def is_allowed(roles: Iterable[str], action: str) -> bool:
    try:
        requested_action = ProjectAction(action)
    except ValueError:
        return False
    allowed: set[ProjectAction] = set()
    for raw_role in roles:
        try:
            role = ProjectRole(raw_role)
        except ValueError:
            continue
        allowed.update(ROLE_ACTIONS[role])
    return requested_action in allowed


def admin_can_bypass_project_membership(*, break_glass_enabled: bool = False) -> bool:
    return break_glass_enabled


def is_expected_version(current_version: int, expected_version: int) -> bool:
    return current_version == expected_version


def derived_version_becomes_working_implicitly() -> bool:
    return False
