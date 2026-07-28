"""
YouTube downloader - специализированный загрузчик для YouTube.
Поддерживает:
- Обычные видео
- YouTube Shorts
- Выбор качества
- Извлечение аудио
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yt_dlp

from app.media.video import config
from app.media.video.errors import (
    DownloaderError,
    FileTooLargeError,
    LoginRequiredError,
    VideoUnavailableError,
)
from app.media.video.platforms.common import Platform

logger = logging.getLogger(__name__)


class YouTubeDownloader:
    """Загрузчик видео с YouTube."""

    def __init__(self):
        self.platform = Platform.YOUTUBE

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
            # YouTube специфичные опции
            "nocheckcertificate": True,
            "age_limit": None,
        }

        # Добавляем cookies если есть
        cookiefile = config.cookiefile_or_none(config.YOUTUBE_COOKIES_FILE)
        if cookiefile:
            opts["cookiefile"] = cookiefile

        # Player clients если заданы
        if config.YOUTUBE_PLAYER_CLIENTS:
            opts["extractor_args"] = {
                "youtube": {"player_client": config.YOUTUBE_PLAYER_CLIENTS}
            }

        return opts

    async def probe(self, url: str) -> dict[str, Any]:
        """Получить метаданные видео без скачивания."""
        try:
            info = await asyncio.to_thread(self._extract_info_sync, url)
        except yt_dlp.utils.DownloadError as exc:
            raise self._map_error(exc) from exc

        if info is None:
            raise VideoUnavailableError("Не удалось получить информацию о видео.")

        # Проверка на плейлисты
        if info.get("_type") == "playlist" or info.get("entries"):
            raise DownloaderError(
                "Это плейлист. Пожалуйста, пришлите ссылку на одиночное видео."
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
        Скачать видео с YouTube.

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
            # YouTube часто требует объединения видео+аудио
            extra_opts["format"] = f"{format_id}+bestaudio/best"
            extra_opts["merge_output_format"] = "mp4"
        else:
            # Автоматический выбор лучшего качества в пределах лимита
            # bestvideo+bestaudio/best - объединяет лучшее видео с лучшим аудио
            extra_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            extra_opts["merge_output_format"] = "mp4"

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

    def list_qualities(self, info: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Список доступных качеств видео.

        Returns:
            Список словарей с format_id, label, height, estimated_size
        """
        duration = info.get("duration")
        limit = int(config.MAX_FILE_SIZE_BYTES * config.SIZE_SAFETY_MARGIN)

        best_per_height: dict[int, dict[str, Any]] = {}

        for fmt in info.get("formats", []):
            # Только видео форматы
            if fmt.get("vcodec") in (None, "none"):
                continue

            height = fmt.get("height")
            if not height:
                continue

            # Оценка размера
            size = self._estimate_size(fmt, duration)
            if size is not None and size > limit:
                continue

            # Берём лучший формат для каждой высоты
            existing = best_per_height.get(height)
            if existing is None or (existing.get("estimated_size") is None and size is not None):
                size_label = f" (~{size // (1024 * 1024)} МБ)" if size else ""
                best_per_height[height] = {
                    "format_id": str(fmt["format_id"]),
                    "label": f"{height}p{size_label}",
                    "height": height,
                    "estimated_size": size,
                }

        # Сортируем по качеству (от большего к меньшему)
        options = sorted(
            best_per_height.values(),
            key=lambda o: o.get("height") or 0,
            reverse=True,
        )

        return options[:5]  # Топ-5 качеств

    def _estimate_size(self, fmt: dict[str, Any], duration: float | None) -> int | None:
        """Оценка размера файла."""
        size = fmt.get("filesize") or fmt.get("filesize_approx")
        if size:
            return int(size)

        tbr = fmt.get("tbr")  # Битрейт в Кбит/с
        if tbr and duration:
            return int(tbr * 1000 / 8 * duration)

        return None

    def _map_error(self, exc: Exception) -> DownloaderError:
        """Преобразует ошибки yt-dlp в понятные сообщения."""
        raw = str(exc)
        msg = raw.lower()
        logger.warning("YouTube yt-dlp error: %s", raw)

        # Проверка на бота / требование авторизации
        login_markers = (
            "sign in to confirm",
            "confirm you're not a bot",
            "confirm you are not a bot",
            "login required",
            "not a bot",
        )
        if any(m in msg for m in login_markers):
            return LoginRequiredError(
                "YouTube требует подтверждения, что вы не бот. "
                "Обновите cookies для YouTube — см. README.md."
            )

        # Видео недоступно
        unavailable_markers = (
            "video unavailable",
            "this video is not available",
            "this video has been removed",
            "video is private",
            "private video",
            "has been removed by the uploader",
            "video does not exist",
        )
        if any(m in msg for m in unavailable_markers):
            return VideoUnavailableError(
                "Видео недоступно: удалено, приватное или гео-заблокировано."
            )

        if "timeout" in msg:
            return DownloaderError(
                "Превышено время ожидания ответа от YouTube, попробуйте ещё раз."
            )

        if "requested format is not available" in msg:
            return DownloaderError(
                "Не нашлось подходящего формата видео. "
                "Попробуйте обновить yt-dlp или добавить cookies."
            )

        # Общая ошибка
        short = raw.strip().splitlines()[-1][:300]
        return DownloaderError(f"Не удалось скачать YouTube видео. Причина: {short}")
