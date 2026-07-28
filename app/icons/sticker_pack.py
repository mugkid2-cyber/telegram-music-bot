from __future__ import annotations

import re

from aiogram import Bot
from aiogram.types import BufferedInputFile, InputSticker

from app.icons.db import get_connection
from app.icons.models import QuoteStickerPack

TELEGRAM_PACK_STICKER_LIMIT = 120
QUOTE_EMOJI = "\U0001F4AC"  # 💬


def _slugify_chat_id(chat_id: int) -> str:
    # id супергрупп отрицательные (-100...), делаем безопасную часть имени
    return f"c{abs(chat_id)}"


def build_pack_name(chat_id: int, part_number: int, bot_username: str) -> str:
    base = f"quotes_{_slugify_chat_id(chat_id)}_p{part_number}"
    name = f"{base}_by_{bot_username}"
    # Telegram: только [a-zA-Z0-9_], <= 64 символов, начинается с буквы
    name = re.sub(r"[^a-zA-Z0-9_]", "", name)
    return name[:64]


def build_pack_title(chat_title: str, part_number: int) -> str:
    title = f"Цитаты «{chat_title}»" if part_number == 1 else f"Цитаты «{chat_title}» #{part_number}"
    return title[:128]


async def _get_open_pack(chat_id: int) -> QuoteStickerPack | None:
    async with get_connection() as db:
        cursor = await db.execute(
            """
            SELECT * FROM quotes_sticker_packs
            WHERE chat_id = ? AND status = 'open'
            ORDER BY part_number DESC
            LIMIT 1
            """,
            (chat_id,),
        )
        row = await cursor.fetchone()
    return QuoteStickerPack.from_row(row) if row else None


async def _next_part_number(chat_id: int) -> int:
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT MAX(part_number) AS mx FROM quotes_sticker_packs WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
    return (row["mx"] or 0) + 1


async def add_quote_sticker(
    bot: Bot,
    chat_id: int,
    chat_title: str,
    owner_user_id: int,
    png_bytes: bytes,
) -> tuple[QuoteStickerPack, str, str]:
    """
    Добавляет отрендеренный стикер в актуальную (открытую) часть
    стикерпака чата, при необходимости создавая пак или новую часть.

    Возвращает (pack, sticker_file_id, sticker_file_unique_id).
    """
    me = await bot.get_me()
    bot_username = me.username
    assert bot_username, "у бота должен быть username, чтобы создавать стикерпаки"

    pack = await _get_open_pack(chat_id)
    input_sticker = InputSticker(
        sticker=BufferedInputFile(png_bytes, filename="quote.png"),
        emoji_list=[QUOTE_EMOJI],
        format="static",
    )

    if pack is None:
        part_number = await _next_part_number(chat_id)
        pack_name = build_pack_name(chat_id, part_number, bot_username)
        pack_title = build_pack_title(chat_title, part_number)

        await bot.create_new_sticker_set(
            user_id=owner_user_id,
            name=pack_name,
            title=pack_title,
            stickers=[input_sticker],
        )

        async with get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO quotes_sticker_packs
                    (chat_id, part_number, pack_name, pack_title, sticker_count, status)
                VALUES (?, ?, ?, ?, 0, 'open')
                """,
                (chat_id, part_number, pack_name, pack_title),
            )
            await db.commit()
            pack_id = cursor.lastrowid

        pack = QuoteStickerPack(
            id=pack_id,
            chat_id=chat_id,
            part_number=part_number,
            pack_name=pack_name,
            pack_title=pack_title,
            sticker_count=0,
            status="open",
        )
    else:
        await bot.add_sticker_to_set(user_id=owner_user_id, name=pack.pack_name, sticker=input_sticker)

    # у addStickerToSet/createNewStickerSet нет ответа с file_id нового стикера —
    # достаём его, запросив актуальное состояние пака
    sticker_set = await bot.get_sticker_set(pack.pack_name)
    new_sticker = sticker_set.stickers[-1]

    new_count = pack.sticker_count + 1
    new_status = "full" if new_count >= TELEGRAM_PACK_STICKER_LIMIT else "open"
    async with get_connection() as db:
        await db.execute(
            "UPDATE quotes_sticker_packs SET sticker_count = ?, status = ? WHERE id = ?",
            (new_count, new_status, pack.id),
        )
        await db.commit()
    pack.sticker_count = new_count
    pack.status = new_status

    return pack, new_sticker.file_id, new_sticker.file_unique_id


async def delete_quote_sticker(bot: Bot, pack: QuoteStickerPack, sticker_file_id: str) -> None:
    await bot.delete_sticker_from_set(sticker=sticker_file_id)

    new_count = max(0, pack.sticker_count - 1)
    new_status = "open" if new_count < TELEGRAM_PACK_STICKER_LIMIT else pack.status
    async with get_connection() as db:
        await db.execute(
            "UPDATE quotes_sticker_packs SET sticker_count = ?, status = ? WHERE id = ?",
            (new_count, new_status, pack.id),
        )
        await db.commit()
    pack.sticker_count = new_count
    pack.status = new_status
