from __future__ import annotations

from typing import Any

from app.core.permissions import Permission, PermissionContext, PermissionService
from app.core.skill_registry import Tool
from app.storage.repositories import MessageRepository


class MessagesSkill:
    name = "messages"
    version = "0.1.0"
    description = "List messages received and indexed from a managed chat."
    configuration_schema: dict[str, Any] = {"type": "object", "properties": {}}
    required_permissions = frozenset({Permission.READ_LIBRARY})

    def __init__(self, repository: MessageRepository, permissions: PermissionService) -> None:
        self.repository, self.permissions = repository, permissions

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description, "configuration_schema": self.configuration_schema, "required_permissions": [p.value for p in self.required_permissions], "tools": [tool.metadata() for tool in self.tools()]}

    def tools(self) -> tuple[Tool, ...]:
        async def list_messages(context: PermissionContext, arguments: dict[str, Any]) -> list[dict[str, Any]]:
            target = arguments["target_id"]
            self.permissions.require_user(context.user_id, target, frozenset({Permission.READ_LIBRARY}))
            return self.repository.list(context.user_id, target, min(arguments.get("limit", 20), 100))

        return (Tool("list_messages", "List recently indexed messages from a managed chat.", {"type": "object", "properties": {"target_id": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["target_id"], "additionalProperties": False}, self.required_permissions, list_messages),)
