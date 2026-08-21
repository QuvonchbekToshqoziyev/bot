from __future__ import annotations

from app.core.skill_registry import Skill
from app.skills.library import LibrarySkill
from app.skills.management import ManagementSkill, ChatManagementAdapter
from app.skills.statistics import StatisticsSkill
from app.storage.repositories import LibraryRepository


def discover_skills(library_repository: LibraryRepository, management_adapter: ChatManagementAdapter, permissions) -> tuple[Skill, ...]:
    """Single skill catalog; the Telegram adapter does not know concrete skills."""
    return (StatisticsSkill(library_repository), LibrarySkill(library_repository), ManagementSkill(management_adapter, permissions))
