import asyncio
from dataclasses import dataclass

import aiosqlite

from app.config import get_settings


@dataclass(slots=True)
class ChatMember:
    user_id: int
    username: str | None
    first_name: str
    is_bot: bool


class ChatMembersService:
    """Bot API не даёт способа получить полный список участников группы —
    только тех, кто когда-либо написал сообщение при бое бота в чате.
    Поэтому список пополняется постепенно, через ChatMemberTrackingMiddleware.
    """

    def __init__(self) -> None:
        self._db_path = str(get_settings().DATABASE_PATH)
        self._initialized = False

    async def _ensure_schema(self) -> None:
        if self._initialized:
            return
        async with aiosqlite.connect(self._db_path, timeout=10.0) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_members (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    first_name TEXT NOT NULL,
                    is_bot INTEGER NOT NULL DEFAULT 0,
                    last_seen TEXT NOT NULL,
                    PRIMARY KEY (chat_id, user_id)
                )
                """
            )
            await db.commit()
        self._initialized = True

    async def track(
        self,
        *,
        chat_id: int,
        user_id: int,
        username: str | None,
        first_name: str,
        is_bot: bool,
    ) -> None:
        await self._ensure_schema()

        # Retry logic для избежания database locked errors
        max_retries = 3
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                async with aiosqlite.connect(self._db_path, timeout=10.0) as db:
                    # Включаем WAL mode для лучшей concurrent записи
                    await db.execute("PRAGMA journal_mode=WAL")
                    await db.execute(
                        """
                        INSERT INTO chat_members (chat_id, user_id, username, first_name, is_bot, last_seen)
                        VALUES (?, ?, ?, ?, ?, datetime('now'))
                        ON CONFLICT(chat_id, user_id) DO UPDATE SET
                            username = excluded.username,
                            first_name = excluded.first_name,
                            is_bot = excluded.is_bot,
                            last_seen = excluded.last_seen
                        """,
                        (chat_id, user_id, username, first_name, int(is_bot)),
                    )
                    await db.commit()
                    return  # Успешно записали
            except Exception as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                # Если это последняя попытка или другая ошибка - логируем но не падаем
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    "Failed to track chat member %s in chat %s after %d attempts: %s",
                    user_id, chat_id, attempt + 1, e
                )
                return

    async def get_members(self, chat_id: int, exclude_user_id: int | None = None) -> list[ChatMember]:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path, timeout=10.0) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM chat_members WHERE chat_id = ?", (chat_id,)
            )
            rows = await cursor.fetchall()

        return [
            ChatMember(
                user_id=row["user_id"],
                username=row["username"],
                first_name=row["first_name"],
                is_bot=bool(row["is_bot"]),
            )
            for row in rows
            if not row["is_bot"] and (exclude_user_id is None or row["user_id"] != exclude_user_id)
        ]