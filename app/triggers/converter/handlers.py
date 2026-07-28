"""
Handler для конвертации различных единиц измерения.
"""
import re
import logging
from typing import Optional, Tuple
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

router = Router(name="converter")


class UnitConverter:
    """Конвертер единиц измерения."""

    # Температура
    @staticmethod
    def celsius_to_fahrenheit(celsius: float) -> float:
        return (celsius * 9/5) + 32

    @staticmethod
    def fahrenheit_to_celsius(fahrenheit: float) -> float:
        return (fahrenheit - 32) * 5/9

    @staticmethod
    def celsius_to_kelvin(celsius: float) -> float:
        return celsius + 273.15

    # Расстояние
    DISTANCE_TO_METERS = {
        'м': 1,
        'км': 1000,
        'см': 0.01,
        'мм': 0.001,
        'миля': 1609.34,
        'ярд': 0.9144,
        'фут': 0.3048,
        'дюйм': 0.0254,
    }

    # Вес
    WEIGHT_TO_GRAMS = {
        'г': 1,
        'кг': 1000,
        'мг': 0.001,
        'т': 1000000,
        'фунт': 453.592,
        'унция': 28.3495,
    }

    # Объем
    VOLUME_TO_LITERS = {
        'л': 1,
        'мл': 0.001,
        'галлон': 3.78541,
        'пинта': 0.473176,
        'чашка': 0.236588,
    }

    # Скорость
    SPEED_TO_MPS = {
        'м/с': 1,
        'км/ч': 0.277778,
        'миля/ч': 0.44704,
        'узел': 0.514444,
    }

    @classmethod
    def convert_distance(cls, value: float, from_unit: str, to_unit: str) -> Optional[float]:
        """Конвертирует расстояние."""
        from_unit = from_unit.lower()
        to_unit = to_unit.lower()

        if from_unit not in cls.DISTANCE_TO_METERS or to_unit not in cls.DISTANCE_TO_METERS:
            return None

        meters = value * cls.DISTANCE_TO_METERS[from_unit]
        result = meters / cls.DISTANCE_TO_METERS[to_unit]
        return result

    @classmethod
    def convert_weight(cls, value: float, from_unit: str, to_unit: str) -> Optional[float]:
        """Конвертирует вес."""
        from_unit = from_unit.lower()
        to_unit = to_unit.lower()

        if from_unit not in cls.WEIGHT_TO_GRAMS or to_unit not in cls.WEIGHT_TO_GRAMS:
            return None

        grams = value * cls.WEIGHT_TO_GRAMS[from_unit]
        result = grams / cls.WEIGHT_TO_GRAMS[to_unit]
        return result

    @classmethod
    def convert_volume(cls, value: float, from_unit: str, to_unit: str) -> Optional[float]:
        """Конвертирует объем."""
        from_unit = from_unit.lower()
        to_unit = to_unit.lower()

        if from_unit not in cls.VOLUME_TO_LITERS or to_unit not in cls.VOLUME_TO_LITERS:
            return None

        liters = value * cls.VOLUME_TO_LITERS[from_unit]
        result = liters / cls.VOLUME_TO_LITERS[to_unit]
        return result

    @classmethod
    def convert_speed(cls, value: float, from_unit: str, to_unit: str) -> Optional[float]:
        """Конвертирует скорость."""
        from_unit = from_unit.lower()
        to_unit = to_unit.lower()

        if from_unit not in cls.SPEED_TO_MPS or to_unit not in cls.SPEED_TO_MPS:
            return None

        mps = value * cls.SPEED_TO_MPS[from_unit]
        result = mps / cls.SPEED_TO_MPS[to_unit]
        return result


