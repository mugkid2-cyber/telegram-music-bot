from __future__ import annotations

import datetime as dt
import hashlib

from aiogram.types import Message

from app.icons.db import get_connection
from app.icons.models import MessageLog

MAX_WINDOW = 10  # ограничение на N в /qt N, чтобы карточка не превращалась в простыню


def _stable_id_from_name(name: str) -> int:
    """
    Детерминированный псевдо-user_id для форвардов, где Telegram скрывает
    настоящего отправителя и отдаёт только имя (скрытая приватность
    пересылки) или это канал/чат без привязанного пользователя. Нужен,
    чтобы у одного и того же "автора" был стабильный цвет/аватар-заглушка
    между разными /qt, а не случайный каждый раз.
    """
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _forward_author(message: Message) -> tuple[int, str, str | None, bool] | None:
    """
    Если сообщение переслано — возвращает (user_id, full_name, username, is_bot)
    ОРИГИНАЛЬНОГО автора, а не того, кто нажал "переслать". Возвращает
    None для обычных (не пересланных) сообщений — тогда в log_message
    используется message.from_user как раньше.

    Поддержаны оба варианта API:
    - актуальный `forward_origin` (MessageOriginUser/HiddenUser/Chat/Channel);
    - устаревшие `forward_from` / `forward_from_chat` / `forward_sender_name`
      (на случай старой версии aiogram/Bot API).
    """
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        sender_user = getattr(origin, "sender_user", None)
        if sender_user is not None:
            return sender_user.id, sender_user.full_name, sender_user.username, sender_user.is_bot

        sender_user_name = getattr(origin, "sender_user_name", None)
        if sender_user_name:
            return _stable_id_from_name(sender_user_name), sender_user_name, None, False

        sender_chat = getattr(origin, "sender_chat", None) or getattr(origin, "chat", None)
        if sender_chat is not None:
            title = sender_chat.title or sender_chat.full_name or "канал"
            return (
                _stable_id_from_name(f"chat:{sender_chat.id}"),
                title,
                getattr(sender_chat, "username", None),
                False,
            )
        return None

    forward_from = getattr(message, "forward_from", None)
    if forward_from is not None:
        return forward_from.id, forward_from.full_name, forward_from.username, forward_from.is_bot

    forward_from_chat = getattr(message, "forward_from_chat", None)
    if forward_from_chat is not None:
        title = forward_from_chat.title or "канал"
        return (
            _stable_id_from_name(f"chat:{forward_from_chat.id}"),
            title,
            getattr(forward_from_chat, "username", None),
            False,
        )

    forward_sender_name = getattr(message, "forward_sender_name", None)
    if forward_sender_name:
        return _stable_id_from_name(forward_sender_name), forward_sender_name, None, False

    return None


def _media_kind(message: Message) -> str | None:
    if message.photo:
        return "photo"
    if message.sticker:
        return "sticker"
    if message.video:
        return "video"
    if message.voice:
        return "voice"
    if message.video_note:
        return "video_note"
    if message.document:
        return "document"
    if message.animation:
        return "animation"
    return None


def _media_file_id(message: Message) -> str | None:
    """
    file_id, по которому позже (в момент рендера цитаты) можно скачать
    сам файл через bot.get_file(). Bot API не позволяет получить
    произвольное сообщение чата заново, поэтому file_id нужно сохранить
    сразу, пока сообщение "видно" боту.

    Пока поддерживаются только фото — именно они превращались в
    "[медиа]" в карточке цитаты. Остальные типы (стикеры, видео и т.д.)
    можно добавить по тому же принципу при необходимости.
    """
    if message.photo:
        return message.photo[-1].file_id  # -1 — самый большой размер
    return None


async def log_message(message: Message) -> None:
    """Записать сообщение в журнал. Вызывается из middleware на каждое сообщение чата."""
    if message.from_user is None:
        return

    forward_author = _forward_author(message)
    if forward_author is not None:
        author_id, author_full_name, author_username, author_is_bot = forward_author
    else:
        author_id = message.from_user.id
        author_full_name = message.from_user.full_name
        author_username = message.from_user.username
        author_is_bot = message.from_user.is_bot

    text = message.text or message.caption
    media_kind = _media_kind(message)
    media_file_id = _media_file_id(message)
    date = (message.date or dt.datetime.now(dt.timezone.utc)).isoformat()

    async with get_connection() as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO quotes_message_log
                (chat_id, message_id, user_id, user_full_name, user_username,
                 is_bot, text, has_media, media_kind, media_file_id, reply_to_message_id, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.chat.id,
                message.message_id,
                author_id,
                author_full_name,
                author_username,
                int(author_is_bot),
                text,
                int(media_kind is not None),
                media_kind,
                media_file_id,
                message.reply_to_message.message_id if message.reply_to_message else None,
                date,
            ),
        )
        await db.commit()


async def get_quote_window(
    chat_id: int, anchor_message_id: int, n_below: int, exclude_message_id: int | None = None
) -> list[MessageLog]:
    """
    Вернуть анкорное сообщение и до n_below сообщений после него по
    возрастанию message_id (сообщения, не залогированные ранее —
    например, отправленные до запуска бота — просто отсутствуют
    в выдаче, окно "сжимается").

    exclude_message_id — id сообщения с самой командой /qt: оно тоже
    успевает попасть в журнал (middleware логирует его до того, как
    отработает хендлер) и, будучи "следующим" по message_id, иначе
    само затесалось бы в цитату как одно из N сообщений вниз.
    """
    n_below = max(0, min(n_below, MAX_WINDOW))
    async with get_connection() as db:
        if exclude_message_id is None:
            cursor = await db.execute(
                
                """
                SELECT * FROM quotes_message_log
                WHERE chat_id = ? AND message_id >= ?
                ORDER BY message_id ASC
                LIMIT ?
                """,
                (chat_id, anchor_message_id, n_below + 1),
            )
        else:
            cursor = await db.execute(
                """
                SELECT * FROM quotes_message_log
                WHERE chat_id = ? AND message_id >= ? AND message_id != ?
                ORDER BY message_id ASC
                LIMIT ?
                """,
                (chat_id, anchor_message_id, exclude_message_id, n_below + 1),
            )
        rows = await cursor.fetchall()

    return [MessageLog.from_row(row) for row in rows]