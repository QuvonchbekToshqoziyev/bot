from __future__ import annotations

import asyncio
import re
from typing import Any, Protocol

from telegram import Update

from app.core.permissions import Permission, PermissionContext, PermissionService
from app.core.skill_registry import Tool
from app.storage.repositories import ManagedChatRepository, ModerationRepository


class ModerationAdapter(Protocol):
    async def delete_message(self, chat_id: int | str, message_id: int) -> bool: ...
    async def send_message(self, chat_id: int | str, text: str) -> dict[str, Any]: ...


class ModerationSkill:
    name = "moderation"
    version = "0.1.0"
    description = "Opt-in link and keyword filtering, welcome/farewell messages, and chat rules."
    configuration_schema: dict[str, Any] = {"type": "object", "properties": {}}
    required_permissions = frozenset()

    def __init__(self, repository: ModerationRepository, managed_chats: ManagedChatRepository, adapter: ModerationAdapter, permissions: PermissionService) -> None:
        self.repository, self.managed_chats, self.adapter, self.permissions = repository, managed_chats, adapter, permissions

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description, "configuration_schema": self.configuration_schema, "required_permissions": [], "tools": [tool.metadata() for tool in self.tools()]}

    def tools(self) -> tuple[Tool, ...]:
        async def get_settings(context: PermissionContext, arguments: dict[str, Any]) -> dict[str, Any]:
            target = self._target(context, arguments)
            self.permissions.require_user(context.user_id, target, frozenset({Permission.READ_MESSAGES}))
            return self.repository.get(context.user_id, target)

        async def update_settings(context: PermissionContext, arguments: dict[str, Any]) -> dict[str, Any]:
            target = self._target(context, arguments)
            self.permissions.require_user(context.user_id, target, frozenset({Permission.MANAGE_SKILLS}))
            values = {key: value for key, value in arguments.items() if key != "target_id"}
            if "keywords" in values:
                values["keywords"] = [str(word).strip().lower() for word in values["keywords"] if str(word).strip()][:50]
            return self.repository.update(context.user_id, target, values)

        async def set_rules(context: PermissionContext, arguments: dict[str, Any]) -> dict[str, Any]:
            target = self._target(context, arguments)
            self.permissions.require_user(context.user_id, target, frozenset({Permission.MANAGE_SKILLS}))
            return {"target_id": str(target), "rules": self.repository.update(context.user_id, target, {"rules": arguments["text"]})["rules"]}

        target = {"type": "string", "description": "Managed target ID or @username."}
        return (
            Tool("get_settings", "Get moderation settings for a managed target.", {"type": "object", "properties": {"target_id": target}, "required": ["target_id"], "additionalProperties": False}, frozenset({Permission.READ_MESSAGES}), get_settings),
            Tool("update_settings", "Update opt-in moderation settings.", {"type": "object", "properties": {"target_id": target, "enabled": {"type": "boolean"}, "link_filter": {"type": "boolean"}, "keyword_filter": {"type": "boolean"}, "keywords": {"type": "array"}, "welcome": {"type": "boolean"}, "farewell": {"type": "boolean"}, "welcome_text": {"type": "string", "maxLength": 4096}, "farewell_text": {"type": "string", "maxLength": 4096}}, "required": ["target_id"], "additionalProperties": False}, frozenset({Permission.MANAGE_SKILLS}), update_settings),
            Tool("set_rules", "Set the rules text for a managed target.", {"type": "object", "properties": {"target_id": target, "text": {"type": "string", "maxLength": 4096}}, "required": ["target_id", "text"], "additionalProperties": False}, frozenset({Permission.MANAGE_SKILLS}), set_rules),
        )

    def _target(self, context: PermissionContext, arguments: dict[str, Any]) -> int | str:
        target = arguments["target_id"]
        if not isinstance(target, str) or not target:
            raise ValueError("target_id is required")
        return target

    async def handle_update(self, update: Update) -> None:
        message = update.message
        if message is None:
            return
        target = str(message.chat.id)
        owners = await asyncio.to_thread(self.managed_chats.owners_for, message.chat.id)
        configs = [await asyncio.to_thread(self.repository.get, owner_id, target) for owner_id in owners]
        configs = [config for config in configs if config["enabled"]]
        if not configs:
            return
        name = message.from_user.full_name if message.from_user else "A member"
        welcome = next((config for config in configs if config["welcome"]), None)
        farewell = next((config for config in configs if config["farewell"]), None)
        if welcome and message.new_chat_members:
            await self.adapter.send_message(target, welcome["welcome_text"].format(name=name))
        if farewell and message.left_chat_member:
            await self.adapter.send_message(target, farewell["farewell_text"].format(name=name))
        if not message.text:
            return
        blocked = any(config["link_filter"] and re.search(r"(?:https?://|www\.|t\.me/)", message.text, re.I) for config in configs)
        blocked = blocked or any(config["keyword_filter"] and any(word in message.text.lower() for word in config["keywords"]) for config in configs)
        if blocked:
            await self.adapter.delete_message(target, message.message_id)
            await self.adapter.send_message(target, "Message removed by chat moderation settings.")
