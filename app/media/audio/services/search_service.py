"""
Оптимизированный сервис поиска музыки с улучшенными результатами.

Улучшения:
1. Умная обработка запросов (исправление опечаток, транслит)
2. Кеширование результатов поиска
3. Улучшенная релевантность
4. Быстрая параллельная загрузка
"""
import asyncio
import hashlib
import logging
from dataclasses import dataclass

import yt_dlp

from app.config import get_settings
from app.utils.ffmpeg import resolve_ffmpeg_location
from app.utils.html_escape import escape_html
from app.utils.lru_cache import LRUCache
from app.media.audio.services.spotify_service import search_spotify

logger = logging.getLogger(__name__)

# Кеш результатов поиска с автоочисткой
_search_cache = LRUCache(max_size=1000, ttl=180)  # 1000 запросов, 3 минуты

PLATFORM_LABELS = {
    "yt": "YouTube",
    "sc": "SoundCloud",
    "sf": "Spotify",
}

PLATFORM_SHORT = {
    "yt": "",
    "sc": "",
    "sf": "",
}

PLATFORM_ICONS = {
    "yt": "🔴",
    "sc": "🟠",
    "sf": "🟢",
}

_CIRCLED_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

# Транслитерация для улучшения поиска
TRANSLIT_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '',
    'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
}


@dataclass(slots=True)
class TrackResult:
    title: str
    source: str
    platform: str
    track_id: str
    duration: int | None
    url: str


def _normalize_for_dedup(title: str) -> str:
    """Нормализует название трека для дедупликации."""
    # Убираем лишние символы и приводим к нижнему регистру
    normalized = title.lower()
    # Убираем распространённые суффиксы
    for suffix in [' (official audio)', ' (official video)', ' (audio)', ' (video)',
                   ' [official audio]', ' [official video]', ' - official audio']:
        normalized = normalized.replace(suffix, '')
    # Убираем лишние пробелы
    normalized = ' '.join(normalized.split())
    return normalized


def _deduplicate_tracks(tracks: list[TrackResult]) -> list[TrackResult]:
    """Удаляет дубликаты треков по нормализованному названию."""
    seen = set()
    unique_tracks = []

    for track in tracks:
        normalized_title = _normalize_for_dedup(track.title)

        if normalized_title not in seen:
            seen.add(normalized_title)
            unique_tracks.append(track)
        else:
            logger.debug(f"Skipping duplicate: {track.title} from {track.platform}")

    return unique_tracks


def normalize_query(query: str) -> str:
    """Нормализует запрос: удаляет лишнее, транслитерирует"""
    query = query.strip().lower()

    # Убираем лишние символы
    query = query.replace("  ", " ")

    # Если запрос на кириллице, добавляем транслит для лучших результатов
    if any(c in TRANSLIT_MAP for c in query):
        translit = ''.join(TRANSLIT_MAP.get(c, c) for c in query)
        # Возвращаем оригинал + транслит
        return f"{query} {translit}"

    return query


def get_cache_key(query: str) -> str:
    """Генерирует ключ кеша для запроса"""
    normalized = normalize_query(query)
    return hashlib.md5(normalized.encode()).hexdigest()


def format_duration(seconds: int) -> str:
    """Форматирует длительность: MM:SS или HH:MM:SS при длине > 1 часа."""
    total = int(seconds)
    if total >= 3600:
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def format_duration_optional(seconds: int | None) -> str:
    if seconds is None:
        return "?:??"
    return format_duration(seconds)


def truncate_text(text: str, max_len: int) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def format_index_badge(index: int) -> str:
    if 1 <= index <= len(_CIRCLED_NUMBERS):
        return _CIRCLED_NUMBERS[index - 1]
    return f"{index}."


def _tracks_count_label(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        word = "трек"
    elif count % 10 in {2, 3, 4} and count % 100 not in {12, 13, 14}:
        word = "трека"
    else:
        word = "треков"
    return f"{count} {word}"


def format_platform_line(track: TrackResult) -> str:
    icon = PLATFORM_ICONS.get(track.platform, "🎵")
    duration = format_duration_optional(track.duration)
    return f"└ ⏱ {duration} {icon}"


def format_search_result_block(
    index: int,
    track: TrackResult,
    max_title_len: int = 42,
) -> str:
    badge = format_index_badge(index)
    icon = PLATFORM_ICONS.get(track.platform, "🎵")
    title = escape_html(truncate_text(track.title, max_title_len))
    duration = format_duration_optional(track.duration)
    return f"{badge} {icon} <b>{title}</b>\n└ ⏱ {duration}"


def format_search_results_message(tracks: list[TrackResult]) -> str:
    count = len(tracks)
    header = f"🎵 Найдено <b>{_tracks_count_label(count)}</b>"
    blocks = [
        format_search_result_block(i, track)
        for i, track in enumerate(tracks, start=1)
    ]
    body = "\n\n".join(blocks)
    footer = "Выберите трек ниже 👇"
    return f"{header}\n\n{body}\n\n{footer}"


def format_button_label(index: int, track: TrackResult, max_len: int = 64) -> str:
    badge = format_index_badge(index)
    prefix = f"{badge} "
    title = truncate_text(track.title, max_len - len(prefix))
    return f"{prefix}{title}"


def _build_ydl_opts() -> dict:
    settings = get_settings()
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "socket_timeout": 10,  # быстрее таймаут
        "ignoreerrors": True,  # не падать на ошибках
    }
    ffmpeg_path = resolve_ffmpeg_location()
    if ffmpeg_path:
        opts["ffmpeg_location"] = ffmpeg_path
    return opts


