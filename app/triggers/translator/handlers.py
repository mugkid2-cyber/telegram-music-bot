"""
Handler для автоматического перевода иностранных сообщений.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

from .language_detector import LanguageDetector
from .translator_service import TranslatorService

logger = logging.getLogger(__name__)

router = Router(name="translator")


@router.message(F.text & ~F.text.startswith("/"))
async def auto_translate_message(message: Message) -> None:
    """
    Автоматически переводит иностранные сообщения на русский язык.

    Реагирует на любой текст, который не является русским, и отправляет
    перевод в ответ на исходное сообщение с флагом страны и форматированием.
    """
    if not message.text:
        return

    text = message.text.strip()

    # Игнорируем слишком короткие сообщения
    if len(text) < 3:
        return

    # Определяем язык
    detected_lang = LanguageDetector.detect(text)

    # Если это русский или не удалось определить - пропускаем
    if detected_lang != 'foreign':
        return

    try:
        # Определяем конкретный язык и получаем флаг
        lang_code, flag = LanguageDetector.detect_specific_language(text)

        # Переводим на русский
        translation = await TranslatorService.translate(text, target_lang="ru")

        if not translation:
            logger.debug(f"Failed to translate message: {text[:50]}...")
            return

        # Если перевод совпадает с оригиналом - не отправляем
        if translation.lower() == text.lower():
            return

        # Форматируем ответ с флагом и разметкой
        response = f"{flag} *Перевод:*\n_{translation}_"

        # Отправляем перевод в ответ на исходное сообщение
        await message.reply(
            text=response,
            parse_mode="Markdown",
            allow_sending_without_reply=True
        )

        logger.info(f"Translated message from {lang_code or 'unknown'} in chat {message.chat.id}")

    except TelegramAPIError as e:
        logger.error(f"Failed to send translation: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error in auto_translate: {e}")
