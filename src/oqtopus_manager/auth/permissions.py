"""Permission utilities.

Verb vocabulary: get / create / update / delete / manage
Format: <resource>.<action> or <resource>.<sub-resource>.<action>

Role-to-permission mappings are defined in config.yaml under ``permissions:``,
not in this module.  This module only provides the ``has_permission`` helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import AuthUser


def has_permission(
    user: AuthUser | None,
    permission: str,
    role_permissions: dict[str, frozenset[str]],
) -> bool:
    """Return True if the user holds any role that grants the given permission.

    Returns:
        True if the user has the permission, False otherwise.

    """
    if user is None:
        return False
    for role in user.roles:
        role_perms = role_permissions.get(role, frozenset())
        if "*" in role_perms or permission in role_perms:
            return True
    return False
