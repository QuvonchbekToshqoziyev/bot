from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)


class ResponsesClient(Protocol):
    @property
    def responses(self) -> Any: ...


@dataclass(frozen=True, slots=True)
class AIResult:
    status: str
    message: str
    selected_skills: tuple[str, ...] = ()


class AIOrchestrator:
    """Constrained AI task runner; the registry remains the authorization boundary."""

    def __init__(self, registry: SkillRegistry, client: ResponsesClient, model: str = "gpt-5", max_tool_rounds: int = 8, max_output_tokens: int = 256) -> None:
        self.registry = registry
        self.client = client
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.max_output_tokens = max_output_tokens

    async def handle_task(self, user_id: int, chat_id: int, task: str) -> AIResult:
        available = self.registry.enabled_tool_metadata(user_id, chat_id)
        if not available:
            return AIResult("not_found", "No enabled skill matches this task.")

        by_skill: dict[str, list[dict[str, Any]]] = {}
        for item in available:
            by_skill.setdefault(item["skill"], []).append(item)
        try:
            selection = await self._select_skills(task, available)
        except Exception:
            logger.exception("AI skill selection failed")
            return await self._fallback(user_id, chat_id, task, available)
        selected = tuple(name for name in selection if name in by_skill)
        if not selected:
            return AIResult("not_found", "No enabled skill matches this task.")

        tools = [item for name in selected for item in by_skill[name]]
        try:
            response = await self.client.responses.create(
                model=self.model,
                input=task,
                instructions="Use only the supplied tools. Do not invent capabilities or call tools outside the selected skills.",
                tools=[self._function_definition(item) for item in tools],
                tool_choice="auto",
                max_output_tokens=self.max_output_tokens,
                store=False,
            )
        except Exception:
            logger.exception("AI tool execution request failed")
            return await self._fallback(user_id, chat_id, task, tools, selected)
        for _ in range(self.max_tool_rounds):
            calls = [item for item in getattr(response, "output", ()) if self._type(item) == "function_call"]
            if not calls:
                return AIResult("completed", getattr(response, "output_text", "Task completed."), selected)
            outputs = []
            allowed = {f"{item['skill']}__{item['name']}": item for item in tools}
            for call in calls:
                name = self._value(call, "name")
                if name not in allowed:
                    return AIResult("failed", "The model requested a tool outside the selected skills.", selected)
                item = allowed[name]
                try:
                    arguments = json.loads(self._value(call, "arguments"))
                    result = await self.registry.execute(user_id, chat_id, item["skill"], item["name"], arguments)
                except Exception as exc:
                    result = {"error": str(exc)}
                outputs.append({"type": "function_call_output", "call_id": self._value(call, "call_id"), "output": json.dumps(result, default=str)})
            try:
                response = await self.client.responses.create(
                    model=self.model,
                    previous_response_id=self._value(response, "id"),
                    input=outputs,
                    tools=[self._function_definition(item) for item in tools],
                    tool_choice="auto",
                    max_output_tokens=self.max_output_tokens,
                    store=False,
                )
            except Exception:
                logger.exception("AI tool continuation failed")
                return await self._fallback(user_id, chat_id, task, tools, selected)
        return AIResult("failed", "The AI task exceeded the tool-call limit.", selected)

    async def _fallback(self, user_id: int, chat_id: int, task: str, available: list[dict[str, Any]], selected: tuple[str, ...] = ()) -> AIResult:
        """Handle safe, no-argument read requests without spending provider credits."""
        query = task.lower()
        if any(term in query for term in ("what can", "capabilit", "do you do", "help")):
            candidates = [item for item in available if item["skill"] == "help" and item["name"] == "answer_question"]
            if candidates:
                result = await self.registry.execute(user_id, chat_id, "help", "answer_question", {"question": task})
                return AIResult("completed", result["answer"], ("help",))
        words = {word.strip(".,?!:;\"'") for word in query.split()}
        for item in available:
            required = item["input_schema"].get("required", [])
            if required:
                continue
            haystack = f"{item['skill']} {item['name']} {item['description']}".lower()
            if words & set(haystack.replace("_", " ").split()):
                result = await self.registry.execute(user_id, chat_id, item["skill"], item["name"], {})
                return AIResult("completed", json.dumps(result, indent=2, default=str), (item["skill"],))
        return AIResult("failed", "AI is unavailable because the provider has insufficient credits, and this task needs a language model. Add provider credits or try a basic capability/statistics request.", selected)

    async def _select_skills(self, task: str, available: list[dict[str, Any]]) -> tuple[str, ...]:
        catalog: dict[str, dict[str, Any]] = {}
        for item in available:
            catalog.setdefault(item["skill"], {"description": item["skill_description"], "tools": []})["tools"].append(item["name"])
        catalog_text = "\n".join(f"- {name}: {details['description']} (tools: {', '.join(details['tools'])})" for name, details in catalog.items())
        response = await self.client.responses.create(
            model=self.model,
            input=task,
            instructions=f"Select only skills that are directly useful for the task. Return an empty list when none match. Enabled skill catalog:\n{catalog_text}",
            tools=[{
                "type": "function",
                "name": "select_skills",
                "description": "Select the enabled skills that directly match the task.",
                "parameters": {"type": "object", "properties": {"skills": {"type": "array", "items": {"type": "string", "enum": list(catalog)}, "uniqueItems": True}}, "required": ["skills"], "additionalProperties": False},
                "strict": True,
            }],
            tool_choice={"type": "function", "name": "select_skills"},
            max_output_tokens=self.max_output_tokens,
            store=False,
        )
        calls = [item for item in getattr(response, "output", ()) if self._type(item) == "function_call" and self._value(item, "name") == "select_skills"]
        if not calls:
            return ()
        try:
            selected = json.loads(self._value(calls[0], "arguments")).get("skills", [])
        except (TypeError, json.JSONDecodeError):
            return ()
        return tuple(name for name in selected if isinstance(name, str))

    @staticmethod
    def _function_definition(item: dict[str, Any]) -> dict[str, Any]:
        return {"type": "function", "name": f"{item['skill']}__{item['name']}", "description": f"[{item['skill']}] {item['description']}", "parameters": item["input_schema"], "strict": True}

    @staticmethod
    def _type(item: Any) -> str:
        return item.get("type", "") if isinstance(item, dict) else getattr(item, "type", "")

    @staticmethod
    def _value(item: Any, key: str) -> Any:
        return item.get(key) if isinstance(item, dict) else getattr(item, key)
