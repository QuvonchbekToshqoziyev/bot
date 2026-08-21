# Telegram Workspace Manager

Small, async Telegram bot foundation built around independently enableable skills.

## Run locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev,ai]'
cp .env.example .env  # edit the token and administrator IDs
python -m app.telegram.bot
```

Run tests with `pytest`.

With `OPENAI_API_KEY` configured, an administrator can use `/ai enable|disable|status`, then send tasks through `/ask <task>`. The AI only sees enabled skills, reports `not_found` when no skill matches, and executes selected tools through the same permission boundary as normal application calls.

The `management` skill provides chat info, member counts, administrator listing, sending, deleting, and pinning. Add the bot as an administrator in each target group/channel and grant the Telegram rights required by the operation. The requesting user must also be authorized for that target chat in the database.

Connected target chats are stored in SQLite and can be switched from the Manage chat menu. The menu also provides indexed message listing/search, indexed-message backup to another chat, and scheduled text posts. Indexing starts when the bot receives messages after a target is connected; Telegram bots cannot download arbitrary historical chat history.

The Telegram dependency is limited to the adapter. Core, storage, and skills are usable and testable without Telegram credentials.
