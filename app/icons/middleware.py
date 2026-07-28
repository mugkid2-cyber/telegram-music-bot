from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message

from app.icons.message_log import log_message


class QuoteLoggingMiddleware(BaseMiddleware):
    """
    Пишет каждое сообщение группового чата в журнал (quotes_message_log).

    Если в проекте уже есть похожий middleware для журналирования
    сообщений (используется под учёт участников чата в app/bday) — лучше
    вызвать log_message() внутри него, а не подключать второй middleware.
    """

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if event.chat.type in ("group", "supergroup") and event.from_user is not None:
            try:
                await log_message(event)
            except Exception:
                # Логирование не должно ронять обработку сообщения
                pass
        return await handler(event, data)
