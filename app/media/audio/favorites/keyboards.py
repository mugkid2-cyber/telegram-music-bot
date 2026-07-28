"""Клавиатуры для избранного."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.media.audio.favorites.models import FavoriteTrack

PLATFORM_ICONS = {
    "yt": "🔴",
    "sc": "🟠",
    "sf": "🟢",
}


def build_favorites_menu() -> InlineKeyboardMarkup:
    """Главное меню избранного."""
    buttons = [
        [InlineKeyboardButton(text="📋 Все треки", callback_data="fav_show_all")],
        [InlineKeyboardButton(text="🎲 Случайный трек", callback_data="fav_random")],
        [InlineKeyboardButton(text="🗑 Удалить всё", callback_data="fav_clear_step1")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="fav_close")],
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_favorites_list(
    favorites: list[FavoriteTrack],
    page: int = 0,
    per_page: int = 8,
    filter_platform: str = None,
    show_back: bool = True
) -> InlineKeyboardMarkup:
    """Список избранных треков."""
    start = page * per_page
    end = start + per_page
    page_favorites = favorites[start:end]

    buttons = []

    # Треки
    for fav in page_favorites:
        icon = PLATFORM_ICONS.get(fav.platform, "🎵")
        # Компактный формат
        title = fav.title if len(fav.title) <= 35 else fav.title[:32] + "..."

        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} {title}",
                callback_data=f"fav_play|{fav.platform}|{fav.track_id}"
            )
        ])

    # Пагинация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️", callback_data=f"fav_page|{page - 1}|{filter_platform or 'all'}")
        )

    # Показываем текущую страницу
    total_pages = (len(favorites) + per_page - 1) // per_page
    if total_pages > 1:
        nav_buttons.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="fav_noop")
        )

    if end < len(favorites):
        nav_buttons.append(
            InlineKeyboardButton(text="▶️", callback_data=f"fav_page|{page + 1}|{filter_platform or 'all'}")
        )

    if nav_buttons:
        buttons.append(nav_buttons)

    # Кнопки управления
    control_buttons = []
    if show_back:
        control_buttons.append(
            InlineKeyboardButton(text="🏠 Меню", callback_data="fav_menu")
        )
    control_buttons.append(
        InlineKeyboardButton(text="❌ Закрыть", callback_data="fav_close")
    )
    buttons.append(control_buttons)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_clear_confirmation_step1() -> InlineKeyboardMarkup:
    """Первое подтверждение очистки избранного."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗑 Да, удалить всё", callback_data="fav_clear_step2"),
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="fav_menu"),
        ]
    ])


def build_clear_confirmation_step2() -> InlineKeyboardMarkup:
    """Второе подтверждение очистки избранного."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ УДАЛИТЬ ВСЁ", callback_data="fav_clear_yes"),
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="fav_menu"),
        ]
    ])


def build_track_actions(platform: str, track_id: str, in_favorites: bool = True) -> InlineKeyboardMarkup:
    """Действия с треком."""
    buttons = []

    if in_favorites:
        buttons.append([
            InlineKeyboardButton(text="🗑 Удалить из избранного", callback_data=f"fav_remove|{platform}|{track_id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="⭐ Добавить в избранное", callback_data=f"fav_add|{platform}|{track_id}")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_delete_confirmation(platform: str, track_id: str) -> InlineKeyboardMarkup:
    """Подтверждение удаления трека."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"fav_confirm_del|{platform}|{track_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"fav_cancel_del|{platform}|{track_id}")
        ]
    ])
