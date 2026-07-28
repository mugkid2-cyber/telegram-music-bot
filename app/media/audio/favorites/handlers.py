"""Хендлеры избранного."""
import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramAPIError

from app.media.audio.favorites.db import FavoritesDB
from app.media.audio.favorites.keyboards import (
    build_favorites_list,
    build_favorites_menu,
    build_clear_confirmation_step1,
    build_clear_confirmation_step2,
    build_delete_confirmation,
)
from app.media.audio.favorites.models import FavoriteTrack
from app.media.audio.services.download_service import (
    DownloadService,
    VideoUnavailableError,
)
from app.media.audio.services.cache_service import CacheService
from app.utils.html_escape import escape_html

# Импорт метаданных из music handler
from app.media.audio.handlers import music

logger = logging.getLogger(__name__)

router = Router(name="favorites")

favorites_db = FavoritesDB()
download_service = DownloadService()
cache_service = CacheService()

# Хранилище временных данных для добавления в избранное (message_id -> track_info)
_pending_favorites = {}


@router.message(Command("fav", "избранное"))
async def show_favorites(message: Message):
    """Показать главное меню избранного."""
    user_id = message.from_user.id

    count = await favorites_db.count_favorites(user_id)

    if count == 0:
        await message.reply(
            "📭 <b>Ваше избранное пусто</b>\n\n"
            "Добавляйте треки:\n"
            "• Нажмите <b>⭐ Добавить в избранное</b> под треком\n"
            "• Ответьте <code>+</code> на любой аудиофайл"
        )
        return

    from app.media.audio.favorites.keyboards import build_favorites_menu

    keyboard = build_favorites_menu()

    await message.reply(
        f"⭐ <b>Ваше избранное</b>\n\n"
        f"📊 Всего треков: <b>{count}</b>\n\n"
        f"Выберите действие:",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "fav_menu")
async def handle_back_to_menu(callback: CallbackQuery):
    """Вернуться в главное меню избранного."""
    user_id = callback.from_user.id
    count = await favorites_db.count_favorites(user_id)

    if count == 0:
        await callback.message.edit_text(
            "📭 <b>Ваше избранное пусто</b>\n\n"
            "Добавляйте треки через кнопку ⭐ под треками"
        )
        await callback.answer()
        return

    keyboard = build_favorites_menu()

    try:
        await callback.message.edit_text(
            f"⭐ <b>Ваше избранное</b>\n\n"
            f"📊 Всего треков: <b>{count}</b>\n\n"
            f"Выберите действие:",
            reply_markup=keyboard
        )
    except TelegramAPIError:
        pass

    await callback.answer()


@router.callback_query(F.data == "fav_show_all")
async def handle_show_all(callback: CallbackQuery):
    """Показать все треки."""
    user_id = callback.from_user.id
    favorites = await favorites_db.get_user_favorites(user_id, limit=1000)

    if not favorites:
        await callback.answer("📭 Нет треков", show_alert=True)
        return

    keyboard = build_favorites_list(favorites, page=0)

    try:
        await callback.message.edit_text(
            f"📋 <b>Все треки</b> ({len(favorites)})\n\n"
            f"Нажмите на трек для воспроизведения:",
            reply_markup=keyboard
        )
    except TelegramAPIError:
        pass

    await callback.answer()


@router.callback_query(F.data.startswith("fav_filter|"))
async def handle_filter(callback: CallbackQuery):
    """Фильтр по платформе."""
    platform = callback.data.split("|")[1]
    user_id = callback.from_user.id

    all_favs = await favorites_db.get_user_favorites(user_id, limit=1000)
    filtered = [f for f in all_favs if f.platform == platform]

    if not filtered:
        platform_names = {"yt": "YouTube", "sc": "SoundCloud", "sf": "Spotify"}
        await callback.answer(f"Нет треков с {platform_names.get(platform, platform)}", show_alert=True)
        return

    keyboard = build_favorites_list(filtered, page=0, filter_platform=platform)

    platform_icons = {"yt": "🔴 YouTube", "sc": "🟠 SoundCloud", "sf": "🟢 Spotify"}

    try:
        await callback.message.edit_text(
            f"{platform_icons.get(platform, platform)} <b>({len(filtered)})</b>\n\n"
            f"Нажмите на трек для воспроизведения:",
            reply_markup=keyboard
        )
    except TelegramAPIError:
        pass

    await callback.answer()


