from __future__ import annotations

import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.permissions import PermissionService
from app.core.router import CommandRouter
from app.core.skill_registry import SkillRegistry
from app.ai.orchestrator import AIOrchestrator
from app.skills.catalog import discover_skills
from app.skills.help import HelpSkill
from app.storage.database import Database
from app.storage.repositories import AIConfigurationRepository, AuthorizationRepository, LibraryRepository, SkillConfigurationRepository
from app.telegram.handlers import build_handlers
from app.telegram.management_adapter import TelegramManagementAdapter


def create_application(settings: Settings) -> Application:
    database = Database(settings.database_url)
    application = Application.builder().token(settings.telegram_bot_token).build()
    authorization = AuthorizationRepository(database)
    registry = SkillRegistry(PermissionService(authorization.permissions_for, settings.admin_user_ids))
    library_repository = LibraryRepository(database)
    for skill in discover_skills(library_repository, TelegramManagementAdapter(application.bot), registry.permissions):
        registry.register(skill)
    registry.register(HelpSkill(registry.metadata))
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
    start, help_command, skills, skill_command, status, ask, ai_command, callback, turn = build_handlers(router, registry, ai, ai_configuration, configurations)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("skills", skills))
    application.add_handler(CommandHandler("skill", skill_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CallbackQueryHandler(callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, turn))
    return application


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    logging.getLogger(__name__).info("Starting Telegram Workspace Manager")
    create_application(settings).run_polling()


if __name__ == "__main__":
    main()
