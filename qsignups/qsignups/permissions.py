"""QSignups tiered permissions: Slack admin/owner, AOQ (site Q), past Q, or user."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from database import get_engine
from data import aoq_channel_ids, database_schema, user_has_q_history

_LOG = logging.getLogger(__name__)


def resolved_paxminer_regional_schema() -> Optional[str]:
    """The connected region schema. Missing or invalid DATABASE_SCHEMA skips AOQ/Q."""
    try:
        return database_schema()
    except RuntimeError:
        return None


class PermissionLevel(Enum):
    ADMIN = "admin"
    AOQ = "aoq"
    Q = "q"
    USER = "user"


@dataclass
class UserPermission:
    level: PermissionLevel
    aoq_channel_ids: List[str] = field(default_factory=list)


def slack_is_admin_or_owner(user_info_dict: Any) -> bool:
    """True if Slack workspace admin or owner (including primary owner)."""
    u = (user_info_dict or {}).get("user") or {}
    return bool(
        u.get("is_admin") or u.get("is_owner") or u.get("is_primary_owner")
    )


def get_aoq_channels(user_id: str, schema: str) -> List[str]:
    """Slack channel_ids where this user is site_q_user_id. schema is accepted and ignored."""
    del schema
    try:
        with get_engine().connect() as conn:
            return aoq_channel_ids(conn, user_id)
    except Exception:
        _LOG.exception("get_aoq_channels failed user_id=%s", user_id)
        return []


def has_q_history(user_id: str, schema: str) -> bool:
    """True if user appears as primary Q on any beatdown. schema is accepted and ignored."""
    del schema
    try:
        with get_engine().connect() as conn:
            return user_has_q_history(conn, user_id)
    except Exception:
        _LOG.exception("has_q_history failed user_id=%s", user_id)
        return False


def resolve_user_permission(
    user_info_dict: Any,
    user_id: str,
    paxminer_schema: Optional[str],
) -> UserPermission:
    """
    Waterfall: Slack admin/owner -> AOQ -> past Q -> USER.
    Without paxminer_schema, AOQ/Q cannot be detected -> USER (unless admin).
    """
    if slack_is_admin_or_owner(user_info_dict):
        return UserPermission(PermissionLevel.ADMIN, [])

    if not paxminer_schema:
        return UserPermission(PermissionLevel.USER, [])

    aoq = get_aoq_channels(user_id, paxminer_schema)
    if aoq:
        return UserPermission(PermissionLevel.AOQ, aoq)

    if has_q_history(user_id, paxminer_schema):
        return UserPermission(PermissionLevel.Q, [])

    return UserPermission(PermissionLevel.USER, [])


def can_manage_ao(permission: UserPermission, ao_channel_id: Optional[str]) -> bool:
    if permission.level == PermissionLevel.ADMIN:
        return True
    if permission.level == PermissionLevel.AOQ and ao_channel_id:
        return ao_channel_id in permission.aoq_channel_ids
    return False


def can_manage_events_for_ao(permission: UserPermission, ao_channel_id: Optional[str]) -> bool:
    return can_manage_ao(permission, ao_channel_id)


def can_edit_any_q_slot(permission: UserPermission) -> bool:
    return permission.level in (
        PermissionLevel.ADMIN,
        PermissionLevel.AOQ,
        PermissionLevel.Q,
    )


def can_open_manage_region_calendar(permission: UserPermission) -> bool:
    return permission.level in (PermissionLevel.ADMIN, PermissionLevel.AOQ)