@router.callback_query(F.data == "fav_random")
async def handle_random(callback: CallbackQuery, bot: Bot):
    """Случайный трек из избранного."""
    import random

    user_id = callback.from_user.id
    favorites = await favorites_db.get_user_favorites(user_id, limit=1000)

    if not favorites:
        await callback.answer("📭 Нет треков", show_alert=True)
        return

    # Выбираем случайный трек
    random_track = random.choice(favorites)

    await callback.answer(f"🎲 {random_track.title}")

    # Воспроизводим
    chat_id = callback.message.chat.id

    # Используем существующую логику воспроизведения
    # Создаём фейковый callback для переиспользования кода
    fake_data = f"fav_play|{random_track.platform}|{random_track.track_id}"
    fake_callback = type('obj', (object,), {
        'data': fake_data,
        'from_user': callback.from_user,
        'message': callback.message,
        'answer': callback.answer
    })()

    await handle_play_favorite(fake_callback, bot)


@router.callback_query(F.data == "fav_recent")
async def handle_recent(callback: CallbackQuery):
    """Последние 10 добавленных треков."""
    user_id = callback.from_user.id
    favorites = await favorites_db.get_user_favorites(user_id, limit=10)

    if not favorites:
        await callback.answer("📭 Нет треков", show_alert=True)
        return

    keyboard = build_favorites_list(favorites, page=0, per_page=10, show_back=True)

    try:
        await callback.message.edit_text(
            f"🔥 <b>Последние треки</b> ({len(favorites)})\n\n"
            f"Нажмите на трек для воспроизведения:",
            reply_markup=keyboard
        )
    except TelegramAPIError:
        pass

    await callback.answer()


@router.callback_query(F.data == "fav_clear_step1")
async def handle_clear_step1(callback: CallbackQuery):
    """Первое подтверждение очистки."""
    keyboard = build_clear_confirmation_step1()

    try:
        await callback.message.edit_text(
            "⚠️ <b>Удалить все треки?</b>\n\n"
            "Это действие нельзя отменить!",
            reply_markup=keyboard
        )
    except TelegramAPIError:
        pass

    await callback.answer()


@router.callback_query(F.data == "fav_clear_step2")
async def handle_clear_step2(callback: CallbackQuery):
    """Второе подтверждение очистки."""
    keyboard = build_clear_confirmation_step2()

    try:
        await callback.message.edit_text(
            "🚨 <b>ПОСЛЕДНЕЕ ПРЕДУПРЕЖДЕНИЕ</b>\n\n"
            "Все треки будут удалены безвозвратно!\n"
            "Вы уверены?",
            reply_markup=keyboard
        )
    except TelegramAPIError:
        pass

    await callback.answer()


@router.callback_query(F.data == "fav_clear_yes")
async def handle_clear_yes(callback: CallbackQuery):
    """Очистка избранного."""
    user_id = callback.from_user.id

    # Удаляем все треки
    all_favs = await favorites_db.get_user_favorites(user_id, limit=10000)
    deleted = 0

    for fav in all_favs:
        if await favorites_db.remove(user_id, fav.platform, fav.track_id):
            deleted += 1

    try:
        await callback.message.edit_text(
            f"✅ <b>Очищено</b>\n\n"
            f"Удалено треков: {deleted}"
        )
    except TelegramAPIError:
        pass

    await callback.answer(f"🗑 Удалено {deleted} треков")


