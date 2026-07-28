"""
Конфигурация модуля скачивания видео.

Вынесена в отдельный файл, чтобы не путать с основным config.py бота.
Все значения можно переопределить переменными окружения (VD_*),
не трогая код.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Базовые пути
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
COOKIES_DIR = BASE_DIR / "cookies"
TMP_DIR = Path(os.getenv("VD_TMP_DIR", "/tmp/video_downloader"))

TMP_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Лимиты Telegram Bot API.
# У облачного Bot API жёсткий лимит на файлы, отправляемые ботом, — 50 МБ.
# Если вы поднимете свой локальный Bot API сервер, лимит можно увеличить
# до 2000 (2 ГБ) — тогда поменяйте VD_MAX_FILE_SIZE_MB.
# ---------------------------------------------------------------------------
MAX_FILE_SIZE_MB = int(os.getenv("VD_MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Запас на неточность оценки размера файла yt-dlp (filesize_approx часто
# врёт на 5-15%). Планируем скачивание так, будто лимит чуть меньше.
SIZE_SAFETY_MARGIN = 0.92

# Ограничение на длительность видео в секундах. None — без ограничений.
# Полезно, чтобы бот не пытался часами скачивать многочасовой стрим.
MAX_DURATION_SECONDS = int(os.getenv("VD_MAX_DURATION_SECONDS", str(3 * 60 * 60)))

# ---------------------------------------------------------------------------
# Cookies в формате Netscape (экспортируются из браузера залогиненного
# аккаунта). Подробно про получение и частые ошибки — см. README.md рядом.
# ---------------------------------------------------------------------------
# Форсировать конкретный(е) player_client для YouTube (через запятую,
# например "android,web"). По умолчанию пусто — yt-dlp выбирает сам.
# Форсировать вручную стоит только если вы точно знаете, что это помогает
# именно в вашем случае — иначе легко словить необъяснимые ошибки, если
# именно этот клиент временно сломан у YouTube/yt-dlp.
YOUTUBE_PLAYER_CLIENTS = [c.strip() for c in os.getenv("VD_YOUTUBE_PLAYER_CLIENT", "").split(",") if c.strip()]

YOUTUBE_COOKIES_FILE = Path(os.getenv("VD_YOUTUBE_COOKIES", str(COOKIES_DIR / "youtube_cookies.txt")))
TIKTOK_COOKIES_FILE = Path(os.getenv("VD_TIKTOK_COOKIES", str(COOKIES_DIR / "tiktok_cookies.txt")))
INSTAGRAM_COOKIES_FILE = Path(os.getenv("VD_INSTAGRAM_COOKIES", str(COOKIES_DIR / "instagram_cookies.txt")))


def cookiefile_or_none(path: Path) -> str | None:
    """Возвращает путь к cookie-файлу, только если он реально существует и не пуст."""
    return str(path) if path.exists() and path.stat().st_size > 0 else None


# ---------------------------------------------------------------------------
# Прочее
# ---------------------------------------------------------------------------
CAPTION = "Скачано с помощью @Allaince_solo"
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("VD_MAX_CONCURRENT_DOWNLOADS", "3"))
CALLBACK_TTL_SECONDS = 15 * 60  # сколько "живёт" запрос между нажатиями кнопок
USER_DOWNLOAD_COOLDOWN_SECONDS = 5  # анти-спам: минимальный интервал между запросами юзера
