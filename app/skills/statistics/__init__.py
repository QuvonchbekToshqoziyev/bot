from __future__ import annotations

import asyncio
from typing import Any

from app.core.permissions import Permission, PermissionContext
from app.core.skill_registry import Tool
from app.storage.repositories import LibraryRepository


class StatisticsSkill:
    name = "statistics"
    version = "0.1.0"
    description = "Basic workspace statistics."
    configuration_schema: dict[str, Any] = {"type": "object", "properties": {}}
    required_permissions = frozenset({Permission.READ_MESSAGES})

    def __init__(self, repository: LibraryRepository | None = None) -> None:
        self.repository = repository

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description, "configuration_schema": self.configuration_schema, "required_permissions": [p.value for p in self.required_permissions], "tools": [tool.metadata() for tool in self.tools()]}

    def tools(self) -> tuple[Tool, ...]:
        async def get_stats(context: PermissionContext, arguments: dict[str, Any]) -> dict[str, int]:
            messages = await asyncio.to_thread(self.repository.list_messages, context.user_id, context.chat_id) if self.repository else []
            return {"user_id": context.user_id, "chat_id": context.chat_id, "indexed_messages": len(messages)}
        return (Tool("get_stats", "Return basic workspace statistics.", {"type": "object", "additionalProperties": False}, frozenset({Permission.READ_MESSAGES}), get_stats),)
