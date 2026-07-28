import asyncio
import logging
import tempfile
import time
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import aiofiles.os
import yt_dlp
from yt_dlp.utils import DownloadError

from app.config import get_settings
from app.utils.ffmpeg import convert_image_to_jpg, resolve_ffmpeg_location
from app.utils.security import sanitize_track_id, validate_file_path
from app.utils.retry import sync_retry_with_backoff
from app.utils.lru_cache import LRUCache

logger = logging.getLogger(__name__)

# Кеш метаданных с автоочисткой
_info_cache = LRUCache(max_size=500, ttl=300)  # 500 треков, 5 минут
_MAX_LOCKS = 500  # Максимум locks


class TrackTooLongError(Exception):
    def __init__(self, duration: int, limit: int) -> None:
        self.duration = duration
        self.limit = limit
        super().__init__(f"Track duration {duration}s exceeds limit {limit}s")


class VideoUnavailableError(Exception):
    pass


@dataclass(slots=True)
class DownloadedTrack:
    file_path: Path
    title: str
    performer: str
    duration: int | None
    thumbnail_path: Path | None
    source: str
    track_id: str
    is_cached: bool = False


def _split_title_performer(title: str) -> tuple[str, str]:
    separators = [" - ", " – ", " — ", " | "]
    for separator in separators:
        if separator in title:
            artist, name = title.split(separator, 1)
            return name.strip(), artist.strip()
    return title.strip(), ""


def _resolve_url(platform: str, track_id: str, url: str | None = None) -> str:
    if url:
        return url
    if platform == "yt":
        return f"https://www.youtube.com/watch?v={track_id}"
    if platform == "sc":
        # SoundCloud треки должны иметь полный URL
        return f"https://soundcloud.com/{track_id}"
    if platform == "sf":
        # Для Spotify track_id это на самом деле YouTube поисковый запрос
        return f"ytsearch1:{track_id}"
    raise ValueError(
        f"URL для трека {track_id} (платформа: {platform}) не найден. Повторите поиск."
    )


