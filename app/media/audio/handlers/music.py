
import asyncio
import logging
from collections import OrderedDict
from pathlib import Path
from time import time

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.config import get_settings
from app.media.audio.filters.music import MusicCommandFilter, parse_music_command
from app.media.audio.keyboards.music_keyboard import (
    CANCEL_SEARCH_CALLBACK,
    build_search_keyboard,
    parse_callback_data,
)
from app.utils.html_escape import escape_html
from app.utils.security import RateLimiter
from app.media.audio.services.cache_service import CacheService
from app.media.audio.services.download_service import (
    DownloadService,
    TrackTooLongError,
    VideoUnavailableError,
)
from app.media.audio.services.search_service import SearchService
from app.media.audio.services.url_store import pop_url, store_url

# Хранилище метаданных отправленных треков для избранного
# message_id -> {platform, track_id, title, performer, url}
_sent_tracks_metadata = {}

logger = logging.getLogger(__name__)

router = Router(name="music")

search_service = SearchService()
download_service = DownloadService()
cache_service = CacheService()

# Rate limiter: 5 requests per user per minute, 50 global per minute
rate_limiter = RateLimiter(per_user_rate=5, per_user_period=60, global_rate=50, global_period=60)

SEARCH_RESULTS_TEXT = "Результаты поиска:"
SEARCH_EXPIRY_SECONDS = 60
MAX_SEARCH_STATE_SIZE = 1000  # Максимум записей

# Структура: message_id -> (owner_id, created_at, timer_task)
_search_state: OrderedDict[int, tuple[int, float, asyncio.Task | None]] = OrderedDict()


def _add_search_state(message_id: int, owner_id: int, timer_task: asyncio.Task | None = None) -> None:
    """Добавляет запись в состояние поиска с автоочисткой."""
    _search_state[message_id] = (owner_id, time(), timer_task)

    # Если превышен лимит, удаляем самые старые записи
    if len(_search_state) > MAX_SEARCH_STATE_SIZE:
        to_remove = len(_search_state) - MAX_SEARCH_STATE_SIZE
        for _ in range(to_remove):
            old_msg_id, (_, _, old_task) = _search_state.popitem(last=False)
            if old_task and not old_task.done():
                old_task.cancel()


def _get_search_owner(message_id: int) -> int | None:
    """Получает владельца поискового запроса."""
    state = _search_state.get(message_id)
    return state[0] if state else None


def _cleanup_search_state(message_id: int) -> None:
    """Удаляет состояние поиска."""
    state = _search_state.pop(message_id, None)
    if state and state[2] and not state[2].done():
        state[2].cancel()


def _cancel_search_timer(message_id: int) -> None:
    """Отменяет таймер поиска."""
    state = _search_state.get(message_id)
    if state and state[2] and not state[2].done():
        state[2].cancel()


async def _periodic_cleanup_search_state() -> None:
    """Периодическая очистка устаревших записей."""
    while True:
        try:
            await asyncio.sleep(300)  # Каждые 5 минут
            now = time()
            expired = [
                msg_id for msg_id, (_, created_at, _) in _search_state.items()
                if now - created_at > SEARCH_EXPIRY_SECONDS * 2  # Двойной запас
            ]
            for msg_id in expired:
                _cleanup_search_state(msg_id)
            if expired:
                logger.info("Cleaned up %d expired search states", len(expired))
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Search state cleanup failed")


def _schedule_search_expiry(bot: Bot, chat_id: int, message_id: int) -> None:
    _cancel_search_timer(message_id)  # на всякий случай, если уже была задача
    task = asyncio.create_task(_expire_search_message(bot, chat_id, message_id))
    # Обновляем состояние с новым таймером
    state = _search_state.get(message_id)
    if state:
        _search_state[message_id] = (state[0], state[1], task)


