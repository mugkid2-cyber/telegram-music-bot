"""
TikTok downloader - специализированный загрузчик для TikTok.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yt_dlp

from app.media.video import config
from app.media.video.errors import DownloaderError, FileTooLargeError
from app.media.video.platforms.common import Platform

logger = logging.getLogger(__name__)


class TikTokDownloader:
    """Загрузчик видео с TikTok."""

    def __init__(self):
        self.platform = Platform.TIKTOK

    def _base_opts(self) -> dict[str, Any]:
        """Базовые опции для yt-dlp."""
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "restrictfilenames": True,
            "concurrent_fragment_downloads": 8,
            "http_chunk_size": 10485760,  # 10MB
            "buffersize": 16777216,  # 16MB
            "throttledratelimit": None,
        }

        # Добавляем cookies если есть
        cookiefile = config.cookiefile_or_none(config.TIKTOK_COOKIES_FILE)
        if cookiefile:
            opts["cookiefile"] = cookiefile

        return opts

    async def probe(self, url: str) -> dict[str, Any]:
        """Получить метаданные видео без скачивания."""
        try:
            info = await asyncio.to_thread(self._extract_info_sync, url)
        except yt_dlp.utils.DownloadError as exc:
            raise self._map_error(exc) from exc

        if info is None:
            raise DownloaderError("Не удалось получить информацию о видео.")

        # Проверка на карусели/плейлисты
        if info.get("_type") == "playlist" or info.get("entries"):
            raise DownloaderError(
                "Это карусель/слайд-шоу из нескольких файлов — такой формат пока "
                "не поддерживается. Пришлите ссылку на одиночное видео."
            )

        # Проверка длительности
        duration = info.get("duration")
        if duration and config.MAX_DURATION_SECONDS and duration > config.MAX_DURATION_SECONDS:
            raise DownloaderError(
                f"Видео слишком длинное ({int(duration // 60)} мин), "
                f"максимум {config.MAX_DURATION_SECONDS // 60} мин."
            )

        return info

    def _extract_info_sync(self, url: str) -> dict[str, Any]:
        """Синхронное извлечение информации."""
        opts = self._base_opts()
        opts["skip_download"] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False, process=False)

    async def download(
        self,
        url: str,
        workdir: Path,
        format_id: str | None = None,
        extract_audio: bool = False,
    ) -> Path:
        """
        Скачать видео с TikTok.

        Args:
            url: URL видео
            workdir: Рабочая директория для скачивания
            format_id: ID формата (для выбора качества)
            extract_audio: Извлечь только аудио

        Returns:
            Path к скачанному файлу
        """
        extra_opts: dict[str, Any] = {}

        if extract_audio:
            extra_opts["format"] = "bestaudio/best"
            extra_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        elif format_id:
            extra_opts["format"] = format_id
        else:
            # Для TikTok используем best - обычно это уже оптимизированный формат
            extra_opts["format"] = "best"

        try:
            filepath = await asyncio.to_thread(
                self._download_sync, url, workdir, extra_opts
            )
        except yt_dlp.utils.DownloadError as exc:
            raise self._map_error(exc) from exc

        # Проверка размера
        size = filepath.stat().st_size
        if size > config.MAX_FILE_SIZE_BYTES:
            raise FileTooLargeError(size, config.MAX_FILE_SIZE_BYTES)

        return filepath

    def _download_sync(
        self, url: str, workdir: Path, extra_opts: dict[str, Any]
    ) -> Path:
        """Синхронное скачивание."""
        opts = {**self._base_opts(), **extra_opts}
        opts["outtmpl"] = str(workdir / "%(id)s.%(ext)s")

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info.get("entries"):
                info = info["entries"][0]
            filename = Path(ydl.prepare_filename(info))

        # Проверяем, может постпроцессор поменял расширение
        if not filename.exists():
            for ext in [".mp4", ".mp3", ".webm", ".mkv"]:
                candidate = filename.with_suffix(ext)
                if candidate.exists():
                    filename = candidate
                    break

        if not filename.exists():
            raise DownloaderError(f"Файл не найден после скачивания: {filename}")

        return filename

    def _map_error(self, exc: Exception) -> DownloaderError:
        """Преобразует ошибки yt-dlp в понятные сообщения."""
        raw = str(exc)
        msg = raw.lower()
        logger.warning("TikTok yt-dlp error: %s", raw)

        if "login required" in msg or "sign in" in msg:
            return DownloaderError(
                "TikTok требует авторизации. Обновите cookies для TikTok."
            )

        if "video unavailable" in msg or "private" in msg or "removed" in msg:
            return DownloaderError(
                "Видео недоступно: удалено, приватное или гео-заблокировано."
            )

        if "timeout" in msg:
            return DownloaderError(
                "Превышено время ожидания ответа от TikTok, попробуйте ещё раз."
            )

        # Общая ошибка с кратким описанием
        short = raw.strip().splitlines()[-1][:300]
        return DownloaderError(f"Не удалось скачать TikTok. Причина: {short}")
