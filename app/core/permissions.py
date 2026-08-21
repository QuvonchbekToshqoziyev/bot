from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable


class Permission(StrEnum):
    MANAGE_SKILLS = "manage_skills"
    READ_MESSAGES = "read_messages"
    SEND_MESSAGES = "send_messages"
    COPY_MESSAGES = "copy_messages"
    DELETE_MESSAGES = "delete_messages"
    EDIT_MESSAGES = "edit_messages"
    PIN_MESSAGES = "pin_messages"
    MANAGE_MEMBERS = "manage_members"
    SCHEDULE_MESSAGES = "schedule_messages"
    MANAGE_BACKUP = "manage_backup"
    READ_LIBRARY = "read_library"


class PermissionDenied(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PermissionContext:
    user_id: int
    chat_id: int
    permissions: frozenset[Permission]


class PermissionService:
    def __init__(self, resolver: Callable[[int, int], frozenset[Permission]] | None = None, admin_user_ids: frozenset[int] = frozenset()) -> None:
        self._resolver = resolver or (lambda user_id, chat_id: frozenset())
        self._admin_user_ids = admin_user_ids

    def context_for(self, user_id: int, chat_id: int) -> PermissionContext:
        permissions = frozenset(Permission) if user_id in self._admin_user_ids else self._resolver(user_id, chat_id)
        return PermissionContext(user_id, chat_id, permissions)

    def require(self, context: PermissionContext, required: frozenset[Permission]) -> None:
        missing = required - context.permissions
        if missing:
            raise PermissionDenied(f"Missing permissions: {', '.join(sorted(permission.value for permission in missing))}")

    def require_user(self, user_id: int, chat_id: int, required: frozenset[Permission]) -> PermissionContext:
        context = self.context_for(user_id, chat_id)
        self.require(context, required)
        return context
