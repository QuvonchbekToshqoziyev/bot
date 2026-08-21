from __future__ import annotations

import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler
from telegram.ext import ContextTypes

from app.core.permissions import Permission, PermissionDenied
from app.core.router import CommandRouter
from app.core.skill_registry import SkillRegistry
from app.ai.orchestrator import AIOrchestrator
from app.storage.repositories import AIConfigurationRepository
from app.storage.repositories import SkillConfigurationRepository


def build_handlers(router: CommandRouter, registry: SkillRegistry, ai: AIOrchestrator | None = None, ai_configuration: AIConfigurationRepository | None = None, configurations: SkillConfigurationRepository | None = None):
    def menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("What can you do?", callback_data="menu:capabilities"), InlineKeyboardButton("Skills", callback_data="menu:skills")],
            [InlineKeyboardButton("Ask a question/task", callback_data="menu:ask"), InlineKeyboardButton("Manage chat", callback_data="menu:management")],
            [InlineKeyboardButton("AI settings", callback_data="menu:ai")],
        ])

    def skills_markup(user_id: int, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
        items = registry.metadata(user_id, chat_id)
        text = "Skills in this chat:\n" + "\n".join(f"• {item['name']}: {'enabled' if item['enabled'] else 'disabled'}" for item in items)
        buttons = [[InlineKeyboardButton(("Disable " if item["enabled"] else "Enable ") + item["name"], callback_data=f"skill:{'disable' if item['enabled'] else 'enable'}:{item['name']}" )] for item in items]
        buttons.append([InlineKeyboardButton("Back", callback_data="menu:back")])
        return text, InlineKeyboardMarkup(buttons)

    async def ensure_help(user_id: int, chat_id: int) -> None:
        if configurations is not None:
            await asyncio.to_thread(configurations.set_enabled, user_id, chat_id, "help", True)

    async def menu_text(update: Update, text: str) -> None:
        await update.effective_message.reply_text(text, reply_markup=menu())

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await ensure_help(update.effective_user.id, update.effective_chat.id)
        await menu_text(update, "Telegram Workspace Manager\nChoose an option:")

    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await ensure_help(update.effective_user.id, update.effective_chat.id)
        await menu_text(update, "Choose an option:")

    async def skills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id, chat_id = update.effective_user.id, update.effective_chat.id
        text, markup = skills_markup(user_id, chat_id)
        await update.effective_message.reply_text(text, reply_markup=markup)

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

    async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        await ensure_help(query.from_user.id, query.message.chat_id)
        action = query.data or "menu:back"
        if action == "menu:back":
            await query.edit_message_text("Choose an option:", reply_markup=menu())
        elif action == "menu:capabilities":
            result = await registry.execute(query.from_user.id, query.message.chat_id, "help", "answer_question", {"question": "What can you do?"})
            await query.edit_message_text(result["answer"], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="menu:back")]]))
        elif action == "menu:skills":
            text, markup = skills_markup(query.from_user.id, query.message.chat_id)
            await query.edit_message_text(text, reply_markup=markup)
        elif action == "menu:ask":
            context.user_data["awaiting_task"] = True
            await query.edit_message_text("Send your question or task as the next message.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="menu:back")]]))
        elif action == "menu:management":
            await query.edit_message_text("I can inspect chats, list administrators, send, delete, and pin messages. Add me as a Telegram administrator in the target group or channel, then choose Ask a question/task and describe what you want.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Ask a task", callback_data="menu:ask"), InlineKeyboardButton("Back", callback_data="menu:back")]]))
        elif action == "menu:ai":
            enabled = ai is not None and ai_configuration is not None and ai_configuration.is_enabled(query.message.chat_id)
            await query.edit_message_text(f"AI is {'enabled' if enabled else 'disabled'}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Enable", callback_data="ai:enable"), InlineKeyboardButton("Disable", callback_data="ai:disable")], [InlineKeyboardButton("Back", callback_data="menu:back")]]))
        elif action in {"ai:enable", "ai:disable"}:
            if ai is None or ai_configuration is None:
                await query.edit_message_text("AI is not configured on this server.", reply_markup=menu())
                return
            try:
                router.registry.permissions.require_user(query.from_user.id, query.message.chat_id, frozenset({Permission.MANAGE_SKILLS}))
                enabled = action == "ai:enable"
                await asyncio.to_thread(ai_configuration.set_enabled, query.message.chat_id, enabled)
                await query.edit_message_text(f"AI {'enabled' if enabled else 'disabled'}.", reply_markup=menu())
            except PermissionDenied as exc:
                await query.edit_message_text(str(exc), reply_markup=menu())
        elif action.startswith("skill:"):
            _, operation, skill_name = action.split(":", 2)
            try:
                await asyncio.to_thread((router.enable if operation == "enable" else router.disable), query.from_user.id, query.message.chat_id, skill_name)
                text, markup = skills_markup(query.from_user.id, query.message.chat_id)
                await query.edit_message_text(text, reply_markup=markup)
            except (KeyError, PermissionDenied, PermissionError) as exc:
                await query.edit_message_text(str(exc), reply_markup=menu())

    async def turn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await ensure_help(update.effective_user.id, update.effective_chat.id)
        if not context.user_data.pop("awaiting_task", False):
            if update.effective_chat.type == "private":
                result = await registry.execute(update.effective_user.id, update.effective_chat.id, "help", "answer_question", {"question": update.effective_message.text})
                await update.effective_message.reply_text(result["answer"], reply_markup=menu())
            return
        if ai is None or ai_configuration is None or not ai_configuration.is_enabled(update.effective_chat.id):
            await update.effective_message.reply_text("AI is disabled. Use the AI settings button first.", reply_markup=menu())
            return
        result = await ai.handle_task(update.effective_user.id, update.effective_chat.id, update.effective_message.text)
        await update.effective_message.reply_text(result.message, reply_markup=menu())

    return start, help_command, skills, skill_command, status, ask, ai_command, callback, turn