async def _expire_search_message(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await asyncio.sleep(SEARCH_EXPIRY_SECONDS)
    except asyncio.CancelledError:
        return

    _search_state.pop(message_id, None)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramAPIError:
        # сообщение уже могли удалить руками или его нет — не страшно
        pass


def _max_duration_minutes() -> int:
    return get_settings().MAX_DURATION_SECONDS // 60


async def _delete_message_safe(message: Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except Exception:
        pass


async def _send_error(
    bot: Bot,
    chat_id: int,
    reply_to_message_id: int | None,
    status_message: Message | None,
    text: str,
) -> None:
    await _delete_message_safe(status_message)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
        )
    except TelegramAPIError:
        logger.exception("Failed to send error message to chat %s", chat_id)


@router.message(F.text, MusicCommandFilter())
async def handle_music_search(message: Message) -> None:
    query = parse_music_command(message.text or "")
    if query is None:
        return

    if not query:
        try:
            await message.reply("❌ Укажите название трека.")
        except TelegramAPIError:
            logger.warning("Failed to reply - message may be deleted")
        return

    # Check rate limit
    user_id = message.from_user.id if message.from_user else 0
    allowed, retry_after = rate_limiter.check_rate_limit(user_id)
    if not allowed:
        try:
            await message.reply(
                f"⏳ Слишком много запросов. Попробуйте через {retry_after} секунд."
            )
        except TelegramAPIError:
            logger.warning("Failed to send rate limit message")
        return

    try:
        status = await message.reply("🔍 Поиск...")
    except TelegramAPIError:
        logger.warning("Failed to reply - message may be deleted")
        return

    try:
        tracks = await search_service.search(query)
    except Exception:
        logger.exception("Search error for query: %s", query)
        await status.edit_text("❌ Ошибка поиска. Попробуйте позже.")
        return

    if not tracks:
        await status.edit_text(f"😔 По запросу <b>{escape_html(query)}</b> ничего не найдено.")
        return

    for track in tracks:
        store_url(track.platform, track.track_id, track.url)

    keyboard = build_search_keyboard(tracks)
    await status.edit_text(SEARCH_RESULTS_TEXT, reply_markup=keyboard)
    _add_search_state(status.message_id, message.from_user.id)
    _schedule_search_expiry(message.bot, status.chat.id, status.message_id)


@router.callback_query(F.data == CANCEL_SEARCH_CALLBACK)
async def handle_search_cancel(callback: CallbackQuery) -> None:
    if not callback.message:
        await callback.answer()
        return

    owner_id = _get_search_owner(callback.message.message_id)
    if owner_id is not None and callback.from_user.id != owner_id:
        await callback.answer("❌ Это не ваш запрос", show_alert=True)
        return

    await callback.answer()
    _cleanup_search_state(callback.message.message_id)
    await _delete_message_safe(callback.message)


@router.callback_query(F.data.startswith("dl|"))
async def handle_track_download(callback: CallbackQuery, bot: Bot) -> None:
    parsed = parse_callback_data(callback.data or "")
    if not parsed:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    platform, track_id = parsed

    owner_id = _get_search_owner(callback.message.message_id) if callback.message else None
    if owner_id is not None and callback.from_user.id != owner_id:
        await callback.answer("Это не ваш запрос", show_alert=True)
        return

    await callback.answer()

    chat_id = callback.message.chat.id
    reply_target = callback.message.reply_to_message
    reply_to_id = reply_target.message_id if reply_target else None

    _cleanup_search_state(callback.message.message_id)
    await _delete_message_safe(callback.message)

    try:
        status_message = await bot.send_message(
            chat_id=chat_id,
            text="⏳ Подготовка...",
            reply_to_message_id=reply_to_id,
        )
    except TelegramAPIError:
        logger.exception("Failed to send status message to chat %s", chat_id)
        return

    cached = await cache_service.get(platform, track_id)
    if cached and Path(cached.file_path).exists():
        try:
            # Обновляем статус для кеша
            try:
                await status_message.edit_text("📤 Отправка из кеша...")
            except Exception:
                pass

            cached_thumb = Path(cached.file_path).with_suffix(".jpg")
            await _delete_message_safe(status_message)
            await _send_audio(
                bot=bot,
                chat_id=chat_id,
                file_path=cached.file_path,
                title=cached.title,
                performer=getattr(cached, "performer", "") or "",
                duration=getattr(cached, "duration", None),
                thumbnail_path=str(cached_thumb) if cached_thumb.exists() else None,
                reply_to_message_id=reply_to_id,
            )
            return
        except Exception:
            logger.exception("Failed to send cached track, invalidating cache entry")
            await cache_service.delete(platform, track_id)
            # не выходим с ошибкой — падаем ниже на обычное скачивание,
            # чтобы пользователь всё равно получил трек
    elif cached:
        # запись в кэше есть, а файла на диске уже нет — инвалидируем
        logger.warning("Cached file missing on disk, invalidating: %s:%s", platform, track_id)
        await cache_service.delete(platform, track_id)

    track_url = pop_url(platform, track_id)

    # Обновляем статус на скачивание
    try:
        await status_message.edit_text("⬇️ Скачивание...")
    except Exception:
        pass

    try:
        track = await download_service.download(platform, track_id, url=track_url)
    except ValueError as exc:
        logger.warning("URL resolution failed: %s:%s — %s", platform, track_id, exc)
        await _send_error(
            bot, chat_id, reply_to_id, status_message, "❌ Трек не найден. Повторите поиск."
        )
        return
    except TrackTooLongError:
        await _send_error(
            bot,
            chat_id,
            reply_to_id,
            status_message,
            f"❌ Трек превышает лимит загрузки ({_max_duration_minutes()} минут).",
        )
        return
    except VideoUnavailableError:
        logger.warning("Video unavailable: %s:%s", platform, track_id)
        await _send_error(
            bot,
            chat_id,
            reply_to_id,
            status_message,
            "❌ Видео недоступно или удалено.",
        )
        return
    except RuntimeError as exc:
        logger.exception("Download/runtime error: %s:%s", platform, track_id)
        if "ffmpeg" in str(exc).lower():
            error_text = "❌ Ошибка конвертации аудио на стороне сервера."
        else:
            error_text = f"❌ {escape_html(str(exc))}"
        await _send_error(bot, chat_id, reply_to_id, status_message, error_text)
        return
    except Exception:
        logger.exception("Download error: %s:%s", platform, track_id)
        await _send_error(
            bot,
            chat_id,
            reply_to_id,
            status_message,
            "❌ Ошибка скачивания. Проверьте соединение и попробуйте снова.",
        )
        return

    try:
        await cache_service.save(
            source=platform,
            track_id=track_id,
            title=track.title,
            file_path=str(track.file_path),
        )

        # Обновляем статус на отправку
        try:
            await status_message.edit_text("📤 Отправка...")
        except Exception:
            pass

        await _delete_message_safe(status_message)
        sent_message = await _send_audio(
            bot=bot,
            chat_id=chat_id,
            file_path=str(track.file_path),
            title=track.title,
            performer=track.performer,
            duration=track.duration,
            thumbnail_path=str(track.thumbnail_path) if track.thumbnail_path else None,
            reply_to_message_id=reply_to_id,
            platform=platform,
            track_id=track_id,
            url=track_url or resolved_url,
        )
    except TelegramAPIError:
        logger.exception("Telegram API error while sending audio")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Ошибка отправки файла в Telegram.",
            reply_to_message_id=reply_to_id,
        )
    except Exception:
        logger.exception("Unexpected error while sending audio")
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Произошла непредвиденная ошибка.",
            reply_to_message_id=reply_to_id,
        )


