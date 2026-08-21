from __future__ import annotations

import asyncio
import time
from typing import Any

from app.storage.repositories import ScheduledPostRepository


async def run_scheduler(repository: ScheduledPostRepository, sender: Any) -> None:
    while True:
        for post in await asyncio.to_thread(repository.due, int(time.time())):
            try:
                await sender.send_message(post["target_id"], post["text"])
            except Exception:
                repository.mark(post["id"], "failed")
            else:
                repository.mark(post["id"], "sent")
        await asyncio.sleep(1)
