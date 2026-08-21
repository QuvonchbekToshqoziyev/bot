from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class User:
    telegram_id: int
    username: str | None = None


@dataclass(frozen=True, slots=True)
class Chat:
    telegram_id: int
    title: str | None = None

