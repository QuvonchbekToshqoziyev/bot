from __future__ import annotations

import asyncio

import pytest

from app.core.models import Chat, User
from app.core.local_tasks import LocalTaskRouter
from app.core.permissions import PermissionDenied, PermissionService
from app.core.router import CommandRouter
from app.core.skill_registry import SkillRegistry
from app.skills.library import LibrarySkill
from app.skills.management import ManagementSkill
from app.skills.statistics import StatisticsSkill
from app.storage.database import Database
from app.storage.repositories import AuthorizationRepository, LibraryRepository, SkillConfigurationRepository, WorkspaceRepository
from app.ai.orchestrator import AIOrchestrator


def make_registry(admins: frozenset[int] = frozenset()):
    db = Database("sqlite:///:memory:")
    library = LibraryRepository(db)
    configs = SkillConfigurationRepository(db)
    registry = SkillRegistry(PermissionService(admin_user_ids=admins))
    registry.attach_enablement_store(configs)
    registry.register(StatisticsSkill(library))
    registry.register(LibrarySkill(library))
    return db, library, configs, registry


def test_registration_and_duplicate_rejection():
    _, _, _, registry = make_registry()
    with pytest.raises(ValueError):
        registry.register(StatisticsSkill())
    assert {skill.name for skill in registry.enabled(1, 2)} == set()


def test_enable_disable_and_disabled_execution_rejection():
    _, _, _, registry = make_registry(frozenset({1}))
    with pytest.raises(PermissionError):
        asyncio.run(registry.execute(1, 2, "statistics", "get_stats", {}))
    registry.enable(1, 2, "statistics")
    assert asyncio.run(registry.execute(1, 2, "statistics", "get_stats", {}))["chat_id"] == 2
    registry.disable(1, 2, "statistics")
    assert not registry.is_enabled(1, 2, "statistics")


def test_permission_rejection_and_success():
    db, library, _, registry = make_registry()
    authorization = AuthorizationRepository(db)
    authorization.grant_role(1, 2, "admin")
    registry.permissions = PermissionService(authorization.permissions_for)
    library.add_message(1, 2, 9, "hello")
    registry.enable(1, 2, "library")
    authorization.grant_role(3, 2, "member")
    assert asyncio.run(registry.execute(3, 2, "library", "list_indexed_messages", {})) == []
    assert asyncio.run(registry.execute(1, 2, "library", "list_indexed_messages", {})) == [{"telegram_message_id": 9, "text": "hello"}]

    registry.permissions = PermissionService(authorization.permissions_for)
    with pytest.raises(PermissionDenied):
        asyncio.run(registry.execute(4, 2, "library", "list_indexed_messages", {}))


def test_execution_identity_cannot_be_forged():
    _, library, _, registry = make_registry(frozenset({1}))
    library.add_message(1, 2, 9, "private")
    registry.enable(1, 2, "library")
    assert asyncio.run(registry.execute(1, 2, "library", "list_indexed_messages", {})) == [{"telegram_message_id": 9, "text": "private"}]


def test_metadata_and_persistence():
    db = Database("sqlite:///:memory:")
    workspace = WorkspaceRepository(db)
    workspace.upsert_user(User(1, "alice"))
    workspace.upsert_chat(Chat(2, "team"))
    configs = SkillConfigurationRepository(db)
    configs.set_enabled(1, 2, "library", True, {"retention_days": 30})
    configs.set_enabled(1, 2, "library", False)
    assert not configs.is_enabled_for_chat(2, "library")
    assert db.connection.execute("SELECT config_json FROM skill_configurations").fetchone()[0] == '{"retention_days": 30}'
    _, _, _, registry = make_registry()
    metadata = registry.get("library").metadata()
    assert metadata["tools"][0]["input_schema"]["type"] == "object"


def test_admin_router_persists_configuration():
    db, _, configs, registry = make_registry(frozenset({99}))
    router = CommandRouter(registry)
    with pytest.raises(PermissionDenied):
        router.enable(1, 2, "library")
    router.enable(99, 2, "library")
    assert registry.is_enabled(99, 2, "library")
    assert configs.is_enabled_for_chat(2, "library")


