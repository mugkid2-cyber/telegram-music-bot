import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """Thread-safe connection pool для aiosqlite с автоматическим управлением ресурсами."""

    def __init__(self, db_path: Path, max_connections: int = 10, timeout: float = 30.0):
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=max_connections)
        self._created_connections = 0
        self._lock = asyncio.Lock()
        self._closed = False

    async def _create_connection(self) -> aiosqlite.Connection:
        """Создает новое подключение с оптимальными настройками."""
        conn = await aiosqlite.connect(
            self.db_path,
            timeout=self.timeout,
            check_same_thread=False,
        )
        # Оптимизация производительности SQLite
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        await conn.execute("PRAGMA temp_store=MEMORY")
        await conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
        await conn.execute("PRAGMA foreign_keys=ON")
        return conn

    async def acquire(self) -> aiosqlite.Connection:
        """Получить подключение из пула."""
        if self._closed:
            raise RuntimeError("Connection pool is closed")

        try:
            # Пытаемся получить существующее подключение без ожидания
            return self._pool.get_nowait()
        except asyncio.QueueEmpty:
            # Пула нет свободных - создаем новое если не достигли лимита
            async with self._lock:
                if self._created_connections < self.max_connections:
                    conn = await self._create_connection()
                    self._created_connections += 1
                    logger.debug(
                        "Created new connection (%d/%d)",
                        self._created_connections,
                        self.max_connections,
                    )
                    return conn

            # Достигли лимита - ждем освобождения
            try:
                return await asyncio.wait_for(self._pool.get(), timeout=self.timeout)
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Could not acquire connection within {self.timeout}s - pool exhausted"
                ) from None

    async def release(self, conn: aiosqlite.Connection) -> None:
        """Вернуть подключение в пул."""
        if self._closed:
            await conn.close()
            return

        try:
            # Откатываем незакоммиченные транзакции
            await conn.rollback()
        except Exception:
            logger.exception("Error rolling back connection before release")
            await conn.close()
            async with self._lock:
                self._created_connections -= 1
            return

        try:
            self._pool.put_nowait(conn)
        except asyncio.QueueFull:
            # Не должно происходить, но на всякий случай
            await conn.close()
            async with self._lock:
                self._created_connections -= 1

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Context manager для безопасного использования подключения."""
        conn = await self.acquire()
        try:
            yield conn
        except Exception:
            # При ошибке откатываем транзакцию
            try:
                await conn.rollback()
            except Exception:
                logger.exception("Error rolling back transaction after exception")
            raise
        finally:
            await self.release(conn)

    async def close(self) -> None:
        """Закрыть все подключения в пуле."""
        if self._closed:
            return

        self._closed = True

        # Закрываем все подключения в очереди
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                await conn.close()
            except asyncio.QueueEmpty:
                break
            except Exception:
                logger.exception("Error closing pooled connection")

        logger.info("Database connection pool closed")


# Глобальный пул - создается при инициализации БД
_global_pool: DatabaseConnectionPool | None = None


def get_pool() -> DatabaseConnectionPool:
    """Получить глобальный пул подключений."""
    if _global_pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db() first.")
    return _global_pool


async def init_pool(db_path: Path, max_connections: int = 10) -> None:
    """Инициализировать глобальный пул подключений."""
    global _global_pool
    if _global_pool is not None:
        await _global_pool.close()
    _global_pool = DatabaseConnectionPool(db_path, max_connections)
    logger.info("Database connection pool initialized with %d max connections", max_connections)


async def close_pool() -> None:
    """Закрыть глобальный пул подключений."""
    global _global_pool
    if _global_pool is not None:
        await _global_pool.close()
        _global_pool = None
