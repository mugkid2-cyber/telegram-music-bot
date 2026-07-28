"""
База данных для сохранённых TikTok видео.
Хранит видео за последние 3 дня, автоматически чистит старые.
"""
import logging
import aiosqlite
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TikTokDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def init_db(self):
        """Создаёт таблицу если её нет"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS tiktok_videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    file_path TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_saved_at ON tiktok_videos(saved_at)
            """)
            await conn.commit()

    async def save_video(self, url: str, file_path: str, user_id: int, chat_id: int):
        """Сохраняет информацию о скачанном TikTok"""
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.execute(
                    "INSERT OR IGNORE INTO tiktok_videos (url, file_path, user_id, chat_id) VALUES (?, ?, ?, ?)",
                    (url, file_path, user_id, chat_id)
                )
                await conn.commit()
                logger.info("Saved TikTok: %s", url)
        except Exception as e:
            logger.error("Failed to save TikTok: %s", e)

    async def get_random_video(self) -> Optional[tuple[str, str]]:
        """Возвращает случайное видео за последние 3 дня (file_path, url)"""
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)

        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """
                SELECT file_path, url FROM tiktok_videos
                WHERE saved_at >= ?
                ORDER BY RANDOM()
                LIMIT 1
                """,
                (three_days_ago.isoformat(),)
            ) as cursor:
                row = await cursor.fetchone()
                return row if row else None

    async def cleanup_old_videos(self):
        """Удаляет видео старше 3 дней из БД и с диска"""
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)

        async with aiosqlite.connect(self.db_path) as conn:
            # Получаем пути к файлам для удаления
            async with conn.execute(
                "SELECT file_path FROM tiktok_videos WHERE saved_at < ?",
                (three_days_ago.isoformat(),)
            ) as cursor:
                old_files = [row[0] for row in await cursor.fetchall()]

            # Удаляем файлы с диска
            for file_path in old_files:
                try:
                    Path(file_path).unlink(missing_ok=True)
                    logger.info("Deleted old file: %s", file_path)
                except Exception as e:
                    logger.error("Failed to delete %s: %s", file_path, e)

            # Удаляем записи из БД
            await conn.execute(
                "DELETE FROM tiktok_videos WHERE saved_at < ?",
                (three_days_ago.isoformat(),)
            )
            deleted_count = conn.total_changes
            await conn.commit()

            logger.info("Cleaned up %d old TikTok records", deleted_count)
            return deleted_count

    async def get_total_count(self) -> int:
        """Возвращает общее количество видео за последние 3 дня"""
        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)

        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM tiktok_videos WHERE saved_at >= ?",
                (three_days_ago.isoformat(),)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0
