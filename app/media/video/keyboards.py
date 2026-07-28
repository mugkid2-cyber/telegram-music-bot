from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .callbacks import CancelCallback, DownloadTypeCallback, QualityCallback


def choose_type_kb(req_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🎵 Аудио (mp3)",
        callback_data=DownloadTypeCallback(req_id=req_id, kind="audio"),
    )
    builder.button(
        text="🎬 Видео (mp4)",
        callback_data=DownloadTypeCallback(req_id=req_id, kind="video"),
    )
    builder.button(text="✖️ Отмена", callback_data=CancelCallback(req_id=req_id))
    builder.adjust(2, 1)
    return builder.as_markup()


def quality_kb(req_id: str, options: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """
    options: список (format_id, подпись_кнопки), например:
    [("auto", "⚡ Авто (макс. доступное качество)"), ("137", "1080p (~42 МБ)"), ...]
    """
    builder = InlineKeyboardBuilder()
    for format_id, label in options:
        builder.button(
            text=label,
            callback_data=QualityCallback(req_id=req_id, format_id=format_id),
        )
    builder.button(text="✖️ Отмена", callback_data=CancelCallback(req_id=req_id))
    builder.adjust(1)
    return builder.as_markup()
