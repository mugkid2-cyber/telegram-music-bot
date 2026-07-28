from dataclasses import dataclass
from datetime import datetime, UTC

import aiosqlite

from app.config import get_settings


@dataclass(slots=True)
class BirthdayRecord:
    id: int
    chat_id: int
    user_id: int | None
    username: str | None
    display_name: str
    birth_day: int
    birth_month: int
    birth_year: int
    added_by_user_id: int
    last_greeted_year: int | None
    pinned_message_id: int | None = None
    pinned_date: str | None = None


class BirthdayPermissionError(Exception):
    """Запись принадлежит другому пользователю — менять её может только
    тот, кто добавил, или админ чата."""


class BirthdayService:
    def __init__(self) -> None:
        self._db_path = str(get_settings().DATABASE_PATH)
        self._initialized = False

    async def _ensure_schema(self) -> None:
        if self._initialized:
            return
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS birthdays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER,
                    username TEXT,
                    display_name TEXT NOT NULL,
                    birth_day INTEGER NOT NULL,
                    birth_month INTEGER NOT NULL,
                    birth_year INTEGER NOT NULL,
                    added_by_user_id INTEGER NOT NULL,
                    last_greeted_year INTEGER,
                    pinned_message_id INTEGER,
                    pinned_date TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            # Миграция для баз, созданных до появления закрепления сообщений.
            for column_def in ("pinned_message_id INTEGER", "pinned_date TEXT"):
                try:
                    await db.execute(f"ALTER TABLE birthdays ADD COLUMN {column_def}")
                except aiosqlite.OperationalError:
                    pass  # колонка уже существует

            # Миграция для баз, созданных до появления записей без username
            # (добавленных через reply или упоминание без @ — см.
            # birthday_handlers.py). Раньше колонка username была NOT NULL
            # с UNIQUE(chat_id, username) прямо в определении таблицы;
            # теперь она nullable, а уникальность обеспечивают частичные
            # индексы ниже. SQLite не умеет снимать NOT NULL через
            # ALTER TABLE, поэтому при необходимости пересобираем таблицу.
            cursor = await db.execute("PRAGMA table_info(birthdays)")
            columns = await cursor.fetchall()
            username_column = next((col for col in columns if col[1] == "username"), None)
            if username_column is not None and username_column[3] == 1:  # notnull флаг
                await db.execute("ALTER TABLE birthdays RENAME TO birthdays_old")
                await db.execute(
                    """
                    CREATE TABLE birthdays (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER NOT NULL,
                        user_id INTEGER,
                        username TEXT,
                        display_name TEXT NOT NULL,
                        birth_day INTEGER NOT NULL,
                        birth_month INTEGER NOT NULL,
                        birth_year INTEGER NOT NULL,
                        added_by_user_id INTEGER NOT NULL,
                        last_greeted_year INTEGER,
                        pinned_message_id INTEGER,
                        pinned_date TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                await db.execute(
                    """
                    INSERT INTO birthdays (
                        id, chat_id, user_id, username, display_name, birth_day, birth_month,
                        birth_year, added_by_user_id, last_greeted_year, pinned_message_id,
                        pinned_date, created_at
                    )
                    SELECT id, chat_id, user_id, username, display_name, birth_day, birth_month,
                           birth_year, added_by_user_id, last_greeted_year, pinned_message_id,
                           pinned_date, created_at
                    FROM birthdays_old
                    """
                )
                await db.execute("DROP TABLE birthdays_old")

            # Уникальность — двумя отдельными частичными индексами вместо
            # одного UNIQUE(chat_id, username): теперь запись может быть
            # без username (тогда уникальный ключ — user_id) или, в теории,
            # без user_id (тогда — username). Обычный UNIQUE(chat_id,
            # username) не спас бы от дублей записей без username, так как
            # в SQLite NULL в UNIQUE-индексе не считается равным другому
            # NULL.
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_birthdays_chat_username "
                "ON birthdays(chat_id, username) WHERE username IS NOT NULL"
            )
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_birthdays_chat_user_id "
                "ON birthdays(chat_id, user_id) WHERE user_id IS NOT NULL"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_birthdays_day_month "
                "ON birthdays(birth_month, birth_day)"
            )
            await db.commit()
        self._initialized = True

    async def add_or_update(
        self,
        *,
        chat_id: int,
        username: str | None,
        display_name: str,
        birth_day: int,
        birth_month: int,
        birth_year: int,
        added_by_user_id: int,
        user_id: int | None,
        requester_is_admin: bool,
    ) -> BirthdayRecord:
        await self._ensure_schema()
        if username is not None:
            username = username.lower()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            existing = await self._find_existing(db, chat_id, username, user_id)

            if existing and existing["added_by_user_id"] != added_by_user_id and not requester_is_admin:
                raise BirthdayPermissionError()

            created_at = datetime.now(UTC).isoformat()

            if existing:
                await db.execute(
                    """
                    UPDATE birthdays
                    SET display_name = ?, birth_day = ?, birth_month = ?, birth_year = ?,
                        user_id = ?, username = ?, added_by_user_id = ?, last_greeted_year = NULL
                    WHERE id = ?
                    """,
                    (
                        display_name,
                        birth_day,
                        birth_month,
                        birth_year,
                        user_id,
                        username,
                        added_by_user_id,
                        existing["id"],
                    ),
                )
                record_id = existing["id"]
            else:
                cursor = await db.execute(
                    """
                    INSERT INTO birthdays (
                        chat_id, user_id, username, display_name, birth_day, birth_month,
                        birth_year, added_by_user_id, last_greeted_year, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        chat_id,
                        user_id,
                        username,
                        display_name,
                        birth_day,
                        birth_month,
                        birth_year,
                        added_by_user_id,
                        created_at,
                    ),
                )
                record_id = cursor.lastrowid

            await db.commit()

        return BirthdayRecord(
            id=record_id,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            display_name=display_name,
            birth_day=birth_day,
            birth_month=birth_month,
            birth_year=birth_year,
            added_by_user_id=added_by_user_id,
            last_greeted_year=None,
        )

    @staticmethod
    async def _find_existing(
        db: aiosqlite.Connection, chat_id: int, username: str | None, user_id: int | None
    ) -> aiosqlite.Row | None:
        """Ищет существующую запись сначала по username (если он указан),
        затем по user_id — это позволяет и находить дубли для людей без
        username (у них ключ — только user_id), и «дозаполнять» username
        записи, которая раньше была создана через reply/упоминание без
        него."""
        if username is not None:
            cursor = await db.execute(
                "SELECT * FROM birthdays WHERE chat_id = ? AND username = ?",
                (chat_id, username),
            )
            row = await cursor.fetchone()
            if row is not None:
                return row

        if user_id is not None:
            cursor = await db.execute(
                "SELECT * FROM birthdays WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
            return await cursor.fetchone()

        return None

    async def delete(
        self,
        *,
        chat_id: int,
        username: str | None,
        user_id: int | None,
        requester_user_id: int,
        requester_is_admin: bool,
    ) -> bool:
        await self._ensure_schema()
        if username is not None:
            username = username.lower()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            existing = await self._find_existing(db, chat_id, username, user_id)
            if not existing:
                return False

            if existing["added_by_user_id"] != requester_user_id and not requester_is_admin:
                raise BirthdayPermissionError()

            await db.execute("DELETE FROM birthdays WHERE id = ?", (existing["id"],))
            await db.commit()

        return True

    async def list_for_chat(self, chat_id: int) -> list[BirthdayRecord]:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM birthdays WHERE chat_id = ? ORDER BY birth_month, birth_day",
                (chat_id,),
            )
            rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def get_todays_birthdays(self, day: int, month: int, year: int) -> list[BirthdayRecord]:
        """Дни рождения на сегодня, которые ещё не поздравляли в этом году
        (last_greeted_year != текущий год) — защита от дублей при рестарте
        бота в течение того же дня."""
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM birthdays
                WHERE birth_day = ? AND birth_month = ?
                  AND (last_greeted_year IS NULL OR last_greeted_year != ?)
                """,
                (day, month, year),
            )
            rows = await cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    async def mark_greeted(self, record_id: int, year: int) -> None:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE birthdays SET last_greeted_year = ? WHERE id = ?",
                (year, record_id),
            )
            await db.commit()

    async def set_pinned_message(
        self, record_id: int, message_id: int | None, pinned_date: str | None = None
    ) -> None:
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE birthdays SET pinned_message_id = ?, pinned_date = ? WHERE id = ?",
                (message_id, pinned_date, record_id),
            )
            await db.commit()

    async def get_pinned_messages(self) -> list[tuple[int, int, int, str | None]]:
        """Возвращает (record_id, chat_id, message_id, pinned_date) для всех
        поздравлений, которые всё ещё закреплены — чтобы открепить
        сообщения за прошлые дни в начале нового дня по МСК. pinned_date
        хранится в БД (а не только в памяти), чтобы при перезапуске бота
        сегодняшнее закреплённое сообщение не открепили раньше времени."""
        await self._ensure_schema()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT id, chat_id, pinned_message_id, pinned_date FROM birthdays "
                "WHERE pinned_message_id IS NOT NULL"
            )
            rows = await cursor.fetchall()
        return [(row[0], row[1], row[2], row[3]) for row in rows]

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> BirthdayRecord:
        return BirthdayRecord(
            id=row["id"],
            chat_id=row["chat_id"],
            user_id=row["user_id"],
            username=row["username"],
            display_name=row["display_name"],
            birth_day=row["birth_day"],
            birth_month=row["birth_month"],
            birth_year=row["birth_year"],
            added_by_user_id=row["added_by_user_id"],
            last_greeted_year=row["last_greeted_year"],
            pinned_message_id=row["pinned_message_id"],
            pinned_date=row["pinned_date"],
        )