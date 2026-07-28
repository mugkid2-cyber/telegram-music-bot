"""
Handler для автоматического калькулятора.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

from .calculator_service import CalculatorService

logger = logging.getLogger(__name__)

router = Router(name="calculator")


@router.message(F.text & ~F.text.startswith("/"))
async def auto_calculate(message: Message) -> None:
    """
    Автоматически вычисляет математические выражения.

    Если сообщение содержит математическое выражение, бот автоматически
    вычисляет его и отправляет результат в ответ.
    """
    if not message.text:
        return

    text = message.text.strip()

    # Проверяем, является ли это математическим выражением
    if not CalculatorService.is_math_expression(text):
        return

    try:
        # Вычисляем выражение
        result, error = CalculatorService.calculate(text)

        if error:
            # Не отправляем ошибки, просто логируем
            logger.debug(f"Calculation error for '{text}': {error}")
            return

        if result is None:
            return

        # Форматируем результат
        formatted_result = CalculatorService.format_result(result)

        # Формируем ответ с эмодзи калькулятора
        response = f"🔢 *Результат:*\n`{formatted_result}`"

        # Отправляем результат в ответ на исходное сообщение
        await message.reply(
            text=response,
            parse_mode="Markdown",
            allow_sending_without_reply=True
        )

        logger.info(f"Calculated: {text} = {formatted_result} in chat {message.chat.id}")

    except TelegramAPIError as e:
        logger.error(f"Failed to send calculation result: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error in auto_calculate: {e}")
