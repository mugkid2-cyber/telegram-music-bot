"""
Handler для генерации паролей и случайных данных.
"""
import random
import string
import secrets
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

router = Router(name="password_generator")


def generate_password(length: int = 16, use_symbols: bool = True, use_numbers: bool = True) -> str:
    """
    Генерирует криптографически стойкий пароль.

    Args:
        length: Длина пароля
        use_symbols: Использовать символы
        use_numbers: Использовать цифры

    Returns:
        Сгенерированный пароль
    """
    chars = string.ascii_letters

    if use_numbers:
        chars += string.digits

    if use_symbols:
        chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"

    # Используем secrets для криптографической стойкости
    password = ''.join(secrets.choice(chars) for _ in range(length))

    return password


def generate_pin(length: int = 4) -> str:
    """
    Генерирует случайный PIN-код.

    Args:
        length: Длина PIN-кода

    Returns:
        PIN-код
    """
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def generate_username() -> str:
    """
    Генерирует случайное имя пользователя.

    Returns:
        Имя пользователя
    """
    adjectives = [
        "Swift", "Brave", "Mighty", "Clever", "Silent", "Golden", "Silver", "Dark",
        "Light", "Wild", "Cosmic", "Electric", "Frozen", "Blazing", "Storm", "Shadow"
    ]

    nouns = [
        "Wolf", "Eagle", "Dragon", "Phoenix", "Tiger", "Hawk", "Lion", "Bear",
        "Fox", "Raven", "Falcon", "Panther", "Viper", "Shark", "Cobra", "Lynx"
    ]

    adjective = random.choice(adjectives)
    noun = random.choice(nouns)
    number = random.randint(10, 999)

    return f"{adjective}{noun}{number}"


@router.message(Command("genpass"))
async def generate_password_command(message: Message) -> None:
    """
    Команда для генерации пароля.

    Использование:
    /genpass - пароль 16 символов
    /genpass 24 - пароль 24 символа
    /genpass 12 simple - простой пароль без символов
    """
    command_parts = message.text.split()

    length = 16
    use_symbols = True
    use_numbers = True

    if len(command_parts) >= 2:
        try:
            length = int(command_parts[1])
        except ValueError:
            await message.reply("⚠️ Укажите корректную длину пароля!")
            return

    if len(command_parts) >= 3 and command_parts[2].lower() == "simple":
        use_symbols = False

    # Ограничения
    if length < 6:
        await message.reply("⚠️ Минимальная длина пароля - 6 символов!")
        return

    if length > 64:
        await message.reply("⚠️ Максимальная длина пароля - 64 символа!")
        return

    # Генерируем пароль
    password = generate_password(length, use_symbols, use_numbers)

    # Оценка сложности
    strength = "🟢 Сильный" if length >= 16 else "🟡 Средний" if length >= 12 else "🟠 Слабый"

    response = (
        f"🔐 *Сгенерированный пароль:*\n\n"
        f"`{password}`\n\n"
        f"Длина: {length} символов\n"
        f"Сложность: {strength}\n\n"
        f"_Скопируйте пароль и сохраните в надежном месте_"
    )

    try:
        # Отправляем в личку если возможно, иначе в чат
        await message.reply(response, parse_mode="Markdown")

        # Если это группа, предупреждаем
        if message.chat.type in ["group", "supergroup"]:
            await message.reply(
                "⚠️ *Внимание!* Пароль виден всем в чате. "
                "Используйте команду в личных сообщениях с ботом для безопасности.",
                parse_mode="Markdown"
            )

        logger.info(f"Password generated: length={length} in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send password: {e}")


@router.message(Command("genpin"))
async def generate_pin_command(message: Message) -> None:
    """
    Команда для генерации PIN-кода.

    Использование:
    /genpin - 4-значный PIN
    /genpin 6 - 6-значный PIN
    """
    command_parts = message.text.split()

    length = 4

    if len(command_parts) >= 2:
        try:
            length = int(command_parts[1])
        except ValueError:
            await message.reply("⚠️ Укажите корректную длину PIN!")
            return

    # Ограничения
    if length < 4:
        await message.reply("⚠️ Минимальная длина PIN - 4 цифры!")
        return

    if length > 8:
        await message.reply("⚠️ Максимальная длина PIN - 8 цифр!")
        return

    # Генерируем PIN
    pin = generate_pin(length)

    response = (
        f"🔢 *Сгенерированный PIN-код:*\n\n"
        f"`{pin}`\n\n"
        f"_Не используйте простые комбинации типа 1234 или 0000_"
    )

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"PIN generated: length={length} in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send PIN: {e}")


@router.message(Command("genuser"))
async def generate_username_command(message: Message) -> None:
    """
    Команда для генерации имени пользователя.

    Использование:
    /genuser - генерирует случайное имя
    """
    username = generate_username()

    response = f"👤 *Сгенерированное имя:*\n\n`{username}`"

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Username generated in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send username: {e}")


@router.message(Command("gencolor"))
async def generate_color_command(message: Message) -> None:
    """
    Команда для генерации случайного цвета.

    Использование:
    /gencolor - генерирует HEX цвет
    """
    # Генерируем случайный HEX цвет
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)

    hex_color = f"#{r:02x}{g:02x}{b:02x}".upper()
    rgb_color = f"RGB({r}, {g}, {b})"

    # Определяем тип цвета
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    color_type = "🌟 Светлый" if brightness > 128 else "🌙 Темный"

    response = (
        f"🎨 *Случайный цвет:*\n\n"
        f"HEX: `{hex_color}`\n"
        f"RGB: `{rgb_color}`\n"
        f"Тип: {color_type}"
    )

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Color generated in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send color: {e}")


@router.message(F.text.regexp(r"(?i)^(сгенерируй пароль|генерация пароля|пароль)$"))
async def password_text_trigger(message: Message) -> None:
    """
    Текстовый триггер для генерации пароля.

    Примеры:
    - "сгенерируй пароль"
    - "генерация пароля"
    """
    password = generate_password(16, True, True)

    response = f"🔐 *Ваш пароль:*\n\n`{password}`"

    try:
        await message.reply(response, parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.error(f"Failed to send password: {e}")