@router.message(Command("convert"))
async def convert_command(message: Message) -> None:
    """
    Команда для конвертации единиц.

    Использование:
    /convert 100 км в мили
    /convert 32 F в C
    /convert 5 кг в фунты
    """
    command_parts = message.text.split()

    if len(command_parts) < 5:
        await message.reply(
            "🔄 *Конвертер единиц*\n\n"
            "Использование:\n"
            "`/convert [число] [единица] в [единица]`\n\n"
            "Примеры:\n"
            "`/convert 100 км в мили`\n"
            "`/convert 32 F в C`\n"
            "`/convert 5 кг в фунты`\n"
            "`/convert 10 л в галлоны`\n\n"
            "Поддерживаемые типы:\n"
            "• Температура: C, F, K\n"
            "• Расстояние: м, км, миля, фут, дюйм\n"
            "• Вес: г, кг, фунт, унция\n"
            "• Объем: л, мл, галлон, пинта\n"
            "• Скорость: м/с, км/ч, миля/ч",
            parse_mode="Markdown"
        )
        return

    try:
        value = float(command_parts[1])
        from_unit = command_parts[2]
        to_unit = command_parts[4]
    except (ValueError, IndexError):
        await message.reply("⚠️ Неверный формат! Используйте: `/convert 100 км в мили`", parse_mode="Markdown")
        return

    result = None
    unit_type = ""

    # Температура
    if from_unit.upper() in ['C', 'F', 'K'] and to_unit.upper() in ['C', 'F', 'K']:
        unit_type = "температуры"
        if from_unit.upper() == 'C' and to_unit.upper() == 'F':
            result = UnitConverter.celsius_to_fahrenheit(value)
        elif from_unit.upper() == 'F' and to_unit.upper() == 'C':
            result = UnitConverter.fahrenheit_to_celsius(value)
        elif from_unit.upper() == 'C' and to_unit.upper() == 'K':
            result = UnitConverter.celsius_to_kelvin(value)
        elif from_unit.upper() == 'K' and to_unit.upper() == 'C':
            result = value - 273.15

    # Расстояние
    elif from_unit.lower() in UnitConverter.DISTANCE_TO_METERS and to_unit.lower() in UnitConverter.DISTANCE_TO_METERS:
        unit_type = "расстояния"
        result = UnitConverter.convert_distance(value, from_unit, to_unit)

    # Вес
    elif from_unit.lower() in UnitConverter.WEIGHT_TO_GRAMS and to_unit.lower() in UnitConverter.WEIGHT_TO_GRAMS:
        unit_type = "веса"
        result = UnitConverter.convert_weight(value, from_unit, to_unit)

    # Объем
    elif from_unit.lower() in UnitConverter.VOLUME_TO_LITERS and to_unit.lower() in UnitConverter.VOLUME_TO_LITERS:
        unit_type = "объема"
        result = UnitConverter.convert_volume(value, from_unit, to_unit)

    # Скорость
    elif from_unit.lower() in UnitConverter.SPEED_TO_MPS and to_unit.lower() in UnitConverter.SPEED_TO_MPS:
        unit_type = "скорости"
        result = UnitConverter.convert_speed(value, from_unit, to_unit)

    if result is None:
        await message.reply("⚠️ Не могу конвертировать эти единицы. Проверьте правильность написания.")
        return

    # Форматируем результат
    if abs(result) < 0.01 or abs(result) > 1000000:
        result_str = f"{result:.2e}"
    else:
        result_str = f"{result:.2f}"

    response = (
        f"🔄 *Конвертация {unit_type}:*\n\n"
        f"{value} {from_unit} = **{result_str} {to_unit}**"
    )

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Conversion: {value} {from_unit} to {to_unit} in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send conversion: {e}")


@router.message(F.text.regexp(r"(?i)^(\d+(?:\.\d+)?)\s*(км|м|см|миля|фут)\s+в\s+(км|м|см|миля|фут)$"))
async def distance_text_trigger(message: Message) -> None:
    """
    Текстовый триггер для конвертации расстояния.

    Примеры:
    - "100 км в мили"
    - "5 футов в метры"
    """
    match = re.match(r"(?i)^(\d+(?:\.\d+)?)\s*(км|м|см|миля|фут)\s+в\s+(км|м|см|миля|фут)$", message.text)

    if not match:
        return

    value = float(match.group(1))
    from_unit = match.group(2).lower()
    to_unit = match.group(3).lower()

    result = UnitConverter.convert_distance(value, from_unit, to_unit)

    if result is None:
        return

    result_str = f"{result:.2f}"
    response = f"🔄 {value} {from_unit} = **{result_str} {to_unit}**"

    try:
        await message.reply(response, parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.error(f"Failed to send conversion: {e}")


@router.message(Command("currency"))
async def currency_info_command(message: Message) -> None:
    """
    Информация о конвертации валют.

    Использование:
    /currency
    """
    response = (
        "💱 *Конвертация валют*\n\n"
        "Для точной конвертации валют рекомендую использовать:\n\n"
        "• Google: `100 usd в рубли`\n"
        "• Яндекс: `100 usd в рубли`\n"
        "• Специализированные боты Telegram\n\n"
        "_Курсы валют постоянно меняются, поэтому лучше использовать "
        "актуальные источники данных_"
    )

    try:
        await message.reply(response, parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.error(f"Failed to send currency info: {e}")
