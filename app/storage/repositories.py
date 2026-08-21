from __future__ import annotations

import json
from typing import Any

from app.core.models import Chat, User
from app.core.permissions import Permission
from app.storage.database import Database


class WorkspaceRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def upsert_user(self, user: User) -> None:
        with self.db.lock:
            self.db.connection.execute("INSERT INTO users VALUES (?, ?) ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username", (user.telegram_id, user.username))
            self.db.connection.commit()

    def upsert_chat(self, chat: Chat) -> None:
        with self.db.lock:
            self.db.connection.execute("INSERT INTO chats VALUES (?, ?) ON CONFLICT(telegram_id) DO UPDATE SET title=excluded.title", (chat.telegram_id, chat.title))
            self.db.connection.commit()


class AuthorizationRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def grant_role(self, user_id: int, chat_id: int, role: str) -> None:
        if role not in {"owner", "admin", "member"}:
            raise ValueError("Invalid chat role")
        with self.db.lock:
            self.db.connection.execute("INSERT OR IGNORE INTO users(telegram_id) VALUES (?)", (user_id,))
            self.db.connection.execute("INSERT OR IGNORE INTO chats(telegram_id) VALUES (?)", (chat_id,))
            self.db.connection.execute("INSERT INTO chat_members VALUES (?, ?, ?) ON CONFLICT(user_id, chat_id) DO UPDATE SET role=excluded.role", (user_id, chat_id, role))
            self.db.connection.commit()

    def permissions_for(self, user_id: int, chat_id: int) -> frozenset[Permission]:
        with self.db.lock:
            row = self.db.connection.execute("SELECT role FROM chat_members WHERE user_id=? AND chat_id=?", (user_id, chat_id)).fetchone()
        if not row:
            return frozenset()
        if row[0] in {"owner", "admin"}:
            return frozenset(Permission)
        return frozenset({Permission.READ_MESSAGES, Permission.READ_LIBRARY})

class SkillConfigurationRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def set_enabled(self, user_id: int, chat_id: int, skill_name: str, enabled: bool, config: dict[str, Any] | None = None) -> None:
        with self.db.lock:
            self.db.connection.execute("INSERT OR IGNORE INTO users(telegram_id) VALUES (?)", (user_id,))
            self.db.connection.execute("INSERT OR IGNORE INTO chats(telegram_id) VALUES (?)", (chat_id,))
            if config is None:
                existing = self.db.connection.execute("SELECT config_json FROM skill_configurations WHERE user_id=? AND chat_id=? AND skill_name=?", (user_id, chat_id, skill_name)).fetchone()
                config_json = existing[0] if existing else "{}"
            else:
                config_json = json.dumps(config)
            self.db.connection.execute("INSERT INTO skill_configurations VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id, chat_id, skill_name) DO UPDATE SET enabled=excluded.enabled, config_json=excluded.config_json", (user_id, chat_id, skill_name, int(enabled), config_json))
            self.db.connection.commit()

    def is_enabled_for_chat(self, chat_id: int, skill_name: str) -> bool:
        with self.db.lock:
            row = self.db.connection.execute("SELECT enabled FROM skill_configurations WHERE chat_id=? AND skill_name=? AND enabled=1 LIMIT 1", (chat_id, skill_name)).fetchone()
        return bool(row and row[0])

    def disable_for_chat(self, chat_id: int, skill_name: str) -> None:
        with self.db.lock:
            self.db.connection.execute("UPDATE skill_configurations SET enabled=0 WHERE chat_id=? AND skill_name=?", (chat_id, skill_name))
            self.db.connection.commit()

    def enabled_configurations(self) -> list[tuple[int, int, str]]:
        with self.db.lock:
            rows = self.db.connection.execute("SELECT user_id, chat_id, skill_name FROM skill_configurations WHERE enabled=1").fetchall()
        return [(row[0], row[1], row[2]) for row in rows]


class AIConfigurationRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def set_enabled(self, chat_id: int, enabled: bool) -> None:
        with self.db.lock:
            self.db.connection.execute("INSERT OR IGNORE INTO chats(telegram_id) VALUES (?)", (chat_id,))
            self.db.connection.execute("INSERT INTO ai_configurations VALUES (?, ?) ON CONFLICT(chat_id) DO UPDATE SET enabled=excluded.enabled", (chat_id, int(enabled)))
            self.db.connection.commit()

    def is_enabled(self, chat_id: int) -> bool:
        with self.db.lock:
            row = self.db.connection.execute("SELECT enabled FROM ai_configurations WHERE chat_id=?", (chat_id,)).fetchone()
        return bool(row and row[0])


class ManagedChatRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def add(self, user_id: int, target_id: int | str, title: str | None = None, chat_type: str | None = None) -> None:
        with self.db.lock:
            self.db.connection.execute("INSERT OR IGNORE INTO users(telegram_id) VALUES (?)", (user_id,))
            self.db.connection.execute("INSERT INTO managed_chats(user_id, target_id, title, chat_type) VALUES (?, ?, ?, ?) ON CONFLICT(user_id, target_id) DO UPDATE SET title=COALESCE(excluded.title, managed_chats.title), chat_type=COALESCE(excluded.chat_type, managed_chats.chat_type)", (user_id, str(target_id), title, chat_type))
            self.db.connection.commit()

    def remove(self, user_id: int, target_id: int | str) -> None:
        with self.db.lock:
            self.db.connection.execute("DELETE FROM managed_chats WHERE user_id=? AND target_id=?", (user_id, str(target_id)))
            self.db.connection.commit()

    def list(self, user_id: int) -> list[dict[str, Any]]:
        with self.db.lock:
            rows = self.db.connection.execute("SELECT target_id, title, chat_type, added_at FROM managed_chats WHERE user_id=? ORDER BY added_at, target_id", (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def owners_for(self, target_id: int | str) -> list[int]:
        with self.db.lock:
            rows = self.db.connection.execute("SELECT user_id FROM managed_chats WHERE target_id=?", (str(target_id),)).fetchall()
        return [row[0] for row in rows]


class ModerationRepository:
    defaults = {
        "enabled": False,
        "link_filter": False,
        "keyword_filter": False,
        "keywords": [],
        "welcome": False,
        "farewell": False,
        "welcome_text": "Welcome, {name}!",
        "farewell_text": "{name} left the chat.",
        "rules": "",
    }

    def __init__(self, database: Database) -> None:
        self.db = database

    def get(self, user_id: int, target_id: int | str) -> dict[str, Any]:
        with self.db.lock:
            row = self.db.connection.execute("SELECT config_json FROM moderation_settings WHERE user_id=? AND target_id=?", (user_id, str(target_id))).fetchone()
        config = dict(self.defaults)
        if row:
            config.update(json.loads(row[0]))
        return config

    def update(self, user_id: int, target_id: int | str, values: dict[str, Any]) -> dict[str, Any]:
        config = self.get(user_id, target_id)
        config.update(values)
        with self.db.lock:
            self.db.connection.execute("INSERT OR IGNORE INTO users(telegram_id) VALUES (?)", (user_id,))
            self.db.connection.execute("INSERT INTO moderation_settings(user_id, target_id, config_json) VALUES (?, ?, ?) ON CONFLICT(user_id, target_id) DO UPDATE SET config_json=excluded.config_json", (user_id, str(target_id), json.dumps(config)))
            self.db.connection.commit()
        return config


class MessageRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def add(self, owner_id: int, target_id: int | str, message_id: int, text: str, sender_id: int | None = None) -> None:
        with self.db.lock:
            self.db.connection.execute("INSERT OR IGNORE INTO users(telegram_id) VALUES (?)", (owner_id,))
            self.db.connection.execute("INSERT OR IGNORE INTO managed_messages(owner_id, target_id, message_id, sender_id, text) VALUES (?, ?, ?, ?, ?)", (owner_id, str(target_id), message_id, sender_id, text))
            self.db.connection.commit()

    def list(self, owner_id: int, target_id: int | str, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.lock:
            rows = self.db.connection.execute("SELECT message_id, sender_id, text, created_at FROM managed_messages WHERE owner_id=? AND target_id=? ORDER BY created_at DESC LIMIT ?", (owner_id, str(target_id), limit)).fetchall()
        return [dict(row) for row in rows]

    def search(self, owner_id: int, target_id: int | str, query: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.lock:
            rows = self.db.connection.execute("SELECT message_id, sender_id, text, created_at FROM managed_messages WHERE owner_id=? AND target_id=? AND text LIKE ? ORDER BY created_at DESC LIMIT ?", (owner_id, str(target_id), f"%{query}%", limit)).fetchall()
        return [dict(row) for row in rows]


class ScheduledPostRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def create(self, user_id: int, target_id: int | str, text: str, run_at: int) -> int:
        with self.db.lock:
            self.db.connection.execute("INSERT OR IGNORE INTO users(telegram_id) VALUES (?)", (user_id,))
            cursor = self.db.connection.execute("INSERT INTO scheduled_posts(user_id, target_id, text, run_at) VALUES (?, ?, ?, ?)", (user_id, str(target_id), text, run_at))
            self.db.connection.commit()
        return int(cursor.lastrowid)

    def list(self, user_id: int, target_id: int | str | None = None) -> list[dict[str, Any]]:
        with self.db.lock:
            if target_id is None:
                rows = self.db.connection.execute("SELECT id, target_id, text, run_at, status FROM scheduled_posts WHERE user_id=? ORDER BY run_at", (user_id,)).fetchall()
            else:
                rows = self.db.connection.execute("SELECT id, target_id, text, run_at, status FROM scheduled_posts WHERE user_id=? AND target_id=? ORDER BY run_at", (user_id, str(target_id))).fetchall()
        return [dict(row) for row in rows]

    def due(self, now: int) -> list[dict[str, Any]]:
        with self.db.lock:
            rows = self.db.connection.execute("SELECT id, user_id, target_id, text FROM scheduled_posts WHERE status='pending' AND run_at<=? ORDER BY run_at", (now,)).fetchall()
            for row in rows:
                self.db.connection.execute("UPDATE scheduled_posts SET status='sending' WHERE id=?", (row[0],))
            self.db.connection.commit()
        return [dict(row) for row in rows]

    def mark(self, post_id: int, status: str, user_id: int | None = None) -> None:
        with self.db.lock:
            if user_id is None:
                self.db.connection.execute("UPDATE scheduled_posts SET status=? WHERE id=?", (status, post_id))
            else:
                self.db.connection.execute("UPDATE scheduled_posts SET status=? WHERE id=? AND user_id=?", (status, post_id, user_id))
            self.db.connection.commit()


class LibraryRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def list_messages(self, user_id: int, chat_id: int) -> list[dict[str, Any]]:
        with self.db.lock:
            rows = self.db.connection.execute("SELECT telegram_message_id, text FROM indexed_messages WHERE user_id=? AND chat_id=? ORDER BY id", (user_id, chat_id)).fetchall()
        return [dict(row) for row in rows]

    def add_message(self, user_id: int, chat_id: int, message_id: int, text: str) -> None:
        with self.db.lock:
            self.db.connection.execute("INSERT OR IGNORE INTO users(telegram_id) VALUES (?)", (user_id,))
            self.db.connection.execute("INSERT OR IGNORE INTO chats(telegram_id) VALUES (?)", (chat_id,))
            self.db.connection.execute("INSERT OR IGNORE INTO indexed_messages(user_id, chat_id, telegram_message_id, text) VALUES (?, ?, ?, ?)", (user_id, chat_id, message_id, text))
            self.db.connection.commit()