def _base_ydl_opts() -> dict:
    """Общие опции yt-dlp. Куки из браузера подключаются только если явно
    заданы в настройках — на сервере без браузера это иначе всегда падает."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 15,
        "retries": 3,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        # SPEED OPTIMIZATIONS:
        "concurrent_fragment_downloads": 8,  # параллельное скачивание фрагментов
        "http_chunk_size": 10485760,  # 10MB чанки для лучшей скорости
        "buffersize": 16777216,  # 16MB буфер
        "throttledratelimit": None,  # без ограничения скорости
    }

    ffmpeg_path = resolve_ffmpeg_location()
    if ffmpeg_path:
        opts["ffmpeg_location"] = ffmpeg_path

    settings = get_settings()
    cookies_browser = getattr(settings, "YTDLP_COOKIES_FROM_BROWSER", None)
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    cookies_file = getattr(settings, "YTDLP_COOKIES_FILE", None)
    if cookies_file:
        opts["cookiefile"] = cookies_file

    return opts


@sync_retry_with_backoff(
    max_retries=3,
    initial_delay=2.0,
    exceptions=(DownloadError, ConnectionError, TimeoutError)
)
def _extract_info(url: str) -> dict:
    # Проверяем кеш
    cached = _info_cache.get(url)
    if cached:
        logger.debug("Using cached metadata for %s", url)
        return cached

    opts = _base_ydl_opts()
    opts["skip_download"] = True

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        message = str(exc).lower()
        if "unavailable" in message or "private" in message or "removed" in message:
            raise VideoUnavailableError(str(exc)) from exc
        raise

    if not info:
        raise VideoUnavailableError(f"Не удалось получить информацию о треке: {url}")

    # плейлист/подборка вместо одиночного трека
    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        if not entries:
            raise VideoUnavailableError(f"Пустой плейлист: {url}")
        info = entries[0]

    # Кешируем результат
    _info_cache.set(url, info)

    return info


def _find_cached(cache_dir: Path, track_id: str) -> Path | None:
    # Validate track_id to prevent path traversal
    safe_track_id = sanitize_track_id(track_id)
    candidate = cache_dir / f"{safe_track_id}.mp3"

    # Ensure result is within cache_dir
    try:
        validate_file_path(candidate, cache_dir)
    except ValueError:
        logger.warning("Invalid cache path for track_id=%s", track_id)
        return None

    return candidate if candidate.exists() else None


def _download_sync(
    url: str,
    output_dir: Path,
    platform: str,
    track_id: str,
) -> DownloadedTrack:
    # Validate track_id early to prevent path traversal
    safe_track_id = sanitize_track_id(track_id)

    settings = get_settings()
    output_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = settings.DOWNLOAD_DIR / "cache" / platform
    cache_dir.mkdir(parents=True, exist_ok=True)
    final_path = cache_dir / f"{safe_track_id}.mp3"
    cached_thumb = cache_dir / f"{safe_track_id}.jpg"

    # Validate paths are within cache_dir
    validate_file_path(final_path, cache_dir)
    validate_file_path(cached_thumb, cache_dir)

    # Уже скачано ранее — не дёргаем сеть повторно.
    cached_audio = _find_cached(cache_dir, safe_track_id)
    if cached_audio is not None:
        info = _extract_info(url)
        title = info.get("title") or info.get("track") or "Unknown"
        track_name, performer = _split_title_performer(title)
        if info.get("artist") and not performer:
            performer = info["artist"]
        if info.get("track"):
            track_name = info["track"]

        return DownloadedTrack(
            file_path=cached_audio,
            title=track_name,
            performer=performer,
            duration=info.get("duration"),
            thumbnail_path=cached_thumb if cached_thumb.exists() else None,
            source=platform,
            track_id=safe_track_id,
            is_cached=True,
        )

    info = _extract_info(url)
    duration = info.get("duration")
    if duration and duration > settings.MAX_DURATION_SECONDS:
        raise TrackTooLongError(duration, settings.MAX_DURATION_SECONDS)

    title = info.get("title") or info.get("track") or "Unknown"
    track_name, performer = _split_title_performer(title)
    if info.get("artist") and not performer:
        performer = info["artist"]
    if info.get("track"):
        track_name = info["track"]

    ydl_opts = _base_ydl_opts()
    ydl_opts.update(
        {
            "format": "bestaudio[ext=opus]/bestaudio[ext=m4a]/bestaudio/best",  # приоритет быстрых форматов
            "outtmpl": str(output_dir / f"{safe_track_id}.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": settings.MP3_BITRATE,
                }
            ],
            "postprocessor_args": [
                "-threads", "0",  # используем все CPU ядра
            ],
            "writethumbnail": True,
            "embedthumbnail": False,
        }
    )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadError as exc:
        message = str(exc).lower()
        if "unavailable" in message or "private" in message:
            raise VideoUnavailableError(str(exc)) from exc
        if "ffmpeg" in message:
            raise RuntimeError("Ошибка конвертации ffmpeg") from exc
        raise

    downloaded_files = list(output_dir.glob(f"{safe_track_id}.*"))
    audio_file: Path | None = None
    thumbnail_path: Path | None = None

    for file_path in downloaded_files:
        if file_path.suffix.lower() == ".mp3":
            audio_file = file_path
        elif file_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            thumbnail_path = file_path

    if audio_file is None:
        mp3_candidates = list(output_dir.glob("*.mp3"))
        if not mp3_candidates:
            raise RuntimeError("Не удалось найти скачанный MP3-файл")
        audio_file = mp3_candidates[0]

    if final_path.exists():
        final_path.unlink()
    audio_file.rename(final_path)

    persisted_thumbnail: Path | None = None
    if thumbnail_path and thumbnail_path.exists():
        persisted_thumbnail = convert_image_to_jpg(thumbnail_path, cached_thumb)

    for leftover in output_dir.glob("*"):
        if leftover.is_file():
            leftover.unlink(missing_ok=True)

    return DownloadedTrack(
        file_path=final_path,
        title=track_name,
        performer=performer,
        duration=duration,
        thumbnail_path=persisted_thumbnail,
        source=platform,
        track_id=track_id,
        is_cached=False,
    )


class DownloadService:
    def __init__(self) -> None:
        # По одному замку на трек, чтобы параллельные запросы одного и того
        # же track_id не качали его одновременно и не топтали друг друга.
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_access_time: dict[str, float] = {}
        self._locks_mutex = threading.Lock()  # Защита от race condition

    def _get_lock(self, lock_key: str) -> asyncio.Lock:
        """Получает или создаёт lock с автоочисткой (thread-safe)."""
        with self._locks_mutex:
            # Очистка старых locks
            if len(self._locks) > _MAX_LOCKS:
                now = time.time()
                expired = [
                    k for k, last_use in self._lock_access_time.items()
                    if now - last_use > 600  # 10 минут без использования
                ]
                for k in expired[:100]:  # Удаляем максимум 100 за раз
                    self._locks.pop(k, None)
                    self._lock_access_time.pop(k, None)
                if expired:
                    logger.debug("Cleaned up %d unused locks", len(expired[:100]))

            if lock_key not in self._locks:
                self._locks[lock_key] = asyncio.Lock()

            self._lock_access_time[lock_key] = time.time()
            return self._locks[lock_key]

    async def download(
        self,
        platform: str,
        track_id: str,
        url: str | None = None,
    ) -> DownloadedTrack:
        resolved_url = _resolve_url(platform, track_id, url)
        lock_key = f"{platform}:{track_id}"
        lock = self._get_lock(lock_key)

        temp_dir = None
        try:
            async with lock:
                temp_dir = Path(tempfile.mkdtemp(prefix="music_bot_"))
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None, _download_sync, resolved_url, temp_dir, platform, track_id
                )
        except Exception:
            logger.exception(
                "Ошибка скачивания трека platform=%s track_id=%s", platform, track_id
            )
            raise
        finally:
            if temp_dir:
                await self._cleanup_dir(temp_dir)

    async def cleanup_temp(self, *paths: Path) -> None:
        for path in paths:
            if not path.exists():
                continue
            parent = path.parent
            if parent.name.startswith("music_bot_"):
                await self._cleanup_dir(parent)
            elif path.parent.name == "cache":
                continue
            else:
                try:
                    await aiofiles.os.remove(path)
                except OSError:
                    logger.warning("Failed to remove temp file: %s", path)

    async def _cleanup_dir(self, directory: Path) -> None:
        if not directory.exists():
            return
        for item in directory.iterdir():
            try:
                if item.is_file():
                    await aiofiles.os.remove(item)
            except OSError:
                logger.warning("Failed to remove: %s", item)
        try:
            directory.rmdir()
        except OSError:
            logger.warning("Failed to remove directory: %s", directory)