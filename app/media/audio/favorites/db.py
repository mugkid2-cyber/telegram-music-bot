"""База данных избранных треков."""
import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

from app.config import get_settings
from app.media.audio.favorites.models import FavoriteTrack

logger = logging.getLogger(__name__)


class FavoritesDB:
    """Управление избранными треками в БД."""

    def __init__(self):
        settings = get_settings()
        self.db_path = settings.DATABASE_PATH.parent / "favorites.db"

    async def init(self):
        """Инициализация таблицы избранного."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    platform TEXT NOT NULL,
                    track_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    performer TEXT NOT NULL,
                    url TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    UNIQUE(user_id, platform, track_id)
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_favorites_user
                ON favorites(user_id)
            """)
            await db.commit()

    async def add(self, favorite: FavoriteTrack) -> bool:
        """Добавить трек в избранное."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR IGNORE INTO favorites
                    (user_id, platform, track_id, title, performer, url, added_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    favorite.user_id,
                    favorite.platform,
                    favorite.track_id,
                    favorite.title,
                    favorite.performer,
                    favorite.url,
                    favorite.added_at.isoformat()
                ))
                await db.commit()
                return db.total_changes > 0
        except Exception:
            logger.exception("Failed to add favorite")
            return False

    async def remove(self, user_id: int, platform: str, track_id: str) -> bool:
        """Удалить трек из избранного."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    DELETE FROM favorites
                    WHERE user_id = ? AND platform = ? AND track_id = ?
                """, (user_id, platform, track_id))
                await db.commit()
                return db.total_changes > 0
        except Exception:
            logger.exception("Failed to remove favorite")
            return False

    async def get_user_favorites(self, user_id: int, limit: int = 50) -> list[FavoriteTrack]:
        """Получить избранное пользователя (последние N треков)."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT user_id, platform, track_id, title, performer, url, added_at
                    FROM favorites
                    WHERE user_id = ?
                    ORDER BY added_at DESC
                    LIMIT ?
                """, (user_id, limit)) as cursor:
                    rows = await cursor.fetchall()

                return [
                    FavoriteTrack(
                        user_id=row['user_id'],
                        platform=row['platform'],
                        track_id=row['track_id'],
                        title=row['title'],
                        performer=row['performer'],
                        url=row['url'],
                        added_at=datetime.fromisoformat(row['added_at'])
                    )
                    for row in rows
                ]
        except Exception:
            logger.exception("Failed to get favorites")
            return []

    async def is_favorite(self, user_id: int, platform: str, track_id: str) -> bool:
        """Проверить, находится ли трек в избранном."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("""
                    SELECT 1 FROM favorites
                    WHERE user_id = ? AND platform = ? AND track_id = ?
                """, (user_id, platform, track_id)) as cursor:
                    row = await cursor.fetchone()
                    return row is not None
        except Exception:
            logger.exception("Failed to check favorite")
            return False

    async def count_favorites(self, user_id: int) -> int:
        """Количество избранных треков пользователя."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("""
                    SELECT COUNT(*) FROM favorites WHERE user_id = ?
                """, (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0
        except Exception:
            logger.exception("Failed to count favorites")
            return 0
