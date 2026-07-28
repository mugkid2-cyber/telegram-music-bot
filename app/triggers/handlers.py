"""
Handler для фан-команд с триггерами на имена и музыкальными триггерами.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.exceptions import TelegramAPIError

from .triggers import check_trigger
from .nervy import get_nervy_trigger
from .calculator.calculator_service import CalculatorService
from .translator.language_detector import LanguageDetector
from .translator.translator_service import TranslatorService

logger = logging.getLogger(__name__)

router = Router(name="fun_commands")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_message_triggers(message: Message) -> None:
    """Проверяет сообщение на различные триггеры и отвечает соответствующим образом"""
    if not message.text:
        return

    text = message.text.strip()

    # 1. Проверяем триггер группы Нервы
    nervy = get_nervy_trigger()
    if nervy.check_trigger(text):
        try:
            result = await nervy.get_random_track()
            if result:
                audio_file, title, performer, thumbnail_path = result

                # Подготавливаем kwargs для отправки
                kwargs = {
                    "audio": audio_file,
                    "title": title,
                    "performer": performer,
                }

                # Добавляем thumbnail если есть
                if thumbnail_path:
                    kwargs["thumbnail"] = FSInputFile(thumbnail_path)

                await message.reply_audio(**kwargs)
                logger.info("Triggered: Nervy - %s", title)
                return
            else:
                logger.warning("Nervy trigger activated but no tracks available")
        except Exception:
            logger.exception("Error handling Nervy trigger")
        return

    # 2. Проверяем стандартные триггеры (медиа)
    trigger = check_trigger(text)
    if trigger:
        try:
            if trigger["type"] == "video":
                await message.reply_video(
                    video=FSInputFile(trigger["file"]),
                    caption=None,
                )
            elif trigger["type"] == "photo":
                await message.reply_photo(
                    photo=FSInputFile(trigger["file"]),
                    caption=None,
                )
            elif trigger["type"] == "audio":
                await message.reply_audio(
                    audio=FSInputFile(trigger["file"]),
                )
            logger.info("Triggered: %s", trigger["name"])
            return
        except TelegramAPIError as e:
            logger.error("Failed to send media for trigger %s: %s", trigger["name"], e)
        except FileNotFoundError:
            logger.error("Media file not found: %s", trigger["file"])
        except Exception:
            logger.exception("Unexpected error in fun_commands")
        return

    # 3. Проверяем математическое выражение
    if len(text) >= 3 and CalculatorService.is_math_expression(text):
        try:
            result, error = CalculatorService.calculate(text)

            if result is not None and not error:
                formatted_result = CalculatorService.format_result(result)
                response = f"🔢 *Результат:*\n`{formatted_result}`"

                await message.reply(
                    text=response,
                    parse_mode="Markdown",
                    allow_sending_without_reply=True
                )
                logger.info(f"Calculated: {text} = {formatted_result} in chat {message.chat.id}")
                return
        except Exception as e:
            logger.exception(f"Unexpected error in calculator: {e}")

    # 4. Проверяем иностранный текст для перевода
    if len(text) >= 3:
        detected_lang = LanguageDetector.detect(text)

        if detected_lang == 'foreign':
            try:
                # Переводим текст и получаем определённый язык от Google Translate
                translation, detected_lang_code = await TranslatorService.translate(text, target_lang="ru")

                if translation and translation.lower() != text.lower():
                    # Получаем флаг из Google Translate API или используем наш детектор как запасной вариант
                    flag = TranslatorService.get_flag_emoji(detected_lang_code)

                    # Если Google не определил язык, используем наш детектор
                    if flag == '🌐':
                        lang_code, flag = LanguageDetector.detect_specific_language(text)

                    response = f"{flag} *Перевод:*\n_{translation}_"

                    await message.reply(
                        text=response,
                        parse_mode="Markdown",
                        allow_sending_without_reply=True
                    )
                    logger.info(f"Translated message from {detected_lang_code or 'unknown'} in chat {message.chat.id}")
                    return
            except Exception as e:
                logger.exception(f"Unexpected error in translator: {e}")