async def _search_platform_async(query: str, platform: str, limit: int) -> list[TrackResult]:
    """Асинхронный поиск по платформе."""
    if platform == "sf":
        # Spotify через улучшенный YouTube поиск
        try:
            spotify_results = await search_spotify(query, limit)
            results = []
            settings = get_settings()

            for track in spotify_results:
                # Проверяем длительность (может быть None)
                if track.get('duration') and track['duration'] > settings.MAX_DURATION_SECONDS:
                    continue

                results.append(
                    TrackResult(
                        title=track['title'],
                        source="Spotify",
                        platform="sf",
                        track_id=track['track_id'],
                        duration=track.get('duration'),
                        url=track['url'],
                    )
                )
            return results
        except Exception:
            logger.exception("Spotify search failed for: %s", query)
            return []
    else:
        # YouTube и SoundCloud через yt-dlp
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _search_platform_sync, query, platform, limit)


def _search_platform_sync(query: str, platform: str, limit: int) -> list[TrackResult]:
    # Нормализуем запрос для лучших результатов
    normalized_query = normalize_query(query)

    if platform == "yt":
        search_url = f"ytsearch{limit}:{normalized_query}"
        source_label = "YouTube"
        platform_code = "yt"
    else:
        search_url = f"scsearch{limit}:{normalized_query}"
        source_label = "SoundCloud"
        platform_code = "sc"

    results: list[TrackResult] = []

    try:
        with yt_dlp.YoutubeDL(_build_ydl_opts()) as ydl:
            info = ydl.extract_info(search_url, download=False)

        if not info:
            return results

        entries = info.get("entries") or []
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
                if platform_code == "yt":
                    webpage_url = f"https://www.youtube.com/watch?v={track_id}"
                else:
                    continue

            settings = get_settings()
            if duration and duration > settings.MAX_DURATION_SECONDS:
                continue

            results.append(
                TrackResult(
                    title=title,
                    source=source_label,
                    platform=platform_code,
                    track_id=str(track_id),
                    duration=duration,
                    url=webpage_url,
                )
            )
    except Exception:
        logger.exception("Search failed for %s: %s", source_label, query)

    return results


def score_relevance(track: TrackResult, query: str) -> float:
    """Оценивает релевантность трека запросу (чем выше, тем лучше)"""
    title_lower = track.title.lower()
    query_lower = query.lower()

    score = 0.0

    # Точное совпадение = максимальный балл
    if title_lower == query_lower:
        score += 100

    # Начинается с запроса = высокий балл
    if title_lower.startswith(query_lower):
        score += 50

    # Содержит все слова из запроса
    query_words = query_lower.split()
    title_words = title_lower.split()
    matching_words = sum(1 for word in query_words if word in title_words)
    score += matching_words * 10

    # Штраф за ремиксы/каверы (если не указаны в запросе)
    unwanted_markers = ['cover', 'remix', 'instrumental', 'karaoke', 'nightcore']
    if not any(marker in query_lower for marker in unwanted_markers):
        if any(marker in title_lower for marker in unwanted_markers):
            score -= 20

    # Штраф за очень длинные названия (скорее всего плейлисты)
    if len(track.title) > 100:
        score -= 15

    # Приоритет платформ
    if track.platform == 'yt':
        score += 2
    elif track.platform == 'sf':
        score += 1.5
    elif track.platform == 'sc':
        score += 1

    return score


class SearchService:
    async def search(self, query: str) -> list[TrackResult]:
        # Проверяем кеш
        cache_key = get_cache_key(query)
        cached = _search_cache.get(cache_key)
        if cached:
            logger.debug("Using cached search results for: %s", query)
            return cached

        settings = get_settings()
        per_platform = settings.SEARCH_PER_PLATFORM
        limit = settings.SEARCH_RESULTS_LIMIT

        # Параллельный поиск по всем платформам
        youtube_task = _search_platform_async(query, "yt", per_platform)
        soundcloud_task = _search_platform_async(query, "sc", per_platform)
        spotify_task = _search_platform_async(query, "sf", per_platform)

        youtube_results, soundcloud_results, spotify_results = await asyncio.gather(
            youtube_task, soundcloud_task, spotify_task, return_exceptions=True
        )

        # Обработка исключений - показываем частичные результаты
        failed_platforms = []
        if isinstance(youtube_results, Exception):
            logger.error("YouTube search failed: %s", youtube_results)
            youtube_results = []
            failed_platforms.append("YouTube")
        if isinstance(soundcloud_results, Exception):
            logger.error("SoundCloud search failed: %s", soundcloud_results)
            soundcloud_results = []
            failed_platforms.append("SoundCloud")
        if isinstance(spotify_results, Exception):
            logger.error("Spotify search failed: %s", spotify_results)
            spotify_results = []
            failed_platforms.append("Spotify")

        # Логируем, если были проблемы с платформами
        if failed_platforms:
            logger.warning(f"Search completed with errors on: {', '.join(failed_platforms)}")

        # Объединяем все результаты
        all_results = youtube_results + soundcloud_results + spotify_results

        # Если совсем ничего не нашли, возвращаем пустой список
        if not all_results:
            logger.warning(f"No results found for query: {query}")
            return []

        # Сортируем по релевантности
        scored_results = [(score_relevance(track, query), track) for track in all_results]
        scored_results.sort(key=lambda x: x[0], reverse=True)

        # Берём топ-N и удаляем дубликаты
        top_results = [track for score, track in scored_results[:limit * 2]]  # Берём с запасом
        unique_results = _deduplicate_tracks(top_results)
        results = unique_results[:limit]  # Обрезаем до нужного количества

        # Кешируем результаты
        if results:
            _search_cache.set(cache_key, results)

        return results
