from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.icons.db import get_connection
from app.icons.message_log import MAX_WINDOW, get_quote_window
from app.icons.models import Quote, QuoteStickerPack
from app.icons.renderer import render_quote_card
from app.icons.sticker_pack import add_quote_sticker, delete_quote_sticker

logger = logging.getLogger(__name__)
router = Router(name="quotes")


async def _is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramBadRequest:
        return False
    return member.status in ("administrator", "creator")


def _parse_n(command: CommandObject) -> int | None:
    """
    Из '/qt 5' достаёт 5 — это ОБЩЕЕ число сообщений в цитате, включая
    само отмеченное (т.е. отмеченное + 4 следующих). Без аргумента
    считаем N=1 (только отмеченное сообщение).
    """
    if not command.args:
        return 1
    arg = command.args.strip().split()[0]
    if not arg.isdigit():
        return None
    n = int(arg)
    return n if n >= 1 else None


@router.message(Command("qt", "q"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_quote(message: Message, command: CommandObject, bot: Bot) -> None:
    if message.reply_to_message is None:
        await message.reply(
            "Ответь этой командой на сообщение, с которого должна начинаться цитата.\n"
            f"Пример: /qt 5 — возьмёт отмеченное сообщение и 4 следующих, всего 5 "
            f"(максимум {MAX_WINDOW + 1})."
        )
        return

    n = _parse_n(command)
    if n is None:
        await message.reply("N должно быть целым положительным числом, например: /qt 5")
        return
    n_below = n - 1  # N — общее число сообщений, отмеченное уже входит в счёт
    if n_below > MAX_WINDOW:
        await message.reply(f"Слишком длинная цитата, максимум {MAX_WINDOW + 1} сообщений вместе с отмеченным.")
        return

    anchor_id = message.reply_to_message.message_id
    window = await get_quote_window(message.chat.id, anchor_id, n_below, exclude_message_id=message.message_id)

    if not window:
        await message.reply(
            "Не нашёл это сообщение в журнале — похоже, оно было отправлено до того, "
            "как бот начал логировать чат, поэтому процитировать его не получится."
        )
        return

    status_msg = await message.reply("Готовлю цитату…")

    try:
        png_bytes = await render_quote_card(bot, window)
    except Exception:
        logger.exception("quote render failed, chat=%s anchor=%s", message.chat.id, anchor_id)
        await status_msg.edit_text("Не получилось отрисовать цитату, попробуйте ещё раз.")
        return

    try:
        pack, file_id, file_unique_id = await add_quote_sticker(
            bot=bot,
            chat_id=message.chat.id,
            chat_title=message.chat.title or "chat",
            owner_user_id=message.from_user.id,
            png_bytes=png_bytes,
        )
    except TelegramBadRequest as e:
        logger.exception("sticker pack error, chat=%s", message.chat.id)
        await status_msg.edit_text(f"Telegram отказал при добавлении стикера в пак: {e.message}")
        return

    async with get_connection() as db:
        await db.execute(
            """
            INSERT INTO quotes
                (chat_id, pack_id, sticker_file_id, sticker_file_unique_id,
                 source_message_ids, anchor_message_id, created_by_user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.chat.id,
                pack.id,
                file_id,
                file_unique_id,
                ",".join(str(m.message_id) for m in window),
                anchor_id,
                message.from_user.id,
            ),
        )
        await db.commit()

    await status_msg.delete()
    await message.reply_sticker(
        sticker=file_id,
        reply_to_message_id=message.reply_to_message.message_id,
    )
    await message.answer(
        f"Добавлено в стикерпак чата ({pack.sticker_count}/120): "
        f"https://t.me/addstickers/{pack.pack_name}"
    )


@router.message(Command("qdel"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_quote_delete(message: Message, bot: Bot) -> None:
    if message.reply_to_message is None or message.reply_to_message.sticker is None:
        await message.reply("Ответь командой /qdel на стикер-цитату, которую нужно удалить.")
        return

    if not await _is_chat_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("Удалять цитаты может только администратор группы.")
        return

    file_unique_id = message.reply_to_message.sticker.file_unique_id

    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT * FROM quotes WHERE chat_id = ? AND sticker_file_unique_id = ?",
            (message.chat.id, file_unique_id),
        )
        quote_row = await cursor.fetchone()

    if quote_row is None:
        await message.reply("Это не цитата из стикерпака этого чата, либо она уже удалена.")
        return

    quote = Quote.from_row(quote_row)

    async with get_connection() as db:
        cursor = await db.execute("SELECT * FROM quotes_sticker_packs WHERE id = ?", (quote.pack_id,))
        pack_row = await cursor.fetchone()
    pack = QuoteStickerPack.from_row(pack_row)

    try:
        await delete_quote_sticker(bot, pack, quote.sticker_file_id)
    except TelegramBadRequest as e:
        await message.reply(f"Telegram отказал при удалении стикера: {e.message}")
        return

    async with get_connection() as db:
        await db.execute("DELETE FROM quotes WHERE id = ?", (quote.id,))
        await db.commit()

    await message.reply("Цитата удалена из стикерпака.")