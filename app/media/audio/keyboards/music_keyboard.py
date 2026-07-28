from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.media.audio.services.search_service import TrackResult

CALLBACK_PREFIX = "dl"
CALLBACK_SEP = "|"
CANCEL_SEARCH_CALLBACK = "cancel_search"
MAX_CALLBACK_BYTES = 64
MAX_BUTTON_LABEL_LEN = 64

PLATFORM_ICONS = {
    "yt": "🔴",
    "sc": "🟠",
    "sf": "🟢",
}


def _build_callback_data(platform: str, track_id: str) -> str:
    data = f"{CALLBACK_PREFIX}{CALLBACK_SEP}{platform}{CALLBACK_SEP}{track_id}"
    if len(data.encode("utf-8")) <= MAX_CALLBACK_BYTES:
        return data

    max_id_len = MAX_CALLBACK_BYTES - len(
        f"{CALLBACK_PREFIX}{CALLBACK_SEP}{platform}{CALLBACK_SEP}".encode("utf-8")
    )
    trimmed_id = track_id.encode("utf-8")[:max_id_len].decode("utf-8", errors="ignore")
    return f"{CALLBACK_PREFIX}{CALLBACK_SEP}{platform}{CALLBACK_SEP}{trimmed_id}"


def parse_callback_data(data: str) -> tuple[str, str] | None:
    if not data.startswith(f"{CALLBACK_PREFIX}{CALLBACK_SEP}"):
        return None

    parts = data.split(CALLBACK_SEP, 2)
    if len(parts) != 3:
        return None

    _, platform, track_id = parts
    if platform not in {"yt", "sc", "sf"} or not track_id:
        return None

    return platform, track_id


def _format_button_label(track: TrackResult, max_len: int) -> str:
    """Иконка + название трека.

    Заголовок обрезается многоточием, если не влезает в лимит Telegram.
    """
    platform_icon = PLATFORM_ICONS.get(track.platform, "")
    prefix = f"{platform_icon} " if platform_icon else ""

    title = (track.title or "Без названия").strip()
    available = max_len - len(prefix)
    if available < 1:
        return prefix.strip()

    if len(title) > available:
        title = title[: max(available - 1, 1)].rstrip() + "…"

    return f"{prefix}{title}"


def build_search_keyboard(tracks: list[TrackResult]) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=_format_button_label(track, MAX_BUTTON_LABEL_LEN),
                callback_data=_build_callback_data(track.platform, track.track_id),
            )
        ]
        for track in tracks
    ]

    buttons.append(
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=CANCEL_SEARCH_CALLBACK,
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)