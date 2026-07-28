"""
Роутер aiogram 3.x для скачивания видео с разных платформ.

Поддерживаемые платформы:
- TikTok (с сохранением в БД и командой /tt)
- YouTube (обычные видео и Shorts)
- Instagram (посты, Reels, IGTV)

Функции:
- Автоматическое определение платформы
- Выбор формата (видео/аудио)
- /tt - отправка рандомного TikTok из базы за последние 3 дня
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import shutil
import tempfile
import time
from pathlib import Path

from aiogram import F, Router
from aiogram.exceptions import TelegramEntityTooLarge, TelegramNetworkError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.media.video import config
from app.media.video.callbacks import CancelCallback, DownloadTypeCallback
from app.media.video.compressor import get_compressor
from app.media.video.errors import DownloaderError, FileTooLargeError
from app.media.video.keyboards import choose_type_kb
from app.media.video.platforms import Platform, detect_platform, extract_url
from app.media.video.platforms.tiktok import TikTokDB, TikTokDownloader
from app.media.video.platforms.youtube import YouTubeDownloader
from app.media.video.platforms.instagram import InstagramDownloader
from app.media.video.request_cache import DownloadRequest, request_cache

logger = logging.getLogger(__name__)
router = Router(name="video_downloader")

# База данных для TikTok
tiktok_db: TikTokDB | None = None

# Папка для постоянного хранения TikTok видео
TIKTOK_STORAGE = Path("app/downloads/tiktok_storage")
TIKTOK_STORAGE.mkdir(parents=True, exist_ok=True)

# Анти-спам: время последнего запроса на пользователя
_last_request_at: dict[int, float] = {}

# Загрузчики для каждой платформы
_downloaders = {
    Platform.TIKTOK: TikTokDownloader(),
    Platform.YOUTUBE: YouTubeDownloader(),
    Platform.INSTAGRAM: InstagramDownloader(),
}


def _workdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="vd_", dir=config.TMP_DIR))


def _cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _cooldown_ok(user_id: int) -> bool:
    """
    Проверяет, прошёл ли кулдаун для пользователя.

    Args:
        user_id: ID пользователя

    Returns:
        True если кулдаун прошёл, False если нужно подождать
    """
    now = time.monotonic()
    last = _last_request_at.get(user_id, 0.0)
    if now - last < config.USER_DOWNLOAD_COOLDOWN_SECONDS:
        return False
    _last_request_at[user_id] = now

    # Очистка старых записей (старше 1 часа)
    if len(_last_request_at) > 1000:
        cutoff = now - 3600
        expired = [uid for uid, timestamp in _last_request_at.items() if timestamp < cutoff]
        for uid in expired[:500]:
            _last_request_at.pop(uid, None)

    return True


def _get_platform_emoji(platform: Platform) -> str:
    """Возвращает emoji для платформы."""
    emoji_map = {
        Platform.TIKTOK: "🎵",
        Platform.YOUTUBE: "▶️",
        Platform.INSTAGRAM: "📷",
    }
    return emoji_map.get(platform, "🎬")


@router.message(F.text.regexp(r"https?://"))
async def handle_link(message: Message) -> None:
    """Обработчик ссылок на видео."""
    url = extract_url(message.text or "")
    if not url:
        return

    platform = detect_platform(url)

    # Поддерживаемые платформы
    if platform not in (Platform.TIKTOK, Platform.YOUTUBE, Platform.INSTAGRAM):
        return  # не наша ссылка

    if not _cooldown_ok(message.from_user.id):
        await message.reply("⏳ Подождите пару секунд перед следующим запросом.")
        return

    emoji = _get_platform_emoji(platform)
    platform_name = platform.name.title()

    req = DownloadRequest(
        url=url,
        platform=platform,
        chat_id=message.chat.id,
        message_id=message.message_id,
        user_id=message.from_user.id,
    )

    req_id = await request_cache.put(req)
    await message.reply(
        f"{emoji} Обнаружена ссылка на {platform_name}\nВыберите что хотите скачать:",
        reply_markup=choose_type_kb(req_id),
    )


@router.message(Command("tt"))
async def handle_random_tiktok(message: Message) -> None:
    """Отправляет случайный TikTok из базы за последние 3 дня."""
    if tiktok_db is None:
        await message.reply("❌ База данных TikTok не инициализирована")
        return

    total = await tiktok_db.get_total_count()
    if total == 0:
        await message.reply(
            "😔 В базе пока нет сохранённых TikTok-ов.\n"
            "Отправьте ссылку на TikTok, чтобы добавить!"
        )
        return

    video = await tiktok_db.get_random_video()
    if video is None:
        await message.reply("😔 Не удалось найти видео. Попробуйте ещё раз.")
        return

    file_path, url = video

    # Проверяем, существует ли файл
    if not Path(file_path).exists():
        await message.reply("😔 Видео было удалено. Попробуйте другое.")
        return

    try:
        await message.answer_video(
            video=FSInputFile(file_path),
            caption=f"🎲 Случайный TikTok\n\n{url}\n\nВсего в базе: {total} видео",
            supports_streaming=True,
        )
    except Exception as e:
        logger.error("Failed to send random TikTok: %s", e)
        await message.reply("❌ Ошибка при отправке видео")


@router.callback_query(CancelCallback.filter())
async def handle_cancel(call: CallbackQuery, callback_data: CancelCallback) -> None:
    """Обработка отмены скачивания."""
    await request_cache.pop(callback_data.req_id)
    await call.message.edit_text("✖️ Отменено.")
    await call.answer()


@router.callback_query(DownloadTypeCallback.filter())
async def handle_type_choice(call: CallbackQuery, callback_data: DownloadTypeCallback) -> None:
    """Обработка выбора типа скачивания (видео/аудио)."""
    req = await request_cache.get(callback_data.req_id)
    if req is None:
        await call.answer("Запрос устарел, отправьте ссылку заново.", show_alert=True)
        return

    await request_cache.pop(callback_data.req_id)
    await call.answer()

    emoji = _get_platform_emoji(req.platform)

    if callback_data.kind == "audio":
        await call.message.edit_text(f"{emoji} ⏳ Скачиваю аудио...")
        await _finish_download(call, req, mode="audio")
    else:
        await call.message.edit_text(f"{emoji} ⏳ Скачиваю видео...")
        await _finish_download(call, req, mode="video")


async def _finish_download(call: CallbackQuery, req: DownloadRequest, mode: str) -> None:
    """Завершение скачивания и отправка файла."""
    workdir = _workdir()
    downloader = _downloaders.get(req.platform)

    if downloader is None:
        await call.message.edit_text("❌ Платформа не поддерживается")
        return

    try:
        # Скачивание
        if mode == "audio":
            path = await downloader.download(
                req.url,
                workdir,
                extract_audio=True,
            )
            await call.bot.send_audio(
                chat_id=req.chat_id,
                audio=FSInputFile(path),
                caption=config.CAPTION,
                reply_to_message_id=req.message_id,
            )
        else:
            path = await downloader.download(
                req.url,
                workdir,
                format_id=None,
                extract_audio=False,
            )

            # Проверяем размер и сжимаем если нужно
            original_size = path.stat().st_size
            if original_size > config.MAX_FILE_SIZE_BYTES:
                logger.info(
                    "Video exceeds limit (%.2f MB), attempting compression",
                    original_size / (1024 * 1024)
                )
                await call.message.edit_text(
                    f"{_get_platform_emoji(req.platform)} 🔄 Видео слишком большое, сжимаю..."
                )

                compressor = get_compressor(config.MAX_FILE_SIZE_MB)
                path = await compressor.compress_if_needed(path)

                # Проверяем результат
                compressed_size = path.stat().st_size
                if compressed_size > config.MAX_FILE_SIZE_BYTES:
                    raise FileTooLargeError(compressed_size, config.MAX_FILE_SIZE_BYTES)

            # Сохраняем TikTok в постоянное хранилище для /tt
            if req.platform == Platform.TIKTOK and tiktok_db is not None:
                url_hash = hashlib.md5(req.url.encode()).hexdigest()[:12]
                permanent_path = TIKTOK_STORAGE / f"{url_hash}.mp4"

                shutil.copy2(path, permanent_path)
                await tiktok_db.save_video(
                    url=req.url,
                    file_path=str(permanent_path),
                    user_id=req.user_id,
                    chat_id=req.chat_id,
                )
                logger.info("Saved TikTok to permanent storage: %s", permanent_path)

            await call.bot.send_video(
                chat_id=req.chat_id,
                video=FSInputFile(path),
                caption=config.CAPTION,
                reply_to_message_id=req.message_id,
                supports_streaming=True,
            )

        await call.message.delete()

    except FileTooLargeError as exc:
        await call.message.edit_text(
            f"⚠️ Файл слишком большой даже после сжатия "
            f"({exc.size_bytes // (1024 * 1024)} МБ, лимит {config.MAX_FILE_SIZE_MB} МБ).\n\n"
            f"💡 Решения:\n"
            f"1. Используйте локальный Bot API с лимитом до 2000 МБ\n"
            f"2. Попробуйте более короткий фрагмент видео"
        )
    except DownloaderError as exc:
        await call.message.edit_text(f"❌ {exc}")
    except TelegramEntityTooLarge:
        await call.message.edit_text(
            "⚠️ Telegram отклонил файл — он больше допустимого размера."
        )
    except TelegramNetworkError:
        await call.message.edit_text(
            "⚠️ Сеть Telegram сейчас недоступна, попробуйте ещё раз чуть позже."
        )
    except Exception:
        logger.exception("Unexpected error while finishing download for %s", req.url)
        await call.message.edit_text(
            "❌ Непредвиденная ошибка при скачивании. Попробуйте позже."
        )
    finally:
        _cleanup(workdir)


async def cleanup_old_tiktoks_loop():
    """Фоновая задача: очистка старых TikTok каждые 24 часа."""
    while True:
        try:
            await asyncio.sleep(86400)  # 24 часа
            if tiktok_db is not None:
                deleted = await tiktok_db.cleanup_old_videos()
                logger.info("Auto-cleanup: removed %d old TikTok videos", deleted)
        except Exception as e:
            logger.error("Error in cleanup loop: %s", e)


async def start_background_tasks() -> None:
    """Запуск фоновых задач (вызывается при старте бота)."""
    global tiktok_db

    try:
        # Инициализируем базу данных TikTok
        db_path = Path("app/data/tiktok.db")
        tiktok_db = TikTokDB(db_path)
        await tiktok_db.init_db()
        logger.info("TikTok database initialized")

        # Запускаем фоновые задачи
        asyncio.create_task(request_cache.cleanup_loop(), name="request_cache_cleanup")
        asyncio.create_task(cleanup_old_tiktoks_loop(), name="tiktok_cleanup")

        logger.info("Video downloader готов (TikTok, YouTube, Instagram)")

    except Exception as e:
        logger.error("Failed to start background tasks: %s", e)
