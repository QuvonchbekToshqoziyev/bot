from __future__ import annotations

from typing import Any, Protocol

from app.core.permissions import Permission, PermissionContext, PermissionService
from app.core.skill_registry import Tool


class ChatManagementAdapter(Protocol):
    async def get_chat(self, chat_id: int | str) -> dict[str, Any]: ...
    async def get_member_count(self, chat_id: int | str) -> int: ...
    async def list_administrators(self, chat_id: int | str) -> list[dict[str, Any]]: ...
    async def send_message(self, chat_id: int | str, text: str) -> dict[str, Any]: ...
    async def delete_message(self, chat_id: int | str, message_id: int) -> bool: ...
    async def pin_message(self, chat_id: int | str, message_id: int, disable_notification: bool) -> bool: ...


class ManagementSkill:
    name = "management"
    version = "0.1.0"
    description = "Manage a Telegram group, supergroup, channel, or private chat where the bot has the required rights."
    configuration_schema: dict[str, Any] = {"type": "object", "properties": {}}
    required_permissions = frozenset()

    def __init__(self, adapter: ChatManagementAdapter, permissions: PermissionService) -> None:
        self.adapter = adapter
        self.permissions = permissions

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description, "configuration_schema": self.configuration_schema, "required_permissions": [], "tools": [tool.metadata() for tool in self.tools()]}

    def tools(self) -> tuple[Tool, ...]:
        async def chat_info(context: PermissionContext, arguments: dict[str, Any]) -> dict[str, Any]:
            return await self.adapter.get_chat(self._authorized_target(context, arguments, Permission.READ_MESSAGES))

        async def member_count(context: PermissionContext, arguments: dict[str, Any]) -> int:
            return await self.adapter.get_member_count(self._authorized_target(context, arguments, Permission.READ_MESSAGES))

        async def administrators(context: PermissionContext, arguments: dict[str, Any]) -> list[dict[str, Any]]:
            return await self.adapter.list_administrators(self._authorized_target(context, arguments, Permission.READ_MESSAGES))

        async def send_message(context: PermissionContext, arguments: dict[str, Any]) -> dict[str, Any]:
            target = self._authorized_target(context, arguments, Permission.SEND_MESSAGES)
            return await self.adapter.send_message(target, arguments["text"])

        async def delete_message(context: PermissionContext, arguments: dict[str, Any]) -> bool:
            target = self._authorized_target(context, arguments, Permission.DELETE_MESSAGES)
            return await self.adapter.delete_message(target, arguments["message_id"])

        async def pin_message(context: PermissionContext, arguments: dict[str, Any]) -> bool:
            target = self._authorized_target(context, arguments, Permission.PIN_MESSAGES)
            return await self.adapter.pin_message(target, arguments["message_id"], arguments.get("disable_notification", False))

        target = {"type": "integer", "description": "Optional target chat ID; defaults to the current chat."}
        return (
            Tool("get_chat_info", "Get information about the target Telegram chat.", {"type": "object", "properties": {"chat_id": target}, "additionalProperties": False}, frozenset({Permission.READ_MESSAGES}), chat_info),
            Tool("get_member_count", "Get the target chat member count.", {"type": "object", "properties": {"chat_id": target}, "additionalProperties": False}, frozenset({Permission.READ_MESSAGES}), member_count),
            Tool("list_administrators", "List administrators of the target chat.", {"type": "object", "properties": {"chat_id": target}, "additionalProperties": False}, frozenset({Permission.READ_MESSAGES}), administrators),
            Tool("send_message", "Send a text message to the target chat.", {"type": "object", "properties": {"chat_id": target, "text": {"type": "string", "minLength": 1, "maxLength": 4096}}, "required": ["text"], "additionalProperties": False}, frozenset({Permission.SEND_MESSAGES}), send_message),
            Tool("delete_message", "Delete one message from the target chat.", {"type": "object", "properties": {"chat_id": target, "message_id": {"type": "integer"}}, "required": ["message_id"], "additionalProperties": False}, frozenset({Permission.DELETE_MESSAGES}), delete_message),
            Tool("pin_message", "Pin one message in the target chat.", {"type": "object", "properties": {"chat_id": target, "message_id": {"type": "integer"}, "disable_notification": {"type": "boolean"}}, "required": ["message_id"], "additionalProperties": False}, frozenset({Permission.PIN_MESSAGES}), pin_message),
        )

    def _authorized_target(self, context: PermissionContext, arguments: dict[str, Any], permission: Permission) -> int:
        target = arguments.get("chat_id", context.chat_id)
        if not isinstance(target, (int, str)) or (isinstance(target, str) and not target.startswith("@")):
            raise ValueError("chat_id must be a numeric ID or @channelusername")
        self.permissions.require_user(context.user_id, target, frozenset({permission}))
        return target
