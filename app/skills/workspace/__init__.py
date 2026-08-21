from __future__ import annotations

from typing import Any, Callable

from app.core.permissions import PermissionContext
from app.core.skill_registry import Tool


class WorkspaceSkill:
    name = "workspace"
    version = "0.1.0"
    description = "Shows the bot status and enabled workspace skills."
    configuration_schema: dict[str, Any] = {"type": "object", "properties": {}}
    required_permissions = frozenset()

    def __init__(self, capabilities: Callable[[int, int], list[dict[str, Any]]]) -> None:
        self.capabilities = capabilities

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description, "configuration_schema": self.configuration_schema, "required_permissions": [], "tools": [tool.metadata() for tool in self.tools()]}

    def tools(self) -> tuple[Tool, ...]:
        async def overview(context: PermissionContext, arguments: dict[str, Any]) -> dict[str, Any]:
            items = self.capabilities(context.user_id, context.chat_id)
            return {"status": "online", "enabled_skills": [item["name"] for item in items if item["enabled"]], "available_skills": [item["name"] for item in items]}

        return (Tool("get_overview", "Show bot status and enabled skills for this chat.", {"type": "object", "additionalProperties": False}, frozenset(), overview),)
