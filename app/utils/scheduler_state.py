import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

from app.config import get_settings

logger = logging.getLogger(__name__)


class SchedulerStateService:
    """Manages persistent scheduler state to prevent missed executions."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_settings().DATABASE_PATH

    async def get_last_birthday_check(self) -> datetime | None:
        """Get timestamp of last birthday check."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT last_birthday_check FROM scheduler_state WHERE id = 1"
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return datetime.fromisoformat(row[0])
                return None

    async def set_last_birthday_check(self, timestamp: datetime) -> None:
        """Record successful birthday check."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO scheduler_state (id, last_birthday_check, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_birthday_check = excluded.last_birthday_check,
                    updated_at = excluded.updated_at
                """,
                (timestamp.isoformat(), datetime.now().isoformat()),
            )
            await db.commit()

    async def get_last_quote_check(self) -> datetime | None:
        """Get timestamp of last quote check."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT last_quote_check FROM scheduler_state WHERE id = 1"
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return datetime.fromisoformat(row[0])
                return None

    async def set_last_quote_check(self, timestamp: datetime) -> None:
        """Record successful quote check."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO scheduler_state (id, last_quote_check, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_quote_check = excluded.last_quote_check,
                    updated_at = excluded.updated_at
                """,
                (timestamp.isoformat(), datetime.now().isoformat()),
            )
            await db.commit()

    async def get_last_cleanup(self) -> datetime | None:
        """Get timestamp of last cleanup."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT last_cleanup FROM scheduler_state WHERE id = 1"
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return datetime.fromisoformat(row[0])
                return None

    async def set_last_cleanup(self, timestamp: datetime) -> None:
        """Record successful cleanup."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO scheduler_state (id, last_cleanup, updated_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_cleanup = excluded.last_cleanup,
                    updated_at = excluded.updated_at
                """,
                (timestamp.isoformat(), datetime.now().isoformat()),
            )
            await db.commit()
