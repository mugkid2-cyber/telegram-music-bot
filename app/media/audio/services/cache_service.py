import logging
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from app.database.db import get_db_path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CachedTrack:
    id: int
    source: str
    track_id: str
    title: str
    file_path: str
    created_at: str


class CacheService:
    async def get(self, source: str, track_id: str) -> CachedTrack | None:
        async with aiosqlite.connect(get_db_path()) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, source, track_id, title, file_path, created_at
                FROM tracks
                WHERE source = ? AND track_id = ?
                """,
                (source, track_id),
            )
            row = await cursor.fetchone()

        if row is None:
            return None

        cached = CachedTrack(
            id=row["id"],
            source=row["source"],
            track_id=row["track_id"],
            title=row["title"],
            file_path=row["file_path"],
            created_at=row["created_at"],
        )

        if not Path(cached.file_path).exists():
            logger.warning(
                "Cached file missing for %s:%s — %s",
                source,
                track_id,
                cached.file_path,
            )
            await self.delete(source, track_id)
            return None

        return cached

    async def save(
        self,
        source: str,
        track_id: str,
        title: str,
        file_path: str,
    ) -> None:
        async with aiosqlite.connect(get_db_path()) as db:
            await db.execute(
                """
                INSERT INTO tracks (source, track_id, title, file_path)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source, track_id) DO UPDATE SET
                    title = excluded.title,
                    file_path = excluded.file_path,
                    created_at = CURRENT_TIMESTAMP
                """,
                (source, track_id, title, file_path),
            )
            await db.commit()

        logger.info("Cached track %s:%s -> %s", source, track_id, file_path)

    async def delete(self, source: str, track_id: str) -> None:
        async with aiosqlite.connect(get_db_path()) as db:
            await db.execute(
                "DELETE FROM tracks WHERE source = ? AND track_id = ?",
                (source, track_id),
            )
            await db.commit()
