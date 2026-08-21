from __future__ import annotations

from typing import Any

from telegram import Bot


def _dict(value: Any) -> dict[str, Any]:
    return value.to_dict() if hasattr(value, "to_dict") else value


class TelegramManagementAdapter:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._bot_id: int | None = None

    async def _require_admin(self, chat_id: int) -> None:
        if self._bot_id is None:
            self._bot_id = (await self.bot.get_me()).id
        member = await self.bot.get_chat_member(chat_id, self._bot_id)
        if getattr(member, "status", None) not in {"administrator", "creator"}:
            raise PermissionError("Bot must be an administrator in the target chat")

    async def get_chat(self, chat_id: int) -> dict[str, Any]:
        await self._require_admin(chat_id)
        return _dict(await self.bot.get_chat(chat_id))

    async def get_member_count(self, chat_id: int) -> int:
        await self._require_admin(chat_id)
        return await self.bot.get_chat_member_count(chat_id)

    async def list_administrators(self, chat_id: int) -> list[dict[str, Any]]:
        await self._require_admin(chat_id)
        return [_dict(member) for member in await self.bot.get_chat_administrators(chat_id)]

    async def send_message(self, chat_id: int, text: str) -> dict[str, Any]:
        await self._require_admin(chat_id)
        return _dict(await self.bot.send_message(chat_id, text))

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        await self._require_admin(chat_id)
        return await self.bot.delete_message(chat_id, message_id)

    async def pin_message(self, chat_id: int, message_id: int, disable_notification: bool) -> bool:
        await self._require_admin(chat_id)
        return await self.bot.pin_chat_message(chat_id, message_id, disable_notification=disable_notification)