@router.callback_query(F.data.startswith("fav_del|"))
async def handle_quick_delete(callback: CallbackQuery):
    """Быстрое удаление трека из списка."""
    parts = callback.data.split("|")
    if len(parts) != 3:
        await callback.answer("❌ Ошибка")
        return

    _, platform, track_id = parts
    user_id = callback.from_user.id

    removed = await favorites_db.remove(user_id, platform, track_id)

    if removed:
        await callback.answer("🗑 Удалено", show_alert=False)

        # Обновляем список
        favorites = await favorites_db.get_user_favorites(user_id, limit=1000)

        if not favorites:
            try:
                await callback.message.edit_text(
                    "📭 <b>Избранное пусто</b>\n\n"
                    "Добавляйте треки через кнопку ⭐"
                )
            except TelegramAPIError:
                pass
        else:
            keyboard = build_favorites_list(favorites, page=0)
            try:
                await callback.message.edit_reply_markup(reply_markup=keyboard)
            except TelegramAPIError:
                pass
    else:
        await callback.answer("❌ Не найдено")


@router.callback_query(F.data.startswith("fav_confirm_del|"))
async def handle_confirm_delete(callback: CallbackQuery):
    """Подтверждение удаления трека."""
    parts = callback.data.split("|")
    if len(parts) != 3:
        await callback.answer("❌ Ошибка")
        return

    _, platform, track_id = parts
    user_id = callback.from_user.id

    removed = await favorites_db.remove(user_id, platform, track_id)

    if removed:
        await callback.answer("🗑 Трек удалён из избранного", show_alert=True)

        # Убираем кнопки под треком
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            pass
    else:
        await callback.answer("❌ Трек не найден в избранном", show_alert=True)


@router.callback_query(F.data.startswith("fav_cancel_del|"))
async def handle_cancel_delete(callback: CallbackQuery):
    """Отмена удаления трека."""
    await callback.answer("❌ Отменено")

    # Убираем кнопки под треком
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError:
        pass


@router.callback_query(F.data == "fav_noop")
async def handle_noop(callback: CallbackQuery):
    """Пустой callback для индикатора страницы."""
    await callback.answer()


