from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() and not key.strip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    database_url: str
    admin_user_ids: frozenset[int]
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-5"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        ids = frozenset(int(value.strip()) for value in os.getenv("ADMIN_USER_IDS", "").split(",") if value.strip())
        if not ids:
            raise ValueError("ADMIN_USER_IDS must contain at least one numeric Telegram user ID")
        router_key = os.getenv("OPENROUTER_API_KEY") or None
        return cls(token, os.getenv("DATABASE_URL", "sqlite:///workspace.db"), ids, os.getenv("OPENAI_API_KEY") or router_key, os.getenv("OPENAI_BASE_URL") or ("https://openrouter.ai/api/v1" if router_key else None), os.getenv("OPENAI_MODEL", "gpt-5"), os.getenv("LOG_LEVEL", "INFO"))
