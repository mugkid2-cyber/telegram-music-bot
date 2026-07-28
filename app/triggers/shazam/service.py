"""Сервис распознавания музыки (Shazam)."""
import logging
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import aiofiles
from shazamio import Shazam

logger = logging.getLogger(__name__)


@dataclass
class TrackInfo:
    """Информация о распознанном треке."""
    title: str
    artist: str
    album: Optional[str] = None
    genre: Optional[str] = None
    release_year: Optional[str] = None
    duration: Optional[int] = None  # секунды
    cover_url: Optional[str] = None
    apple_music_url: Optional[str] = None
    youtube_url: Optional[str] = None
    shazam_url: Optional[str] = None
    isrc: Optional[str] = None


class ShazamService:
    """Сервис для распознавания музыки."""

    def __init__(self):
        self.shazam = Shazam()

    async def recognize_from_file(self, file_path: Path) -> Optional[TrackInfo]:
        """
        Распознаёт трек из аудио/видео файла.

        Args:
            file_path: Путь к файлу

        Returns:
            TrackInfo или None если не распознано
        """
        try:
            logger.info("Recognizing track from file: %s", file_path.name)

            # Распознаём через Shazam
            result = await self.shazam.recognize(str(file_path))

            if not result or "track" not in result:
                logger.warning("Track not recognized")
                return None

            track_data = result["track"]

            # Извлекаем информацию
            track_info = self._parse_track_data(track_data)

            logger.info(
                "Track recognized: %s - %s",
                track_info.artist,
                track_info.title
            )

            return track_info

        except Exception as e:
            logger.exception("Failed to recognize track: %s", e)
            return None

    def _parse_track_data(self, track_data: dict) -> TrackInfo:
        """Парсит данные трека из ответа Shazam."""
        # Базовая информация
        title = track_data.get("title", "Unknown")
        artist = track_data.get("subtitle", "Unknown Artist")

        # Дополнительная информация
        album = None
        genre = None
        release_year = None
        duration = None
        cover_url = None
        apple_music_url = None
        youtube_url = None
        shazam_url = None
        isrc = None

        # Альбом и жанр
        if "sections" in track_data:
            for section in track_data["sections"]:
                if section.get("type") == "SONG":
                    metadata = section.get("metadata", [])
                    for item in metadata:
                        if item.get("title") == "Album":
                            album = item.get("text")
                        elif item.get("title") == "Released":
                            release_year = item.get("text")
                        elif item.get("title") == "Genre":
                            genre = item.get("text")

        # Обложка
        if "images" in track_data:
            cover_url = track_data["images"].get("coverart")

        # Длительность (в секундах)
        if "urlparams" in track_data:
            duration_ms = track_data["urlparams"].get("{tracklength}")
            if duration_ms:
                try:
                    duration = int(duration_ms) // 1000
                except (ValueError, TypeError):
                    pass

        # ISRC код
        isrc = track_data.get("isrc")

        # Ссылки
        if "hub" in track_data:
            hub = track_data["hub"]
            if "actions" in hub:
                for action in hub["actions"]:
                    if action.get("type") == "uri":
                        uri = action.get("uri", "")
                        if "apple.com" in uri:
                            apple_music_url = uri

        # Shazam URL
        if "url" in track_data:
            shazam_url = track_data["url"]

        # YouTube URL (будем искать через наш search_service)
        # Пока оставим None, заполним в handler'е

        return TrackInfo(
            title=title,
            artist=artist,
            album=album,
            genre=genre,
            release_year=release_year,
            duration=duration,
            cover_url=cover_url,
            apple_music_url=apple_music_url,
            youtube_url=youtube_url,
            shazam_url=shazam_url,
            isrc=isrc
        )

    async def download_temp_file(self, file_bytes: bytes, extension: str = "mp3") -> Path:
        """
        Сохраняет файл во временную директорию.

        Args:
            file_bytes: Байты файла
            extension: Расширение файла

        Returns:
            Путь к временному файлу
        """
        # Используем NamedTemporaryFile с delete=False для безопасности
        with tempfile.NamedTemporaryFile(
            suffix=f".{extension}",
            prefix="shazam_",
            delete=False
        ) as temp_file:
            temp_path = Path(temp_file.name)

        async with aiofiles.open(temp_path, "wb") as f:
            await f.write(file_bytes)

        logger.debug("Saved temp file: %s (%d bytes)", temp_path.name, len(file_bytes))
        return temp_path

    async def cleanup_temp_file(self, file_path: Path):
        """Удаляет временный файл."""
        try:
            if file_path.exists():
                await aiofiles.os.remove(file_path)
                logger.debug("Cleaned up temp file: %s", file_path.name)
        except Exception as e:
            logger.warning("Failed to cleanup temp file %s: %s", file_path, e)
