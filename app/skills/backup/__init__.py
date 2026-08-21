from __future__ import annotations

from typing import Any, Protocol

from app.core.permissions import Permission, PermissionContext, PermissionService
from app.core.skill_registry import Tool
from app.storage.repositories import MessageRepository


class MessageSender(Protocol):
    async def send_message(self, chat_id: int | str, text: str) -> dict[str, Any]: ...


class BackupSkill:
    name = "backup"
    version = "0.1.0"
    description = "Copy indexed messages from one managed chat to another."
    configuration_schema: dict[str, Any] = {"type": "object", "properties": {}}
    required_permissions = frozenset({Permission.MANAGE_BACKUP})

    def __init__(self, repository: MessageRepository, sender: MessageSender, permissions: PermissionService) -> None:
        self.repository, self.sender, self.permissions = repository, sender, permissions

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description, "configuration_schema": self.configuration_schema, "required_permissions": [p.value for p in self.required_permissions], "tools": [tool.metadata() for tool in self.tools()]}

    def tools(self) -> tuple[Tool, ...]:
        async def copy_messages(context: PermissionContext, arguments: dict[str, Any]) -> dict[str, Any]:
            source, destination = arguments["source_id"], arguments["destination_id"]
            self.permissions.require_user(context.user_id, source, frozenset({Permission.MANAGE_BACKUP}))
            self.permissions.require_user(context.user_id, destination, frozenset({Permission.MANAGE_BACKUP}))
            messages = self.repository.list(context.user_id, source, min(arguments.get("limit", 20), 100))
            sent = 0
            for message in reversed(messages):
                await self.sender.send_message(destination, message["text"])
                sent += 1
            return {"source": source, "destination": destination, "copied": sent}

        return (Tool("copy_messages", "Copy indexed messages between managed chats.", {"type": "object", "properties": {"source_id": {"type": "string"}, "destination_id": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["source_id", "destination_id"], "additionalProperties": False}, self.required_permissions, copy_messages),)
