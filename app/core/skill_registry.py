from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.core.permissions import Permission, PermissionContext, PermissionService


class SkillEnablementStore(Protocol):
    def is_enabled_for_chat(self, chat_id: int, skill_name: str) -> bool: ...

    def set_enabled(self, user_id: int, chat_id: int, skill_name: str, enabled: bool) -> None: ...

    def disable_for_chat(self, chat_id: int, skill_name: str) -> None: ...

    def enabled_configurations(self) -> list[tuple[int, int, str]]: ...


class ToolExecutor(Protocol):
    async def __call__(self, context: PermissionContext, arguments: dict[str, Any]) -> Any: ...


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    required_permissions: frozenset[Permission]
    execute: ToolExecutor

    def metadata(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema, "required_permissions": sorted(p.value for p in self.required_permissions)}

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict) or self.input_schema.get("type") != "object":
            raise ValueError(f"Invalid arguments for tool: {self.name}")
        properties = self.input_schema.get("properties", {})
        if self.input_schema.get("additionalProperties") is False:
            unknown = set(arguments) - set(properties)
            if unknown:
                raise ValueError(f"Unknown arguments for tool {self.name}: {', '.join(sorted(unknown))}")
        missing = set(self.input_schema.get("required", [])) - set(arguments)
        if missing:
            raise ValueError(f"Missing arguments for tool {self.name}: {', '.join(sorted(missing))}")


class Skill(Protocol):
    name: str
    version: str
    description: str
    configuration_schema: dict[str, Any]
    required_permissions: frozenset[Permission]

    def tools(self) -> tuple[Tool, ...]: ...

    def metadata(self) -> dict[str, Any]: ...


class SkillRegistry:
    def __init__(self, permission_service: PermissionService | None = None) -> None:
        self._skills: dict[str, Skill] = {}
        self.permissions = permission_service or PermissionService()
        self._enablements: SkillEnablementStore | None = None

    def attach_enablement_store(self, store: SkillEnablementStore) -> None:
        self._enablements = store

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Skill already registered: {skill.name}")
        tools = skill.tools()
        names = [tool.name for tool in tools]
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate tool in skill: {skill.name}")
        if any(not tool.required_permissions.issuperset(skill.required_permissions) for tool in tools):
            raise ValueError(f"Tool permissions weaken skill permissions: {skill.name}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"Unknown skill: {name}") from exc

    def enable(self, user_id: int, chat_id: int, name: str) -> None:
        self.get(name)
        self.permissions.require_user(user_id, chat_id, frozenset({Permission.MANAGE_SKILLS}))
        self._store().set_enabled(user_id, chat_id, name, True)

    def disable(self, user_id: int, chat_id: int, name: str) -> None:
        self.get(name)
        self.permissions.require_user(user_id, chat_id, frozenset({Permission.MANAGE_SKILLS}))
        self._store().disable_for_chat(chat_id, name)

    def is_enabled(self, user_id: int, chat_id: int, name: str) -> bool:
        return self._store().is_enabled_for_chat(chat_id, name)

    def enabled(self, user_id: int, chat_id: int) -> tuple[Skill, ...]:
        return tuple(skill for name, skill in self._skills.items() if self.is_enabled(user_id, chat_id, name))

    def metadata(self, user_id: int, chat_id: int) -> list[dict[str, Any]]:
        return [skill.metadata() | {"enabled": self.is_enabled(user_id, chat_id, skill.name)} for skill in self._skills.values()]

    def enabled_tool_metadata(self, user_id: int, chat_id: int) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for skill in self.enabled(user_id, chat_id):
            for tool in skill.tools():
                tools.append({"skill": skill.name, "skill_description": skill.description, **tool.metadata()})
        return tools

    def _store(self) -> SkillEnablementStore:
        if self._enablements is None:
            raise RuntimeError("Skill enablement store is not configured")
        return self._enablements

    async def execute(self, user_id: int, chat_id: int, skill_name: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self.is_enabled(user_id, chat_id, skill_name):
            raise PermissionError(f"Skill is disabled: {skill_name}")
        context = self.permissions.context_for(user_id, chat_id)
        skill = self.get(skill_name)
        try:
            tool = next(tool for tool in skill.tools() if tool.name == tool_name)
        except StopIteration as exc:
            raise KeyError(f"Unknown tool: {skill_name}.{tool_name}") from exc
        tool.validate_arguments(arguments)
        self.permissions.require(context, tool.required_permissions)
        return await tool.execute(context, arguments)
