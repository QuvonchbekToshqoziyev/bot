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

With `OPENAI_API_KEY` configured, send tasks through `/ask <task>`. The AI only sees enabled skills, reports `not_found` when no skill matches, and executes selected tools through the same permission boundary as normal application calls.

The Telegram dependency is limited to the adapter. Core, storage, and skills are usable and testable without Telegram credentials.