@router.callback_query(F.data.startswith("fav_play|"))
async def handle_play_favorite(callback: CallbackQuery, bot: Bot):
    """Воспроизвести трек из избранного."""
    parts = callback.data.split("|")
    if len(parts) != 3:
        await callback.answer("❌ Неверные данные")
        return

    _, platform, track_id = parts
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    await callback.answer("⏳ Подготовка трека...")

    # Получаем трек из БД
    favorites = await favorites_db.get_user_favorites(user_id, limit=100)
    favorite = next((f for f in favorites if f.platform == platform and f.track_id == track_id), None)

    if not favorite:
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Трек не найден в избранном"
        )
        return

    # Проверяем кеш
    cached = await cache_service.get(platform, track_id)

    try:
        if cached:
            # Отправляем из кеша
            from aiogram.types import FSInputFile
            from pathlib import Path

            audio_file = FSInputFile(cached.file_path)
            cached_thumb = Path(cached.file_path).with_suffix(".jpg")
            thumb = FSInputFile(cached_thumb) if cached_thumb.exists() else None

            # Создаём клавиатуру с кнопкой удаления
            from app.media.audio.favorites.keyboards import build_delete_confirmation
            keyboard = build_delete_confirmation(platform, track_id)

            await bot.send_audio(
                chat_id=chat_id,
                audio=audio_file,
                title=cached.title[:64],
                performer=getattr(cached, 'performer', '')[:64] if hasattr(cached, 'performer') else '',
                thumbnail=thumb,
                reply_markup=keyboard
            )
        else:
            # Скачиваем заново
            status = await bot.send_message(
                chat_id=chat_id,
                text="⬇️ Скачивание..."
            )

            # Если нет URL - ищем трек заново по названию
            url = favorite.url
            if not url or url == "":
                await status.edit_text("🔍 Поиск трека...")

                # Формируем поисковый запрос
                search_query = f"{favorite.performer} {favorite.title}" if favorite.performer else favorite.title

                # Ищем через SearchService
                from app.media.audio.services.search_service import SearchService
                search_service = SearchService()

                try:
                    search_results = await search_service.search(search_query)

                    if not search_results:
                        await status.edit_text(f"❌ Не удалось найти трек: {escape_html(search_query)}")
                        return

                    # Берём первый результат с той же платформы, или любой первый
                    track_result = next((t for t in search_results if t.platform == platform), search_results[0])
                    url = track_result.url
                    track_id = track_result.track_id
                    platform = track_result.platform

                    await status.edit_text("⬇️ Скачивание...")
                except Exception as e:
                    logger.exception(f"Search failed for favorite: {search_query}")
                    await status.edit_text(f"❌ Ошибка поиска трека")
                    return

            try:
                track = await download_service.download(platform, track_id, url=url)

                # Сохраняем в кеш
                await cache_service.save(
                    source=platform,
                    track_id=track_id,
                    title=track.title,
                    file_path=str(track.file_path),
                )

                await status.delete()

                from aiogram.types import FSInputFile
                audio_file = FSInputFile(str(track.file_path))
                thumb = FSInputFile(str(track.thumbnail_path)) if track.thumbnail_path else None

                # Создаём клавиатуру с кнопкой удаления
                from app.media.audio.favorites.keyboards import build_delete_confirmation
                keyboard = build_delete_confirmation(platform, track_id)

                await bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_file,
                    title=track.title[:64],
                    performer=track.performer[:64] if track.performer else '',
                    duration=track.duration,
                    thumbnail=thumb,
                    reply_markup=keyboard
                )
            except VideoUnavailableError:
                # Видео недоступно - пробуем найти другую версию
                await status.edit_text("🔍 Видео недоступно, ищу другую версию...")

                search_query = f"{favorite.performer} {favorite.title}" if favorite.performer else favorite.title

                from app.media.audio.services.search_service import SearchService
                search_service = SearchService()

                try:
                    search_results = await search_service.search(search_query)

                    if not search_results:
                        await status.edit_text("❌ Не удалось найти альтернативную версию")
                        return

                    # Пробуем другую платформу
                    for result in search_results:
                        if result.platform != platform or result.track_id != track_id:
                            try:
                                await status.edit_text("⬇️ Скачивание альтернативной версии...")
                                track = await download_service.download(result.platform, result.track_id, url=result.url)

                                await cache_service.save(
                                    source=result.platform,
                                    track_id=result.track_id,
                                    title=track.title,
                                    file_path=str(track.file_path),
                                )

                                await status.delete()

                                from aiogram.types import FSInputFile
                                audio_file = FSInputFile(str(track.file_path))
                                thumb = FSInputFile(str(track.thumbnail_path)) if track.thumbnail_path else None

                                # Создаём клавиатуру с кнопкой удаления
                                from app.media.audio.favorites.keyboards import build_delete_confirmation
                                keyboard = build_delete_confirmation(result.platform, result.track_id)

                                await bot.send_audio(
                                    chat_id=chat_id,
                                    audio=audio_file,
                                    title=track.title[:64],
                                    performer=track.performer[:64] if track.performer else '',
                                    duration=track.duration,
                                    thumbnail=thumb,
                                    reply_markup=keyboard
                                )
                                return
                            except:
                                continue

                    await status.edit_text("❌ Не удалось найти рабочую версию трека")

                except Exception:
                    logger.exception("Failed to find alternative version")
                    await status.edit_text("❌ Ошибка поиска альтернативной версии")

            except Exception as e:
                logger.exception(f"Failed to download: {platform}:{track_id}")
                await status.edit_text("❌ Ошибка скачивания")

    except Exception:
        logger.exception(f"Failed to play favorite: {platform}:{track_id}")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Не удалось воспроизвести трек"
        )


