"""Handler для распознавания музыки через Shazam.

Распознаёт музыку из:
- Голосовых сообщений
- Аудио файлов
- Видео
- Видео-кружков

Использование: ответь словом "шазам" (регистронезависимо) на сообщение с музыкой.
"""
import logging
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile
from aiogram.exceptions import TelegramAPIError

from app.triggers.shazam.service_audd import AudDService as ShazamService, TrackInfo
from app.media.audio.services.search_service import SearchService
from app.media.audio.keyboards.music_keyboard import build_search_keyboard
from app.media.audio.services.url_store import store_url
from app.utils.html_escape import escape_html

logger = logging.getLogger(__name__)

router = Router(name="shazam")

shazam_service = ShazamService()
search_service = SearchService()


def _format_track_info(track: TrackInfo) -> str:
    """Форматирует информацию о треке."""
    lines = [
        "🎵 <b>Найдено!</b>\n",
        f"🎤 <b>{escape_html(track.artist)}</b>",
        f"🎶 <b>{escape_html(track.title)}</b>",
    ]

    if track.album:
        lines.append(f"💿 Альбом: {escape_html(track.album)}")

    if track.genre:
        lines.append(f"🎭 Жанр: {escape_html(track.genre)}")

    if track.release_year:
        lines.append(f"📅 Год: {escape_html(track.release_year)}")

    if track.duration:
        minutes = track.duration // 60
        seconds = track.duration % 60
        lines.append(f"⏱️ Длительность: {minutes}:{seconds:02d}")

    # Ссылки
    links = []
    if track.shazam_url:
        links.append(f'<a href="{track.shazam_url}">Shazam</a>')
    if track.apple_music_url:
        links.append(f'<a href="{track.apple_music_url}">Apple Music</a>')
    if track.spotify_url:
        links.append(f'<a href="{track.spotify_url}">Spotify</a>')

    if links:
        lines.append("\n🔗 " + " • ".join(links))

    return "\n".join(lines)


