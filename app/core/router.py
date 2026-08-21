from __future__ import annotations

from dataclasses import dataclass

from app.core.skill_registry import SkillRegistry


@dataclass(slots=True)
class CommandRouter:
    registry: SkillRegistry

    def enable(self, user_id: int, chat_id: int, name: str) -> None:
        self.registry.enable(user_id, chat_id, name)

    def disable(self, user_id: int, chat_id: int, name: str) -> None:
        self.registry.disable(user_id, chat_id, name)
