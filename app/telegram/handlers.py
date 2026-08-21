from __future__ import annotations

import asyncio
import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler
from telegram.ext import ContextTypes

from app.core.permissions import Permission, PermissionDenied
from app.core.router import CommandRouter
from app.core.skill_registry import SkillRegistry
from app.core.local_tasks import LocalTaskRouter
from app.ai.orchestrator import AIOrchestrator
from app.storage.repositories import AIConfigurationRepository
from app.storage.repositories import SkillConfigurationRepository
from app.storage.repositories import ManagedChatRepository
from app.storage.repositories import MessageRepository


def build_handlers(router: CommandRouter, registry: SkillRegistry, ai: AIOrchestrator | None = None, ai_configuration: AIConfigurationRepository | None = None, configurations: SkillConfigurationRepository | None = None, managed_chats: ManagedChatRepository | None = None, messages: MessageRepository | None = None):
    local_tasks = LocalTaskRouter(registry)
    def menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Overview", callback_data="menu:overview"), InlineKeyboardButton("What can you do?", callback_data="menu:capabilities")],
            [InlineKeyboardButton("Skills", callback_data="menu:skills"), InlineKeyboardButton("Statistics", callback_data="menu:statistics")],
            [InlineKeyboardButton("Library", callback_data="menu:library"), InlineKeyboardButton("Manage chat", callback_data="menu:management")],
            [InlineKeyboardButton("AI settings", callback_data="menu:ai")],
        ])

    def skills_markup(user_id: int, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
        items = registry.metadata(user_id, chat_id)
        text = "Skills in this chat:\n" + "\n".join(f"• {item['name']}: {'enabled' if item['enabled'] else 'disabled'}" for item in items)
        buttons = [[InlineKeyboardButton(("Disable " if item["enabled"] else "Enable ") + item["name"], callback_data=f"skill:{'disable' if item['enabled'] else 'enable'}:{item['name']}" )] for item in items]
        buttons.append([InlineKeyboardButton("Back", callback_data="menu:back")])
        return text, InlineKeyboardMarkup(buttons)

    def management_markup(target: int | str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Chat info", callback_data="manage:info"), InlineKeyboardButton("Member count", callback_data="manage:members")],
            [InlineKeyboardButton("Administrators", callback_data="manage:admins")],
            [InlineKeyboardButton("Get messages", callback_data="manage:messages"), InlineKeyboardButton("Search", callback_data="manage:search")],
            [InlineKeyboardButton("Send message", callback_data="manage:send"), InlineKeyboardButton("Delete message", callback_data="manage:delete")],
            [InlineKeyboardButton("Pin message", callback_data="manage:pin")],
            [InlineKeyboardButton("Backup to chat", callback_data="manage:backup"), InlineKeyboardButton("Schedule post", callback_data="manage:schedule")],
            [InlineKeyboardButton("Scheduled posts", callback_data="manage:scheduled"), InlineKeyboardButton("Cancel scheduled", callback_data="manage:cancel_schedule")],
            [InlineKeyboardButton("Change target", callback_data="manage:target"), InlineKeyboardButton("Back", callback_data="menu:back")],
        ])

    def managed_chat_markup(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
        items = managed_chats.list(user_id) if managed_chats else []
        text = "Managed chats:\n" + ("\n".join(f"• {item['title'] or item['target_id']} ({item['target_id']})" for item in items) if items else "No chats connected yet.")
        buttons = [[InlineKeyboardButton(item["title"] or item["target_id"], callback_data=f"target:{item['target_id']}")] for item in items]
        buttons.append([InlineKeyboardButton("Add channel/group", callback_data="target:add")])
        buttons.append([InlineKeyboardButton("Back", callback_data="menu:back")])
        return text, InlineKeyboardMarkup(buttons)

    def parse_target(value: str) -> int | str:
        value = value.strip()
        if value.startswith("@") and len(value) > 1:
            return value
        if value.lstrip("-").isdigit():
            return int(value)
        raise ValueError("Send a numeric chat ID such as -1001234567890 or @channelusername.")

    async def ensure_help(user_id: int, chat_id: int) -> None:
        if configurations is not None:
            await asyncio.to_thread(configurations.set_enabled, user_id, chat_id, "help", True)

    async def ensure_skill(user_id: int, chat_id: int, name: str) -> bool:
        try:
            await asyncio.to_thread(router.enable, user_id, chat_id, name)
            return True
        except (PermissionDenied, PermissionError):
            return False

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
        task = " ".join(context.args).strip()
        if not task:
            await update.effective_message.reply_text("Usage: /ask <task>")
            return
        local = await local_tasks.handle(update.effective_user.id, update.effective_chat.id, task)
        if local.handled:
            await update.effective_message.reply_text(local.message, reply_markup=menu())
            return
        if ai is None:
            await update.effective_message.reply_text("No local skill matches that task. AI is not configured.", reply_markup=menu())
            return
        if ai_configuration is None or not ai_configuration.is_enabled(update.effective_chat.id):
            await update.effective_message.reply_text("No local skill matches that task. AI is disabled.", reply_markup=menu())
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
            context.user_data.pop("awaiting_task", None)
            context.user_data.pop("awaiting_management_target", None)
            context.user_data.pop("awaiting_management_action", None)
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
        elif action == "menu:overview":
            if not await ensure_skill(query.from_user.id, query.message.chat_id, "workspace"):
                await query.edit_message_text("Overview is not authorized in this chat.", reply_markup=menu())
                return
            result = await registry.execute(query.from_user.id, query.message.chat_id, "workspace", "get_overview", {})
            await query.edit_message_text(json.dumps(result, indent=2), reply_markup=menu())
        elif action == "menu:statistics":
            if not await ensure_skill(query.from_user.id, query.message.chat_id, "statistics"):
                await query.edit_message_text("Statistics is not authorized in this chat.", reply_markup=menu())
                return
            result = await registry.execute(query.from_user.id, query.message.chat_id, "statistics", "get_stats", {})
            await query.edit_message_text(json.dumps(result, indent=2), reply_markup=menu())
        elif action == "menu:library":
            if not await ensure_skill(query.from_user.id, query.message.chat_id, "library"):
                await query.edit_message_text("Library is not authorized in this chat.", reply_markup=menu())
                return
            result = await registry.execute(query.from_user.id, query.message.chat_id, "library", "list_indexed_messages", {})
            await query.edit_message_text(json.dumps(result, indent=2)[:3900], reply_markup=menu())
        elif action == "menu:management":
            try:
                await asyncio.to_thread(router.enable, query.from_user.id, query.message.chat_id, "management")
            except (PermissionDenied, PermissionError) as exc:
                await query.edit_message_text(f"Management is not authorized in this chat: {exc}", reply_markup=menu())
                return
            target = context.user_data.get("management_target")
            if target is None:
                context.user_data["awaiting_management_target"] = True
                text, markup = managed_chat_markup(query.from_user.id)
                await query.edit_message_text(text + "\n\nSend a new target ID or tap Add channel/group.", reply_markup=markup)
            else:
                await query.edit_message_text(f"Managing target: {target}", reply_markup=management_markup(target))
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
        elif action == "ai:run":
            task = context.user_data.pop("pending_task", None)
            if not task or ai is None or ai_configuration is None or not ai_configuration.is_enabled(query.message.chat_id):
                await query.edit_message_text("AI is disabled or there is no pending task.", reply_markup=menu())
                return
            result = await ai.handle_task(query.from_user.id, query.message.chat_id, task)
            await query.edit_message_text(result.message, reply_markup=menu())
        elif action.startswith("skill:"):
            _, operation, skill_name = action.split(":", 2)
            try:
                await asyncio.to_thread((router.enable if operation == "enable" else router.disable), query.from_user.id, query.message.chat_id, skill_name)
                text, markup = skills_markup(query.from_user.id, query.message.chat_id)
                await query.edit_message_text(text, reply_markup=markup)
            except (KeyError, PermissionDenied, PermissionError) as exc:
                await query.edit_message_text(str(exc), reply_markup=menu())
        elif action == "manage:target":
            context.user_data.pop("management_target", None)
            text, markup = managed_chat_markup(query.from_user.id)
            await query.edit_message_text(text, reply_markup=markup)
        elif action == "target:add":
            context.user_data["awaiting_management_target"] = True
            await query.edit_message_text("Send the target channel/group ID or public @username.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="menu:management")]]))
        elif action.startswith("target:"):
            target = parse_target(action.removeprefix("target:"))
            context.user_data["management_target"] = target
            if managed_chats:
                await asyncio.to_thread(managed_chats.add, query.from_user.id, target)
            await query.edit_message_text(f"Managing target: {target}", reply_markup=management_markup(target))
        elif action.startswith("manage:"):
            target = context.user_data.get("management_target")
            if target is None:
                context.user_data["awaiting_management_target"] = True
                await query.edit_message_text("Send the target channel/group ID or public @username.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="menu:back")]]))
                return
            operation = action.removeprefix("manage:")
            skill_for_operation = {"messages": "messages", "search": "search", "backup": "backup", "schedule": "scheduler", "scheduled": "scheduler", "cancel_schedule": "scheduler"}.get(operation)
            if skill_for_operation and not await ensure_skill(query.from_user.id, query.message.chat_id, skill_for_operation):
                await query.edit_message_text(f"{skill_for_operation} is not authorized in this chat.", reply_markup=management_markup(target))
                return
            if operation == "scheduled":
                result = await registry.execute(query.from_user.id, query.message.chat_id, "scheduler", "list_scheduled_posts", {"target_id": str(target)})
                await query.edit_message_text(json.dumps(result, indent=2, default=str)[:3900], reply_markup=management_markup(target))
                return
            if operation in {"send", "delete", "pin", "search", "backup", "schedule", "cancel_schedule"}:
                context.user_data["awaiting_management_action"] = operation
                prompt = {"send": "Send the message text.", "delete": "Send the message ID to delete.", "pin": "Send the message ID to pin.", "search": "Send the search text.", "backup": "Send the destination chat ID, for example -1001234567890.", "schedule": "Send: delay_seconds | post text. Example: 3600 | Good morning", "cancel_schedule": "Send the scheduled post ID."}[operation]
                await query.edit_message_text(f"Target: {target}\n{prompt}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="menu:management")]]))
                return
            tool_name = {"info": "get_chat_info", "members": "get_member_count", "admins": "list_administrators"}.get(operation)
            if operation == "messages":
                result = await registry.execute(query.from_user.id, query.message.chat_id, "messages", "list_messages", {"target_id": str(target)})
                await query.edit_message_text(json.dumps(result, indent=2, default=str)[:3900], reply_markup=management_markup(target))
                return
            if tool_name is None:
                return
            try:
                result = await registry.execute(query.from_user.id, query.message.chat_id, "management", tool_name, {"chat_id": target})
                await query.edit_message_text(json.dumps(result, indent=2, default=str)[:3900], reply_markup=management_markup(target))
            except (PermissionDenied, PermissionError, ValueError, TelegramError) as exc:
                await query.edit_message_text(f"Management failed: {exc}", reply_markup=management_markup(target))

    async def turn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await ensure_help(update.effective_user.id, update.effective_chat.id)
        if context.user_data.get("awaiting_management_target"):
            context.user_data.pop("awaiting_management_target")
            try:
                target = parse_target(update.effective_message.text)
                context.user_data["management_target"] = target
                if managed_chats:
                    await asyncio.to_thread(managed_chats.add, update.effective_user.id, target)
                await update.effective_message.reply_text(f"Managing target: {target}", reply_markup=management_markup(target))
            except ValueError as exc:
                await update.effective_message.reply_text(str(exc))
            return
        management_action = context.user_data.pop("awaiting_management_action", None)
        if management_action:
            target = context.user_data.get("management_target")
            try:
                if target is None:
                    raise ValueError("Choose a management target first.")
                if management_action == "send":
                    result = await registry.execute(update.effective_user.id, update.effective_chat.id, "management", "send_message", {"chat_id": target, "text": update.effective_message.text})
                elif management_action in {"delete", "pin"}:
                    message_id = int(update.effective_message.text.strip())
                    tool_name = "delete_message" if management_action == "delete" else "pin_message"
                    result = await registry.execute(update.effective_user.id, update.effective_chat.id, "management", tool_name, {"chat_id": target, "message_id": message_id})
                elif management_action == "search":
                    result = await registry.execute(update.effective_user.id, update.effective_chat.id, "search", "search_messages", {"target_id": str(target), "query": update.effective_message.text})
                elif management_action == "backup":
                    destination = parse_target(update.effective_message.text)
                    result = await registry.execute(update.effective_user.id, update.effective_chat.id, "backup", "copy_messages", {"source_id": str(target), "destination_id": str(destination), "limit": 20})
                elif management_action == "cancel_schedule":
                    result = await registry.execute(update.effective_user.id, update.effective_chat.id, "scheduler", "cancel_scheduled_post", {"id": int(update.effective_message.text.strip())})
                else:
                    delay_text, separator, post_text = update.effective_message.text.partition("|")
                    if not separator:
                        raise ValueError("Use: delay_seconds | post text")
                    result = await registry.execute(update.effective_user.id, update.effective_chat.id, "scheduler", "schedule_post", {"target_id": str(target), "text": post_text.strip(), "delay_seconds": int(delay_text.strip())})
                await update.effective_message.reply_text(json.dumps(result, indent=2, default=str)[:3900], reply_markup=management_markup(target))
            except (ValueError, PermissionDenied, PermissionError, TelegramError) as exc:
                await update.effective_message.reply_text(f"Management failed: {exc}", reply_markup=management_markup(target) if target is not None else menu())
            return
        if not context.user_data.pop("awaiting_task", False):
            if update.effective_chat.type == "private":
                result = await registry.execute(update.effective_user.id, update.effective_chat.id, "help", "answer_question", {"question": update.effective_message.text})
                await update.effective_message.reply_text(result["answer"], reply_markup=menu())
            return
        local = await local_tasks.handle(update.effective_user.id, update.effective_chat.id, update.effective_message.text)
        if local.handled:
            await update.effective_message.reply_text(local.message, reply_markup=menu())
            return
        context.user_data["pending_task"] = update.effective_message.text
        buttons = [[InlineKeyboardButton("Use AI for this task", callback_data="ai:run")], [InlineKeyboardButton("Back", callback_data="menu:back")]]
        await update.effective_message.reply_text("No local skill matches that task.", reply_markup=InlineKeyboardMarkup(buttons))

    async def index_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if messages is None or managed_chats is None:
            return
        message = update.channel_post or update.message
        if message is None or not message.text:
            return
        owners = await asyncio.to_thread(managed_chats.owners_for, message.chat.id)
        sender_id = message.from_user.id if message.from_user else None
        for owner_id in owners:
            await asyncio.to_thread(messages.add, owner_id, message.chat.id, message.message_id, message.text, sender_id)

    return start, help_command, skills, skill_command, status, ask, ai_command, callback, turn, index_update
