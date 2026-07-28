"""Автоматический бэкап базы данных."""
import asyncio
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class DatabaseBackup:
    """Автоматический бэкап базы данных."""

    def __init__(
        self,
        db_path: Path,
        backup_dir: Path,
        interval_hours: int = 24,
        keep_backups: int = 7
    ):
        """
        Args:
            db_path: Путь к файлу БД
            backup_dir: Директория для бэкапов
            interval_hours: Интервал между бэкапами (часы)
            keep_backups: Количество бэкапов для хранения
        """
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.interval = interval_hours * 3600
        self.keep_backups = keep_backups
        self._task: Optional[asyncio.Task] = None

    def start(self):
        """Запускает автоматический бэкап."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
            logger.info(
                "Database backup started",
                extra={"extra_data": {
                    "interval_hours": self.interval // 3600,
                    "keep_backups": self.keep_backups
                }}
            )

    def stop(self):
        """Останавливает бэкап."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Database backup stopped")

    async def _run(self):
        """Основной цикл бэкапа."""
        # Делаем первый бэкап сразу при старте
        await self.backup()

        while True:
            try:
                await asyncio.sleep(self.interval)
                await self.backup()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Backup task failed")
                await asyncio.sleep(300)  # Повтор через 5 минут

    async def backup(self):
        """Создаёт бэкап базы данных."""
        try:
            # Проверяем что БД существует
            if not self.db_path.exists():
                logger.warning(
                    "Database file not found for backup",
                    extra={"extra_data": {"db_path": str(self.db_path)}}
                )
                return

            # Создаём директорию для бэкапов
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            # Имя файла с датой
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.backup_dir / f"backup_{timestamp}.db"

            # Копируем файл БД
            await asyncio.to_thread(shutil.copy2, self.db_path, backup_file)

            logger.info(
                "Database backed up successfully",
                extra={"extra_data": {
                    "backup_file": backup_file.name,
                    "size_mb": round(backup_file.stat().st_size / 1024 / 1024, 2)
                }}
            )

            # Удаляем старые бэкапы
            await self._cleanup_old_backups()

        except Exception:
            logger.exception("Failed to backup database")

    async def _cleanup_old_backups(self):
        """Удаляет старые бэкапы."""
        try:
            backups = sorted(self.backup_dir.glob("backup_*.db"))

            # Оставляем только последние N
            to_delete = backups[:-self.keep_backups] if len(backups) > self.keep_backups else []

            for backup_file in to_delete:
                await asyncio.to_thread(backup_file.unlink)
                logger.info(
                    "Deleted old backup",
                    extra={"extra_data": {"file": backup_file.name}}
                )

        except Exception:
            logger.exception("Failed to cleanup old backups")

    async def restore(self, backup_file: Path):
        """
        Восстанавливает БД из бэкапа.

        Args:
            backup_file: Путь к файлу бэкапа
        """
        try:
            if not backup_file.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_file}")

            # Создаём копию текущей БД на случай отката
            current_backup = self.db_path.with_suffix('.db.before_restore')
            if self.db_path.exists():
                await asyncio.to_thread(shutil.copy2, self.db_path, current_backup)

            # Восстанавливаем из бэкапа
            await asyncio.to_thread(shutil.copy2, backup_file, self.db_path)

            logger.info(
                "Database restored successfully",
                extra={"extra_data": {"from_backup": backup_file.name}}
            )

        except Exception:
            logger.exception("Failed to restore database")
            raise

    def get_backups(self) -> list[tuple[Path, datetime, int]]:
        """
        Получает список всех бэкапов.

        Returns:
            List of (path, datetime, size_bytes)
        """
        backups = []
        for backup_file in sorted(self.backup_dir.glob("backup_*.db")):
            try:
                # Парсим дату из имени файла
                date_str = backup_file.stem.replace("backup_", "")
                backup_date = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                size = backup_file.stat().st_size
                backups.append((backup_file, backup_date, size))
            except Exception:
                logger.warning(f"Invalid backup file: {backup_file.name}")
                continue

        return sorted(backups, key=lambda x: x[1], reverse=True)
