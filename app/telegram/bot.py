from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, TypeHandler, filters

from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.permissions import PermissionService
from app.core.router import CommandRouter
from app.core.skill_registry import SkillRegistry
from app.ai.orchestrator import AIOrchestrator
from app.skills.catalog import discover_skills
from app.skills.help import HelpSkill
from app.skills.workspace import WorkspaceSkill
from app.storage.database import Database
from app.storage.repositories import AIConfigurationRepository, AuthorizationRepository, LibraryRepository, ManagedChatRepository, MessageRepository, ScheduledPostRepository, SkillConfigurationRepository
from app.telegram.handlers import build_handlers
from app.telegram.management_adapter import TelegramManagementAdapter
from app.telegram.scheduler import run_scheduler


def create_application(settings: Settings) -> Application:
    database = Database(settings.database_url)
    application = Application.builder().token(settings.telegram_bot_token).build()
    authorization = AuthorizationRepository(database)
    registry = SkillRegistry(PermissionService(authorization.permissions_for, settings.admin_user_ids))
    library_repository = LibraryRepository(database)
    management_adapter = TelegramManagementAdapter(application.bot)
    message_repository = MessageRepository(database)
    scheduled_posts = ScheduledPostRepository(database)
    for skill in discover_skills(library_repository, management_adapter, registry.permissions, message_repository, scheduled_posts):
        registry.register(skill)
    registry.register(HelpSkill(registry.metadata))
    registry.register(WorkspaceSkill(registry.metadata))
    configurations = SkillConfigurationRepository(database)
    registry.attach_enablement_store(configurations)
    router = CommandRouter(registry)
    ai = None
    if settings.openai_api_key:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logging.getLogger(__name__).warning("OPENAI_API_KEY is set but the optional OpenAI dependency is not installed")
        else:
            ai = AIOrchestrator(registry, AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url), settings.openai_model, max_output_tokens=settings.ai_max_output_tokens)
    ai_configuration = AIConfigurationRepository(database)
    managed_chats = ManagedChatRepository(database)
    start, help_command, skills, skill_command, status, ask, ai_command, callback, turn, index_update = build_handlers(router, registry, ai, ai_configuration, configurations, managed_chats, message_repository)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("skills", skills))
    application.add_handler(CommandHandler("skill", skill_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CallbackQueryHandler(callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, turn))
    application.add_handler(TypeHandler(Update, index_update), group=1)

    async def post_init(app: Application) -> None:
        app.create_task(run_scheduler(scheduled_posts, management_adapter.send_message), name="scheduled-post-runner")

    application.post_init = post_init
    return application


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    logging.getLogger(__name__).info("Starting Telegram Workspace Manager")
    create_application(settings).run_polling()


if __name__ == "__main__":
    main()
