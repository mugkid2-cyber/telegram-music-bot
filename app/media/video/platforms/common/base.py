"""
Определение платформы по ссылке и извлечение самой ссылки из текста
сообщения (пользователь может прислать ссылку вместе с произвольным
текстом — "глянь видео https://...").
"""
from __future__ import annotations

import re
from enum import Enum, auto


class Platform(Enum):
    TIKTOK = auto()
    YOUTUBE = auto()
    INSTAGRAM = auto()
    UNKNOWN = auto()


_TIKTOK_RE = re.compile(
    r"(https?://)?(www\.|vm\.|vt\.|m\.)?tiktok\.com/[\w@/.\-?=&%]+",
    re.IGNORECASE,
)

_YOUTUBE_RE = re.compile(
    r"(https?://)?(www\.|m\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[\w\-]+",
    re.IGNORECASE,
)

_INSTAGRAM_RE = re.compile(
    r"(https?://)?(www\.|m\.)?instagram\.com/(p|reel|tv)/[\w\-]+",
    re.IGNORECASE,
)

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def extract_url(text: str) -> str | None:
    """Достаёт первую http(s)-ссылку из произвольного текста."""
    if not text:
        return None
    match = _URL_RE.search(text)
    if not match:
        return None
    # отрезаем случайные хвостовые знаки препинания/скобки, которые
    # пользователи иногда лепят рядом со ссылкой
    return match.group(0).rstrip(").,!?»\"'")


def detect_platform(url: str) -> Platform:
    """Определяет платформу по URL."""
    if _TIKTOK_RE.search(url):
        return Platform.TIKTOK
    if _YOUTUBE_RE.search(url):
        return Platform.YOUTUBE
    if _INSTAGRAM_RE.search(url):
        return Platform.INSTAGRAM
    return Platform.UNKNOWN