async def _send_audio(
    bot: Bot,
    chat_id: int,
    file_path: str,
    title: str,
    performer: str,
    duration: int | None,
    thumbnail_path: str | None,
    reply_to_message_id: int | None,
    platform: str = None,
    track_id: str = None,
    url: str = None,
) -> Message:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    # Подготовка thumbnail заранее для ускорения
    thumb = None
    if thumbnail_path:
        thumb_path = Path(thumbnail_path)
        if thumb_path.exists():
            thumb = FSInputFile(thumb_path)

    # Оптимизированная отправка с использованием BufferedInputFile для больших файлов
    audio_file = FSInputFile(file_path)

    kwargs: dict = {
        "chat_id": chat_id,
        "audio": audio_file,
        "title": title[:64] if title else "Track",
    }

    if reply_to_message_id is not None:
        kwargs["reply_to_message_id"] = reply_to_message_id
    if performer:
        kwargs["performer"] = performer[:64]
    if duration:
        kwargs["duration"] = int(duration)
    if thumb:
        kwargs["thumbnail"] = thumb

    # Добавляем кнопку "Добавить в избранное"
    if platform and track_id and url:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⭐ Добавить в избранное",
                callback_data=f"fav_add|{platform}|{track_id}"
            )]
        ])
        kwargs["reply_markup"] = keyboard

    # Отправка с таймаутом
    sent_message = await bot.send_audio(**kwargs)

    # Сохраняем метаданные для возможности добавления в избранное
    if platform and track_id and url:
        _sent_tracks_metadata[sent_message.message_id] = {
            'platform': platform,
            'track_id': track_id,
            'title': title,
            'performer': performer,
            'url': url,
        }

    return sent_message