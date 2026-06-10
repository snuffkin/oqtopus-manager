"""Permission definitions for OQTOPUS Manager.

Verb vocabulary: get / create / update / delete / manage
Format: <resource>.<action> or <resource>.<sub-resource>.<action>
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from oqtopus_manager.auth.base import AuthUser

_OPERATOR: frozenset[str] = frozenset({
    "environment.get",
    "environment.create",
    "environment.delete",
    "environment.config.get",
    "environment.config.update",
    "environment.log.get",
    "environment.service.manage",
    "environment.component.manage",
    "app_settings.get",
})

_ADMIN: frozenset[str] = _OPERATOR | frozenset({
    "app_settings.update",
})

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "operator": _OPERATOR,
    "admin": _ADMIN,
}


def has_permission(user: AuthUser | None, permission: str) -> bool:
    """Return True if the user holds any role that grants the given permission.

    Returns:
        True if the user has the permission, False otherwise.

    """
    if user is None:
        return False
    for role in user.roles:
        role_perms = ROLE_PERMISSIONS.get(role, frozenset())
        if "*" in role_perms or permission in role_perms:
            return True
    return False
