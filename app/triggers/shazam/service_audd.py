"""
Альтернативный сервис распознавания музыки через AudD API.
Не требует shazamio и работает на всех платформах.
"""
import logging
import aiohttp
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import tempfile
import aiofiles

logger = logging.getLogger(__name__)


@dataclass
class TrackInfo:
    """Информация о распознанном треке."""
    title: str
    artist: str
    album: Optional[str] = None
    release_year: Optional[str] = None
    genre: Optional[str] = None
    duration: Optional[int] = None
    cover_url: Optional[str] = None
    shazam_url: Optional[str] = None
    apple_music_url: Optional[str] = None
    spotify_url: Optional[str] = None


class AudDService:
    """Сервис распознавания музыки через AudD API."""

    # Бесплатный API ключ (лимит: 50 запросов в день)
    # Можно получить свой на https://audd.io/
    API_KEY = "test"  # Используем тестовый ключ
    API_URL = "https://api.audd.io/"

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получает или создаёт HTTP сессию."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """Закрывает HTTP сессию."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def download_temp_file(self, file_data: bytes, extension: str = "mp3") -> Path:
        """
        Сохраняет данные во временный файл.

        Args:
            file_data: Байты файла
            extension: Расширение файла

        Returns:
            Path к временному файлу
        """
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f".{extension}"
        )
        temp_path = Path(temp_file.name)

        async with aiofiles.open(temp_path, 'wb') as f:
            await f.write(file_data)

        logger.debug(f"Created temp file: {temp_path}")
        return temp_path

    async def cleanup_temp_file(self, file_path: Path):
        """
        Удаляет временный файл.

        Args:
            file_path: Путь к файлу для удаления
        """
        try:
            if file_path and file_path.exists():
                file_path.unlink()
                logger.debug(f"Deleted temp file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete temp file {file_path}: {e}")

    async def recognize_from_file(self, file_path: Path) -> Optional[TrackInfo]:
        """
        Распознаёт музыку из файла.

        Args:
            file_path: Путь к аудио/видео файлу

        Returns:
            TrackInfo если трек распознан, иначе None
        """
        try:
            session = await self._get_session()

            # Читаем файл
            async with aiofiles.open(file_path, 'rb') as f:
                file_data = await f.read()

            # Формируем запрос к API
            data = aiohttp.FormData()
            data.add_field('api_token', self.API_KEY)
            data.add_field('return', 'apple_music,spotify')  # Запрашиваем ссылки
            data.add_field('file', file_data,
                          filename=file_path.name,
                          content_type='application/octet-stream')

            logger.info("Sending recognition request to AudD API...")

            # Отправляем запрос
            async with session.post(self.API_URL, data=data, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.error(f"AudD API error: HTTP {response.status}")
                    return None

                result = await response.json()

                # Проверяем результат
                if result.get('status') != 'success':
                    logger.warning(f"AudD API returned non-success status: {result}")
                    return None

                # Если трек не распознан
                if not result.get('result'):
                    logger.info("Track not recognized by AudD")
                    return None

                track_data = result['result']

                # Парсим информацию о треке
                track_info = TrackInfo(
                    title=track_data.get('title', 'Unknown'),
                    artist=track_data.get('artist', 'Unknown'),
                    album=track_data.get('album'),
                    release_year=track_data.get('release_date', '').split('-')[0] if track_data.get('release_date') else None,
                    cover_url=track_data.get('cover_url') or (
                        track_data.get('apple_music', {}).get('artwork', {}).get('url', '').replace('{w}', '600').replace('{h}', '600')
                        if track_data.get('apple_music') else None
                    ),
                    apple_music_url=track_data.get('apple_music', {}).get('url') if track_data.get('apple_music') else None,
                    spotify_url=track_data.get('spotify', {}).get('external_urls', {}).get('spotify') if track_data.get('spotify') else None,
                )

                logger.info(f"Track recognized: {track_info.artist} - {track_info.title}")
                return track_info

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error during recognition: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error during recognition: {e}")
            return None

    def __del__(self):
        """Деструктор для закрытия сессии."""
        if self.session and not self.session.closed:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.close())
                else:
                    loop.run_until_complete(self.close())
            except Exception:
                pass
