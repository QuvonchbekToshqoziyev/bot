from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.core.skill_registry import SkillRegistry


@dataclass(frozen=True, slots=True)
class LocalTaskResult:
    handled: bool
    message: str = ""
    skill: str | None = None


class LocalTaskRouter:
    """Small deterministic router for common tasks; no model or network call."""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    async def handle(self, user_id: int, chat_id: int, task: str) -> LocalTaskResult:
        query = task.lower()
        available = self.registry.enabled_tool_metadata(user_id, chat_id)
        if any(term in query for term in ("what can", "capabilit", "do you do", "help")):
            item = next((item for item in available if item["skill"] == "help" and item["name"] == "answer_question"), None)
            if item:
                result = await self.registry.execute(user_id, chat_id, "help", "answer_question", {"question": task})
                return LocalTaskResult(True, result["answer"], "help")

        words = set(re.findall(r"[a-z0-9_]+", query))
        candidates: list[tuple[int, dict[str, Any]]] = []
        for item in available:
            if item["input_schema"].get("required"):
                continue
            vocabulary = set(re.findall(r"[a-z0-9_]+", f"{item['skill']} {item['name']} {item['description']}".lower()))
            score = len(words & vocabulary)
            if score:
                candidates.append((score, item))
        if not candidates:
            return LocalTaskResult(False)
        _, item = max(candidates, key=lambda candidate: candidate[0])
        result = await self.registry.execute(user_id, chat_id, item["skill"], item["name"], {})
        return LocalTaskResult(True, str(result), item["skill"])
