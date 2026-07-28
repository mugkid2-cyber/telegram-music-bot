"""
Триггер для группы Нервы: простая версия для ручной загрузки треков.

Функционал:
- Детекция слова "нервы" (кириллица + транслит, независимо от регистра)
- Отправка случайных треков из папки audio
- Поддержка трёх версий: origin, speedup (1.25x), slowed (0.75x)
- Без повторений до исчерпания коллекции
"""
import asyncio
import logging
import random
import re
from pathlib import Path
from typing import Optional

from aiogram.types import FSInputFile

logger = logging.getLogger(__name__)

# Путь к аудио файлам
AUDIO_DIR = Path(__file__).parent / "audio"

# Паттерны для детекции слова "нервы"
NERVY_PATTERNS = [
    r"\bнервы\b",      # Кириллица
    r"\bнерв\b",
    r"\bnervy\b",      # Латиница
    r"\bnerv\b",
    r"\bnervi\b",
    r"\bнервов\b",     # Склонения
    r"\bнервам\b",
    r"\bнервами\b",
    r"\bнервах\b",
]


class NervyTrigger:
    """Управление триггером группы Нервы"""

    def __init__(self) -> None:
        self.audio_dir = AUDIO_DIR
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        # История воспроизведений
        self.played_tracks: set[str] = set()
        self._initialized = False

    async def initialize(self) -> None:
        """Инициализация триггера"""
        if self._initialized:
            return

        self._initialized = True
        logger.info("Инициализация триггера Нервы")

        # Проверяем наличие треков
        track_count = len(list(self.audio_dir.glob("*.mp3")))
        logger.info("Найдено треков в папке audio: %d", track_count)

        if track_count == 0:
            logger.warning(
                "В папке %s нет MP3 файлов. Добавьте треки вручную.",
                self.audio_dir
            )

    def check_trigger(self, text: str) -> bool:
        """Проверяет, содержит ли текст триггер слова 'нервы'"""
        if not text:
            return False

        normalized = text.lower().strip()

        for pattern in NERVY_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE | re.UNICODE):
                return True

        return False

    async def get_random_track(self) -> Optional[tuple[FSInputFile, str, str, Optional[Path]]]:
        """
        Возвращает случайный трек без повторений.

        Returns:
            Tuple (audio_file, title, performer, thumbnail_path) или None
        """
        if not self._initialized:
            await self.initialize()

        # Получаем все MP3 файлы
        all_tracks = list(self.audio_dir.glob("*.mp3"))

        if not all_tracks:
            logger.warning("Нет треков в папке %s", self.audio_dir)
            return None

        # Фильтруем неиграные треки
        available = [
            track for track in all_tracks
            if track.name not in self.played_tracks
        ]

        # Если все треки сыграны, сбрасываем историю
        if not available:
            logger.info("Все треки сыграны (%d), сброс истории", len(self.played_tracks))
            self.played_tracks.clear()
            available = all_tracks

        # Выбираем случайный трек
        track_path = random.choice(available)

        # Помечаем как сыгранный
        self.played_tracks.add(track_path.name)

        # Извлекаем название из имени файла или метаданных
        title = self._extract_title(track_path)
        performer = "Нервы"

        # Ищем обложку
        thumbnail_path = track_path.parent / f"{track_path.stem}.jpg"
        if not thumbnail_path.exists():
            thumbnail_path = None

        logger.info(
            "Отправка трека: %s, осталось неиграных: %d/%d",
            title,
            len(available) - 1,
            len(all_tracks)
        )

        try:
            audio_file = FSInputFile(track_path)
            return audio_file, title, performer, thumbnail_path
        except Exception:
            logger.exception("Ошибка загрузки файла трека %s", track_path)
            return None

    def _extract_title(self, track_path: Path) -> str:
        """Извлекает название трека из метаданных или имени файла"""
        try:
            import mutagen
            from mutagen.mp3 import MP3

            audio = MP3(track_path)
            if "TIT2" in audio:
                title = str(audio["TIT2"])
                return title.strip()
        except Exception:
            pass

        # Fallback: имя файла без расширения
        name = track_path.stem

        # Убираем технические префиксы
        name = re.sub(r'^[a-f0-9]{8,}_', '', name)
        name = re.sub(r'_(origin|speedup|slowed)$', '', name, flags=re.IGNORECASE)

        # Заменяем подчёркивания пробелами
        name = name.replace('_', ' ')

        return name.strip() or "Unknown"

    def get_stats(self) -> dict[str, int]:
        """Возвращает статистику триггера"""
        all_tracks = list(self.audio_dir.glob("*.mp3"))

        return {
            "total_tracks": len(all_tracks),
            "played_tracks": len(self.played_tracks),
            "remaining_tracks": len(all_tracks) - len(self.played_tracks),
        }


# Глобальный экземпляр триггера
_nervy_trigger_instance: Optional[NervyTrigger] = None


def get_nervy_trigger() -> NervyTrigger:
    """Возвращает глобальный экземпляр триггера"""
    global _nervy_trigger_instance

    if _nervy_trigger_instance is None:
        _nervy_trigger_instance = NervyTrigger()

    return _nervy_trigger_instance
