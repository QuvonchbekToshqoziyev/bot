from __future__ import annotations

import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from app.core.permissions import Permission, PermissionDenied
from app.core.router import CommandRouter
from app.core.skill_registry import SkillRegistry
from app.ai.orchestrator import AIOrchestrator
from app.storage.repositories import AIConfigurationRepository


def build_handlers(router: CommandRouter, registry: SkillRegistry, ai: AIOrchestrator | None = None, ai_configuration: AIConfigurationRepository | None = None):
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text("Telegram Workspace Manager is running. Use /help.")

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text("/skills\n/skill enable <name>\n/skill disable <name>\n/status\n/ask <task>\n/ai enable|disable|status")

    async def skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id, chat_id = update.effective_user.id, update.effective_chat.id
        lines = [f"{item['name']}: {'enabled' if item['enabled'] else 'disabled'}" for item in registry.metadata(user_id, chat_id)]
        await update.effective_message.reply_text("\n".join(lines) or "No skills registered.")

    async def skill_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id, chat_id = update.effective_user.id, update.effective_chat.id
        if len(context.args) != 2 or context.args[0] not in {"enable", "disable"}:
            await update.effective_message.reply_text("Usage: /skill enable|disable <name>")
            return
        try:
            await asyncio.to_thread((router.enable if context.args[0] == "enable" else router.disable), user_id, chat_id, context.args[1])
            await update.effective_message.reply_text(f"Skill {context.args[1]} {context.args[0]}d.")
        except (KeyError, PermissionDenied, PermissionError) as exc:
            await update.effective_message.reply_text(str(exc))

    async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        enabled = registry.enabled(update.effective_user.id, update.effective_chat.id)
        await update.effective_message.reply_text(f"Enabled skills: {', '.join(skill.name for skill in enabled) or 'none'}")

    async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if ai is None:
            await update.effective_message.reply_text("AI is not configured. Set OPENAI_API_KEY and install the ai extra.")
            return
        task = " ".join(context.args).strip()
        if ai_configuration is None or not ai_configuration.is_enabled(update.effective_chat.id):
            await update.effective_message.reply_text("AI is disabled. An administrator can use /ai enable.")
            return
        if not task:
            await update.effective_message.reply_text("Usage: /ask <task>")
            return
        result = await ai.handle_task(update.effective_user.id, update.effective_chat.id, task)
        await update.effective_message.reply_text(result.message)

    async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if ai is None or ai_configuration is None:
            await update.effective_message.reply_text("AI is not configured. Set OPENAI_API_KEY and install the ai extra.")
            return
        if len(context.args) != 1 or context.args[0] not in {"enable", "disable", "status"}:
            await update.effective_message.reply_text("Usage: /ai enable|disable|status")
            return
        try:
            router.registry.permissions.require_user(update.effective_user.id, update.effective_chat.id, frozenset({Permission.MANAGE_SKILLS}))
            if context.args[0] == "status":
                enabled = ai_configuration.is_enabled(update.effective_chat.id)
            else:
                enabled = context.args[0] == "enable"
                await asyncio.to_thread(ai_configuration.set_enabled, update.effective_chat.id, enabled)
            await update.effective_message.reply_text(f"AI {'enabled' if enabled else 'disabled'}.")
        except PermissionDenied as exc:
            await update.effective_message.reply_text(str(exc))

    return start, help_command, skills, skill_command, status, ask, ai_command
