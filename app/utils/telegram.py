import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError

from app.config import Settings

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    session_kwargs: dict = {
        "timeout": settings.TELEGRAM_REQUEST_TIMEOUT,
    }
    if settings.BOT_PROXY:
        session_kwargs["proxy"] = settings.BOT_PROXY
        logger.info("Telegram API: используется прокси")

    session = AiohttpSession(**session_kwargs)
    return Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def verify_telegram_connection(
    bot: Bot,
    retries: int,
    delay: float,
) -> None:
    for attempt in range(1, retries + 1):
        try:
            me = await bot.get_me()
            logger.info("Бот @%s подключен", me.username)
            return
        except TelegramNetworkError as exc:
            if attempt >= retries:
                logger.error("Не удалось подключиться к Telegram API")
                raise
            await asyncio.sleep(delay)
