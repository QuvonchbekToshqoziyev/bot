from __future__ import annotations

import time
from typing import Any

from app.core.permissions import Permission, PermissionContext, PermissionService
from app.core.skill_registry import Tool
from app.storage.repositories import ScheduledPostRepository


class SchedulerSkill:
    name = "scheduler"
    version = "0.1.0"
    description = "Schedule, list, and cancel text posts for managed chats."
    configuration_schema: dict[str, Any] = {"type": "object", "properties": {}}
    required_permissions = frozenset({Permission.SCHEDULE_MESSAGES})

    def __init__(self, repository: ScheduledPostRepository, permissions: PermissionService) -> None:
        self.repository, self.permissions = repository, permissions

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description, "configuration_schema": self.configuration_schema, "required_permissions": [p.value for p in self.required_permissions], "tools": [tool.metadata() for tool in self.tools()]}

    def tools(self) -> tuple[Tool, ...]:
        async def schedule_post(context: PermissionContext, arguments: dict[str, Any]) -> dict[str, Any]:
            target = arguments["target_id"]
            self.permissions.require_user(context.user_id, target, frozenset({Permission.SCHEDULE_MESSAGES}))
            if arguments["delay_seconds"] < 1 or arguments["delay_seconds"] > 31536000:
                raise ValueError("delay_seconds must be between 1 second and 365 days")
            post_id = self.repository.create(context.user_id, target, arguments["text"], int(time.time()) + arguments["delay_seconds"])
            return {"id": post_id, "target_id": target, "delay_seconds": arguments["delay_seconds"]}

        async def list_posts(context: PermissionContext, arguments: dict[str, Any]) -> list[dict[str, Any]]:
            target = arguments.get("target_id")
            if target is not None:
                self.permissions.require_user(context.user_id, target, frozenset({Permission.SCHEDULE_MESSAGES}))
            return self.repository.list(context.user_id, arguments.get("target_id"))

        async def cancel_post(context: PermissionContext, arguments: dict[str, Any]) -> dict[str, Any]:
            self.repository.mark(arguments["id"], "cancelled", context.user_id)
            return {"id": arguments["id"], "status": "cancelled"}

        return (
            Tool("schedule_post", "Schedule a text post for a managed chat.", {"type": "object", "properties": {"target_id": {"type": "string"}, "text": {"type": "string", "minLength": 1, "maxLength": 4096}, "delay_seconds": {"type": "integer"}}, "required": ["target_id", "text", "delay_seconds"], "additionalProperties": False}, self.required_permissions, schedule_post),
            Tool("list_scheduled_posts", "List scheduled posts.", {"type": "object", "properties": {"target_id": {"type": "string"}}, "additionalProperties": False}, self.required_permissions, list_posts),
            Tool("cancel_scheduled_post", "Cancel a scheduled post.", {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"], "additionalProperties": False}, self.required_permissions, cancel_post),
        )
