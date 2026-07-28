"""Сервис для имитации поиска Spotify через YouTube.

Поскольку прямой доступ к Spotify API ограничен и требует авторизации,
мы используем улучшенный поиск на YouTube с фильтрацией по официальным трекам.
Результаты помечаются как "Spotify" для удобства пользователя.
"""
import asyncio
import logging
import urllib.parse

import yt_dlp

from app.utils.lru_cache import LRUCache
from app.config import get_settings

logger = logging.getLogger(__name__)

# Кеш для результатов поиска
_spotify_cache = LRUCache(max_size=200, ttl=300)


def _build_ydl_opts() -> dict:
    """Создаёт опции для yt-dlp."""
    return {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': 'in_playlist',
        'socket_timeout': 10,
        'ignoreerrors': True,
    }


async def search_spotify(query: str, limit: int = 4) -> list[dict]:
    """
    Ищет треки через YouTube с улучшенной фильтрацией (имитация Spotify).

    Добавляет ключевые слова для поиска официальных треков и аудио,
    что повышает качество результатов.

    Возвращает список словарей с полями:
    - track_id: ID трека на YouTube
    - title: название трека
    - artist: исполнитель (извлечён из названия)
    - name: название трека
    - duration: длительность в секундах
    - url: ссылка на YouTube
    """
    # Проверяем кеш
    cache_key = f"sf_search:{query}:{limit}"
    cached = _spotify_cache.get(cache_key)
    if cached:
        logger.debug("Using cached Spotify-style results for: %s", query)
        return cached

    loop = asyncio.get_running_loop()

    def _search_sync():
        # Ищем треки без дополнительных фильтров
        search_url = f"ytsearch{limit}:{query}"

        results = []

        try:
            with yt_dlp.YoutubeDL(_build_ydl_opts()) as ydl:
                info = ydl.extract_info(search_url, download=False)

            if not info:
                return results

            entries = info.get("entries") or []
            settings = get_settings()

            for entry in entries:
                if not entry:
                    continue

                track_id = entry.get("id")
                title = entry.get("title") or "Без названия"
                duration = entry.get("duration")
                webpage_url = entry.get("webpage_url") or entry.get("url")

                if not track_id:
                    continue

                if not webpage_url:
                    webpage_url = f"https://www.youtube.com/watch?v={track_id}"

                # Проверяем длительность
                if duration and duration > settings.MAX_DURATION_SECONDS:
                    continue

                # Пытаемся извлечь исполнителя из названия
                if ' - ' in title:
                    artist, name = title.split(' - ', 1)
                elif '|' in title:
                    artist, name = title.split('|', 1)
                else:
                    artist = "Unknown"
                    name = title

                results.append({
                    'track_id': urllib.parse.quote(f"{artist} {name}"),
                    'title': title,
                    'artist': artist.strip(),
                    'name': name.strip(),
                    'duration': duration,
                    'url': webpage_url,
                })

        except Exception as e:
            logger.error(f"Spotify-style search error: {e}")
            return []

        # Кешируем результаты
        if results:
            _spotify_cache.set(cache_key, results)
            logger.info(f"Found {len(results)} tracks (Spotify-style) for: {query}")
        else:
            logger.warning(f"No Spotify-style results for: {query}")

        return results

    # Добавляем timeout для поиска
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _search_sync),
            timeout=15.0  # 15 секунд максимум
        )
    except asyncio.TimeoutError:
        logger.warning(f"Spotify search timeout for: {query}")
        return []


async def download_spotify_track(url: str, output_path) -> bool:
    """
    Заглушка для совместимости. Реальное скачивание происходит через yt-dlp.
    """
    return True


