import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Message, TelegramObject

from app.triggers.birthdays.chat_members_service import ChatMembersService

logger = logging.getLogger(__name__)


class ChatMemberTrackingMiddleware(BaseMiddleware):
    """Молча запоминает, кто пишет в группе — это единственный способ
    впоследствии компактно упомянуть "всех" в поздравлении с днём
    рождения, так как Bot API не отдаёт список участников напрямую.
    Ошибки трекинга не должны ронять обработку самого сообщения.
    """

    def __init__(self, members_service: ChatMembersService) -> None:
        self._members_service = members_service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if (
            isinstance(event, Message)
            and event.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}
            and event.from_user is not None
        ):
            user = event.from_user
            try:
                await self._members_service.track(
                    chat_id=event.chat.id,
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name or "",
                    is_bot=user.is_bot,
                )
            except Exception:
                logger.exception("Failed to track chat member %s in chat %s", user.id, event.chat.id)

        return await handler(event, data)