def test_tool_input_validation():
    _, _, _, registry = make_registry(frozenset({1}))
    registry.enable(1, 2, "statistics")
    with pytest.raises(ValueError):
        asyncio.run(registry.execute(1, 2, "statistics", "get_stats", {"unexpected": True}))


class FakeManagementAdapter:
    def __init__(self):
        self.sent = []

    async def get_chat(self, chat_id):
        return {"id": chat_id}

    async def get_member_count(self, chat_id):
        return 3

    async def list_administrators(self, chat_id):
        return []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))
        return {"chat_id": chat_id, "text": text}

    async def delete_message(self, chat_id, message_id):
        return True

    async def pin_message(self, chat_id, message_id, disable_notification):
        return True


def test_management_skill_rechecks_permissions_for_target_chat():
    db = Database("sqlite:///:memory:")
    configs = SkillConfigurationRepository(db)
    authorization = AuthorizationRepository(db)
    authorization.grant_role(1, 10, "admin")
    authorization.grant_role(1, 99, "admin")
    permissions = PermissionService(authorization.permissions_for)
    adapter = FakeManagementAdapter()
    registry = SkillRegistry(permissions)
    registry.attach_enablement_store(configs)
    registry.register(ManagementSkill(adapter, permissions))
    registry.enable(1, 10, "management")
    result = asyncio.run(registry.execute(1, 10, "management", "send_message", {"chat_id": 99, "text": "hello"}))
    assert result == {"chat_id": 99, "text": "hello"}
    assert adapter.sent == [(99, "hello")]
    authorization.grant_role(2, 10, "member")
    with pytest.raises(PermissionDenied):
        asyncio.run(registry.execute(2, 10, "management", "send_message", {"chat_id": 99, "text": "blocked"}))


class FakeResponse:
    def __init__(self, output, output_text="", response_id="r1"):
        self.output = output
        self.output_text = output_text
        self.id = response_id


class FakeResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


class FailingResponses:
    async def create(self, **kwargs):
        raise RuntimeError("provider unavailable")


class FailingClient:
    responses = FailingResponses()


def test_ai_reports_no_matching_enabled_skill():
    _, _, _, registry = make_registry(frozenset({1}))
    client = FakeClient([FakeResponse([{"type": "function_call", "name": "select_skills", "arguments": '{"skills": []}', "call_id": "c1"}])])
    result = asyncio.run(AIOrchestrator(registry, client).handle_task(1, 2, "delete all messages"))
    assert result.status == "not_found"
    assert result.selected_skills == ()
    assert len(client.responses.calls) == 0


def test_ai_exposes_and_executes_only_selected_enabled_skill():
    _, library, _, registry = make_registry(frozenset({1}))
    library.add_message(1, 2, 9, "hello")
    registry.enable(1, 2, "library")
    client = FakeClient([
        FakeResponse([{"type": "function_call", "name": "select_skills", "arguments": '{"skills": ["library"]}', "call_id": "select"}], response_id="select-response"),
        FakeResponse([{"type": "function_call", "name": "library__list_indexed_messages", "arguments": "{}", "call_id": "tool"}], response_id="tool-response"),
        FakeResponse([], "Done.", "final-response"),
    ])
    result = asyncio.run(AIOrchestrator(registry, client).handle_task(1, 2, "show my indexed messages"))
    assert result.status == "completed"
    assert result.selected_skills == ("library",)
    execution_tools = client.responses.calls[1]["tools"]
    assert [tool["name"] for tool in execution_tools] == ["library__list_indexed_messages"]
    assert "statistics__get_stats" not in str(execution_tools)


def test_ai_falls_back_to_safe_basic_tool_when_provider_is_unavailable():
    _, _, _, registry = make_registry(frozenset({1}))
    registry.enable(1, 2, "statistics")
    result = asyncio.run(AIOrchestrator(registry, FailingClient()).handle_task(1, 2, "statistics"))
    assert result.status == "completed"
    assert '"indexed_messages": 0' in result.message


def test_local_task_router_handles_statistics_without_ai():
    _, _, _, registry = make_registry(frozenset({1}))
    registry.enable(1, 2, "statistics")
    result = asyncio.run(LocalTaskRouter(registry).handle(1, 2, "show statistics"))
    assert result.handled is True
    assert result.skill == "statistics"
    assert "indexed_messages" in result.message
