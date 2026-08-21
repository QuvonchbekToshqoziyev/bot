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
