from __future__ import annotations

import sqlite3
from threading import RLock
from pathlib import Path


class Database:
    def __init__(self, url: str) -> None:
        if not url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// URLs are supported")
        path = Path(url.removeprefix("sqlite:///"))
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.lock = RLock()
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    def migrate(self) -> None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, username TEXT);
        CREATE TABLE IF NOT EXISTS chats (telegram_id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE IF NOT EXISTS chat_members (
            user_id INTEGER NOT NULL REFERENCES users(telegram_id),
            chat_id INTEGER NOT NULL REFERENCES chats(telegram_id),
            role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
            PRIMARY KEY (user_id, chat_id)
        );
        CREATE TABLE IF NOT EXISTS ai_configurations (
            chat_id INTEGER PRIMARY KEY REFERENCES chats(telegram_id),
            enabled INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS managed_chats (
            user_id INTEGER NOT NULL REFERENCES users(telegram_id),
            target_id TEXT NOT NULL,
            title TEXT,
            chat_type TEXT,
            added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, target_id)
        );
        CREATE TABLE IF NOT EXISTS skill_configurations (
            user_id INTEGER NOT NULL REFERENCES users(telegram_id),
            chat_id INTEGER NOT NULL REFERENCES chats(telegram_id),
            skill_name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            config_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (user_id, chat_id, skill_name)
        );
        CREATE TABLE IF NOT EXISTS indexed_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(telegram_id),
            chat_id INTEGER NOT NULL REFERENCES chats(telegram_id),
            telegram_message_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            UNIQUE (chat_id, telegram_message_id)
        );
        CREATE TABLE IF NOT EXISTS managed_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL REFERENCES users(telegram_id),
            target_id TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            sender_id INTEGER,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (owner_id, target_id, message_id)
        );
        CREATE TABLE IF NOT EXISTS scheduled_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(telegram_id),
            target_id TEXT NOT NULL,
            text TEXT NOT NULL,
            run_at INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS moderation_settings (
            user_id INTEGER NOT NULL REFERENCES users(telegram_id),
            target_id TEXT NOT NULL,
            config_json TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY (user_id, target_id)
        );
        """)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
