from __future__ import annotations

from app.core.skill_registry import Skill
from app.skills.library import LibrarySkill
from app.skills.help import HelpSkill
from app.skills.management import ManagementSkill, ChatManagementAdapter
from app.skills.messages import MessagesSkill
from app.skills.search import SearchSkill
from app.skills.backup import BackupSkill
from app.skills.scheduler import SchedulerSkill
from app.skills.statistics import StatisticsSkill
from app.storage.repositories import LibraryRepository, MessageRepository, ScheduledPostRepository


def discover_skills(library_repository: LibraryRepository, management_adapter: ChatManagementAdapter, permissions, message_repository: MessageRepository, scheduled_posts: ScheduledPostRepository) -> tuple[Skill, ...]:
    """Single skill catalog; the Telegram adapter does not know concrete skills."""
    return (StatisticsSkill(library_repository), LibrarySkill(library_repository), ManagementSkill(management_adapter, permissions), MessagesSkill(message_repository, permissions), SearchSkill(message_repository, permissions), BackupSkill(message_repository, management_adapter, permissions), SchedulerSkill(scheduled_posts, permissions))