@router.callback_query(F.data == "fav_close")
async def handle_close_favorites(callback: CallbackQuery):
    """Закрыть список избранного."""
    try:
        await callback.message.delete()
    except TelegramAPIError:
        pass
    await callback.answer()


@router.message(F.text.in_(["+", "+"]), F.reply_to_message)
async def add_to_favorites_trigger(message: Message):
    """Добавить трек в избранное по триггеру +."""
    if not message.reply_to_message or not message.reply_to_message.audio:
        return

    replied_message_id = message.reply_to_message.message_id
    user_id = message.from_user.id

    # Пытаемся получить метаданные из music handler
    metadata = music._sent_tracks_metadata.get(replied_message_id)

    if metadata:
        # Есть метаданные - сохраняем с полной информацией
        favorite = FavoriteTrack(
            user_id=user_id,
            platform=metadata['platform'],
            track_id=metadata['track_id'],
            title=metadata['title'],
            performer=metadata['performer'],
            url=metadata['url'],
            added_at=datetime.now()
        )
    else:
        # Нет метаданных - используем данные из audio
        audio = message.reply_to_message.audio
        title = audio.title or audio.file_name or "Unknown"
        performer = audio.performer or ""

        favorite = FavoriteTrack(
            user_id=user_id,
            platform="yt",  # по умолчанию
            track_id=audio.file_unique_id,
            title=title,
            performer=performer,
            url="",  # Нет URL
            added_at=datetime.now()
        )

    added = await favorites_db.add(favorite)

    if added:
        await message.reply("⭐ Трек добавлен в избранное!")
    else:
        await message.reply("ℹ️ Трек уже в избранном")

    # Удаляем триггер-сообщение
    try:
        await message.delete()
    except TelegramAPIError:
        pass


@router.callback_query(F.data.startswith("fav_add|"))
async def handle_add_favorite_callback(callback: CallbackQuery):
    """Добавить трек в избранное через кнопку."""
    parts = callback.data.split("|")
    if len(parts) != 3:
        await callback.answer("❌ Неверные данные")
        return

    _, platform, track_id = parts
    user_id = callback.from_user.id

    # Получаем метаданные из хранилища
    metadata = music._sent_tracks_metadata.get(callback.message.message_id)

    if not metadata:
        await callback.answer("❌ Метаданные трека не найдены", show_alert=True)
        return

    favorite = FavoriteTrack(
        user_id=user_id,
        platform=metadata['platform'],
        track_id=metadata['track_id'],
        title=metadata['title'],
        performer=metadata['performer'],
        url=metadata['url'],
        added_at=datetime.now()
    )

    added = await favorites_db.add(favorite)

    if added:
        await callback.answer("⭐ Трек добавлен в избранное!", show_alert=True)

        # Обновляем кнопку на "Удалить из избранного"
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🗑 Удалить из избранного",
                callback_data=f"fav_remove|{platform}|{track_id}"
            )]
        ])
        try:
            await callback.message.edit_reply_markup(reply_markup=keyboard)
        except TelegramAPIError:
            pass
    else:
        await callback.answer("ℹ️ Трек уже в избранном", show_alert=True)


@router.callback_query(F.data.startswith("fav_remove|"))
async def handle_remove_favorite_callback(callback: CallbackQuery):
    """Удалить трек из избранного через кнопку."""
    parts = callback.data.split("|")
    if len(parts) != 3:
        await callback.answer("❌ Неверные данные")
        return

    _, platform, track_id = parts
    user_id = callback.from_user.id

    removed = await favorites_db.remove(user_id, platform, track_id)

    if removed:
        await callback.answer("🗑 Трек удалён из избранного", show_alert=True)

        # Обновляем кнопку обратно на "Добавить в избранное"
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⭐ Добавить в избранное",
                callback_data=f"fav_add|{platform}|{track_id}"
            )]
        ])
        try:
            await callback.message.edit_reply_markup(reply_markup=keyboard)
        except TelegramAPIError:
            pass
    else:
        await callback.answer("❌ Трек не найден в избранном")