@router.message(
    F.reply_to_message,
    F.text,
)
async def handle_shazam_trigger(message: Message, bot: Bot):
    """
    Обрабатывает команду 'шазам' ответом на сообщение.

    Срабатывает на:
    - шазам
    - Шазам
    - ШАЗАМ
    - шАзАм
    """
    # Проверяем текст (регистронезависимо)
    if not message.text or message.text.strip().lower() != "шазам":
        return

    replied_msg = message.reply_to_message

    # Проверяем тип контента
    has_media = (
        replied_msg.audio or
        replied_msg.voice or
        replied_msg.video or
        replied_msg.video_note or
        replied_msg.document  # На случай если отправили аудио как документ
    )

    if not has_media:
        await message.reply(
            "❌ Ответь словом <b>шазам</b> на:\n"
            "• 🎤 Голосовое сообщение\n"
            "• 🎵 Аудио файл\n"
            "• 🎬 Видео\n"
            "• ⭕ Видео-кружок",
            parse_mode="HTML"
        )
        return

    # Отправляем статус
    status_msg = await message.reply("🔍 Распознаю музыку...")

    temp_file = None
    try:
        # Определяем файл для скачивания
        file_to_download = None
        extension = "mp3"

        if replied_msg.audio:
            file_to_download = replied_msg.audio
            extension = "mp3"
            logger.info("Processing audio file", extra={"extra_data": {
                "file_size": file_to_download.file_size,
                "duration": file_to_download.duration
            }})
        elif replied_msg.voice:
            file_to_download = replied_msg.voice
            extension = "ogg"
            logger.info("Processing voice message", extra={"extra_data": {
                "file_size": file_to_download.file_size,
                "duration": file_to_download.duration
            }})
        elif replied_msg.video:
            file_to_download = replied_msg.video
            extension = "mp4"
            logger.info("Processing video", extra={"extra_data": {
                "file_size": file_to_download.file_size,
                "duration": file_to_download.duration
            }})
        elif replied_msg.video_note:
            file_to_download = replied_msg.video_note
            extension = "mp4"
            logger.info("Processing video note", extra={"extra_data": {
                "file_size": file_to_download.file_size,
                "duration": file_to_download.duration
            }})
        elif replied_msg.document:
            file_to_download = replied_msg.document
            # Проверяем MIME type
            if file_to_download.mime_type and "audio" in file_to_download.mime_type:
                extension = "mp3"
                logger.info("Processing audio document", extra={"extra_data": {
                    "file_size": file_to_download.file_size,
                    "mime": file_to_download.mime_type
                }})
            else:
                await status_msg.edit_text("❌ Документ не является аудио файлом")
                return

        if not file_to_download:
            await status_msg.edit_text("❌ Не удалось получить файл")
            return

        # Проверяем размер (лимит 500MB для больших файлов)
        max_size = 500 * 1024 * 1024  # 500 MB
        if file_to_download.file_size and file_to_download.file_size > max_size:
            await status_msg.edit_text(
                "❌ Файл слишком большой (макс. 500 МБ)\n"
                f"Размер вашего файла: {file_to_download.file_size / (1024 * 1024):.1f} МБ"
            )
            return

        # Скачиваем файл
        logger.info("Downloading file from Telegram...")
        file = await bot.get_file(file_to_download.file_id)
        file_bytes = await bot.download_file(file.file_path)

        # Сохраняем во временный файл
        temp_file = await shazam_service.download_temp_file(
            file_bytes.read(),
            extension=extension
        )

        logger.info(
            "File downloaded successfully",
            extra={"extra_data": {"temp_file": temp_file.name, "size": temp_file.stat().st_size}}
        )

        # Распознаём
        await status_msg.edit_text("🎵 Анализирую трек...")
        track_info = await shazam_service.recognize_from_file(temp_file)

        if not track_info:
            await status_msg.edit_text(
                "😔 Не удалось распознать трек.\n\n"
                "💡 <b>Попробуйте:</b>\n"
                "• Более чёткую запись\n"
                "• Без фонового шума\n"
                "• Другой фрагмент песни (припев обычно лучше)\n"
                "• Увеличить громкость",
                parse_mode="HTML"
            )
            return

        logger.info(
            "Track recognized successfully",
            extra={"extra_data": {
                "artist": track_info.artist,
                "title": track_info.title
            }}
        )

        # Формируем ответ
        response_text = _format_track_info(track_info)

        # Отправляем информацию с обложкой если есть
        if track_info.cover_url:
            try:
                await status_msg.delete()
                await message.reply_photo(
                    photo=track_info.cover_url,
                    caption=response_text,
                    parse_mode="HTML"
                )
            except TelegramAPIError as e:
                logger.warning(f"Failed to send cover image: {e}")
                # Если не удалось отправить фото, отправляем просто текст
                await status_msg.edit_text(response_text, parse_mode="HTML")
        else:
            await status_msg.edit_text(response_text, parse_mode="HTML")

        # Ищем и отправляем полную версию для скачивания
        await _search_and_send_download_button(message, track_info)

    except Exception as e:
        logger.exception("Shazam recognition failed")
        try:
            await status_msg.edit_text(
                "❌ Произошла ошибка при распознавании.\n"
                "Попробуйте ещё раз или отправьте другой фрагмент."
            )
        except Exception:
            pass

    finally:
        # Очищаем временный файл
        if temp_file:
            await shazam_service.cleanup_temp_file(temp_file)
            logger.debug(f"Cleaned up temp file: {temp_file.name if temp_file else 'None'}")


async def _search_and_send_download_button(message: Message, track: TrackInfo):
    """Ищет полную версию трека и даёт кнопку для скачивания."""
    try:
        # Формируем поисковый запрос
        search_query = f"{track.artist} {track.title}"

        logger.info(f"Searching for full track: {search_query}")

        # Ищем трек
        search_results = await search_service.search(search_query)

        if not search_results:
            await message.reply(
                "ℹ️ Не нашёл полную версию для скачивания.\n"
                f"Попробуйте сами: <code>мп3 {escape_html(search_query)}</code>",
                parse_mode="HTML"
            )
            return

        # Берём топ-3 результата
        top_results = search_results[:3]

        # Сохраняем URL для кнопок
        for result in top_results:
            store_url(result.platform, result.track_id, result.url)

        # Создаём клавиатуру с результатами
        keyboard = build_search_keyboard(top_results)

        await message.reply(
            f"✅ <b>Нашёл полную версию для скачивания!</b>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        logger.info(f"Found {len(top_results)} download options")

    except Exception as e:
        logger.exception("Failed to search full track")
        # Не критично, просто не отправляем кнопку
        await message.reply(
            f"ℹ️ Попробуй скачать самостоятельно:\n"
            f"<code>мп3 {escape_html(track.artist)} {escape_html(track.title)}</code>",
            parse_mode="HTML"
        )
