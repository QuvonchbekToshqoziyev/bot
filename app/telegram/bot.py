from __future__ import annotations

import logging

from telegram.ext import Application, CommandHandler

from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.permissions import PermissionService
from app.core.router import CommandRouter
from app.core.skill_registry import SkillRegistry
from app.ai.orchestrator import AIOrchestrator
from app.skills.catalog import discover_skills
from app.storage.database import Database
from app.storage.repositories import AuthorizationRepository, LibraryRepository, SkillConfigurationRepository
from app.telegram.handlers import build_handlers


def create_application(settings: Settings) -> Application:
    database = Database(settings.database_url)
    authorization = AuthorizationRepository(database)
    registry = SkillRegistry(PermissionService(authorization.permissions_for, settings.admin_user_ids))
    library_repository = LibraryRepository(database)
    for skill in discover_skills(library_repository):
        registry.register(skill)
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
            ai = AIOrchestrator(registry, AsyncOpenAI(api_key=settings.openai_api_key), settings.openai_model)
    start, help_command, skills, skill_command, status, ask = build_handlers(router, registry, ai)
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("skills", skills))
    application.add_handler(CommandHandler("skill", skill_command))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("ask", ask))
    return application


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    logging.getLogger(__name__).info("Starting Telegram Workspace Manager")
    create_application(settings).run_polling()


if __name__ == "__main__":
    main()
