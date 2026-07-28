"""
Доступ к БД модуля цитатника.

Использует тот же файл sqlite, что и остальной проект
(`app.database.db.get_db_path()`), но заводит свои таблицы отдельным
`executescript` — так они не смешиваются с SCHEMA из
`app/database/models.py`, и его не нужно трогать при обновлении модуля.
"""
from __future__ import annotations

import contextlib
import logging
from typing import AsyncIterator

import aiosqlite

from app.database.db import get_db_path
from app.icons.models import QUOTES_SCHEMA

logger = logging.getLogger(__name__)


async def _ensure_media_file_id_column(db: aiosqlite.Connection) -> None:
    """
    CREATE TABLE IF NOT EXISTS не добавит новую колонку в уже существующую
    таблицу — если quotes_message_log была создана до появления
    media_file_id, добавляем её вручную.
    """
    cursor = await db.execute("PRAGMA table_info(quotes_message_log)")
    columns = {row[1] for row in await cursor.fetchall()}
    if "media_file_id" not in columns:
        await db.execute("ALTER TABLE quotes_message_log ADD COLUMN media_file_id TEXT")
        logger.info("quotes_message_log: добавлена колонка media_file_id")


async def init_quotes_db() -> None:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.executescript(QUOTES_SCHEMA)
        await _ensure_media_file_id_column(db)
        await db.commit()

    logger.info("Модуль цитат готов")


@contextlib.asynccontextmanager
async def get_connection() -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(get_db_path()) as db:
        db.row_factory = aiosqlite.Row
        yield db