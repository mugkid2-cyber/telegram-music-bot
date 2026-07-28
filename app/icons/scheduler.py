from __future__ import annotations

import logging
import random

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.icons.db import get_connection

logger = logging.getLogger(__name__)

# Во сколько (по времени сервера) слать "цитату дня" в каждый чат.
DAILY_HOUR = 12
DAILY_MINUTE = 0


async def send_daily_quote(bot: Bot) -> None:
    async with get_connection() as db:
        cursor = await db.execute("SELECT DISTINCT chat_id FROM quotes")
        chat_rows = await cursor.fetchall()

    for chat_row in chat_rows:
        chat_id = chat_row["chat_id"]

        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT sticker_file_id FROM quotes WHERE chat_id = ?", (chat_id,)
            )
            sticker_rows = await cursor.fetchall()

        if not sticker_rows:
            continue

        sticker_file_id = random.choice(sticker_rows)["sticker_file_id"]
        try:
            await bot.send_sticker(chat_id, sticker_file_id)
        except TelegramForbiddenError:
            logger.info("бот удалён из чата %s, пропускаю ежедневную цитату", chat_id)
        except Exception:
            logger.exception("не удалось отправить цитату дня в чат %s", chat_id)


def setup_quote_scheduler(scheduler: AsyncIOScheduler, bot: Bot) -> None:
    """Вызвать один раз при старте бота, передав общий APScheduler-инстанс проекта."""
    scheduler.add_job(
        send_daily_quote,
        trigger=CronTrigger(hour=DAILY_HOUR, minute=DAILY_MINUTE),
        kwargs={"bot": bot},
        id="quotes_daily_random",
        replace_existing=True,
    )
