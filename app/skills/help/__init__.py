from __future__ import annotations

from typing import Any, Callable

from app.core.permissions import PermissionContext
from app.core.skill_registry import Tool


class HelpSkill:
    name = "help"
    version = "0.1.0"
    description = "Explains what the bot can do and answers basic capability questions."
    configuration_schema: dict[str, Any] = {"type": "object", "properties": {}}
    required_permissions = frozenset()

    def __init__(self, capabilities: Callable[[int, int], list[dict[str, Any]]]) -> None:
        self.capabilities = capabilities

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "description": self.description, "configuration_schema": self.configuration_schema, "required_permissions": [], "tools": [tool.metadata() for tool in self.tools()]}

    def tools(self) -> tuple[Tool, ...]:
        async def answer_question(context: PermissionContext, arguments: dict[str, Any]) -> dict[str, Any]:
            items = self.capabilities(context.user_id, context.chat_id)
            enabled = [item for item in items if item["enabled"]]
            question = arguments["question"].strip().lower()
            if any(term in question for term in ("what can", "capabilit", "do you do", "help")):
                answer = "I can explain skills, answer basic capability questions, manage Telegram chats where I am an administrator, and run enabled skill tools."
            elif "skill" in question or "available" in question:
                answer = "Available skills:\n" + "\n".join(f"• {item['name']}: {item['description']}" for item in enabled) if enabled else "No skills are enabled in this chat yet."
            else:
                answer = "I answer questions about my capabilities. For a real task, choose Ask a task from the menu."
            return {"answer": answer, "enabled_skills": [item["name"] for item in enabled]}

        return (Tool("answer_question", "Answer a basic question about the bot and its enabled skills.", {"type": "object", "properties": {"question": {"type": "string", "minLength": 1, "maxLength": 1000}}, "required": ["question"], "additionalProperties": False}, frozenset(), answer_question),)
