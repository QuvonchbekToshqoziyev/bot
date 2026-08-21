from __future__ import annotations

import asyncio
from typing import Any

from app.core.permissions import Permission, PermissionContext
from app.core.skill_registry import Tool
from app.storage.repositories import LibraryRepository


class LibrarySkill:
    name = "library"
    version = "0.1.0"
    description = "Minimal indexed message library demonstration."
    configuration_schema: dict[str, Any] = {"type": "object", "properties": {"retention_days": {"type": "integer", "minimum": 1}}}
    required_permissions = frozenset({Permission.READ_LIBRARY})

    def __init__(self, repository: LibraryRepository) -> None:
        self.repository = repository

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description, "configuration_schema": self.configuration_schema, "required_permissions": [p.value for p in self.required_permissions], "tools": [tool.metadata() for tool in self.tools()]}

    def tools(self) -> tuple[Tool, ...]:
        async def list_indexed(context: PermissionContext, arguments: dict[str, Any]) -> list[dict[str, Any]]:
            return await asyncio.to_thread(self.repository.list_messages, context.user_id, context.chat_id)
        return (Tool("list_indexed_messages", "List messages indexed for this workspace.", {"type": "object", "additionalProperties": False}, frozenset({Permission.READ_LIBRARY}), list_indexed),)
