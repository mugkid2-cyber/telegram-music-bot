import logging
from pathlib import Path

import aiosqlite

from app.config import get_settings
from app.database.models import SCHEMA

logger = logging.getLogger(__name__)


async def init_db() -> None:
    settings = get_settings()
    db_path: Path = settings.DATABASE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()

    logger.info("База данных готова")


def get_db_path() -> Path:
    return get_settings().DATABASE_PATH
