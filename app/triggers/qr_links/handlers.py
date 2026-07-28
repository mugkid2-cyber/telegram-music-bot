"""
Handler для работы с QR-кодами и короткими ссылками.
"""
import logging
import hashlib
from urllib.parse import urlparse, quote
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

router = Router(name="qr_links")


def is_valid_url(url: str) -> bool:
    """
    Проверяет, является ли строка валидным URL.

    Args:
        url: Строка для проверки

    Returns:
        True если URL валиден
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False


def generate_qr_url(text: str) -> str:
    """
    Генерирует URL для QR-кода через API.

    Args:
        text: Текст для кодирования

    Returns:
        URL изображения QR-кода
    """
    # Используем бесплатный API для генерации QR-кодов
    encoded_text = quote(text)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={encoded_text}"


def shorten_text(text: str, max_length: int = 50) -> str:
    """
    Сокращает текст для отображения.

    Args:
        text: Исходный текст
        max_length: Максимальная длина

    Returns:
        Сокращенный текст
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


@router.message(Command("qr"))
async def generate_qr_command(message: Message) -> None:
    """
    Команда для генерации QR-кода.

    Использование:
    /qr текст или ссылка
    /qr https://example.com
    """
    command_parts = message.text.split(maxsplit=1)

    if len(command_parts) < 2:
        await message.reply(
            "📱 *Генератор QR-кодов*\n\n"
            "Использование:\n"
            "`/qr [текст или ссылка]`\n\n"
            "Примеры:\n"
            "`/qr https://google.com`\n"
            "`/qr Мой номер: +79991234567`\n"
            "`/qr Контакты компании`\n\n"
            "Можно закодировать:\n"
            "• Ссылки\n"
            "• Текст\n"
            "• Телефоны\n"
            "• Email\n"
            "• Координаты",
            parse_mode="Markdown"
        )
        return

    data = command_parts[1].strip()

    # Ограничение на длину
    if len(data) > 500:
        await message.reply("⚠️ Максимальная длина текста - 500 символов!")
        return

    # Генерируем QR-код
    qr_url = generate_qr_url(data)

    try:
        # Отправляем QR-код как фото
        caption = f"📱 QR-код для:\n`{shorten_text(data, 100)}`"

        await message.reply_photo(
            photo=qr_url,
            caption=caption,
            parse_mode="Markdown"
        )

        logger.info(f"QR code generated in chat {message.chat.id}")

    except TelegramAPIError as e:
        logger.error(f"Failed to send QR code: {e}")
        await message.reply("❌ Не удалось сгенерировать QR-код. Попробуйте позже.")


@router.message(Command("shortlink"))
async def short_link_info_command(message: Message) -> None:
    """
    Информация о коротких ссылках.

    Использование:
    /shortlink
    """
    response = (
        "🔗 *Короткие ссылки*\n\n"
        "Для создания коротких ссылок используйте сервисы:\n\n"
        "• [Bitly](https://bitly.com) - популярный сервис\n"
        "• [TinyURL](https://tinyurl.com) - простой и быстрый\n"
        "• [Clck.ru](https://clck.ru) - русский сервис\n"
        "• [Goo.gl](https://goo.gl) - от Google\n\n"
        "Для QR-кодов используйте команду `/qr`"
    )

    try:
        await message.reply(
            response,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    except TelegramAPIError as e:
        logger.error(f"Failed to send shortlink info: {e}")


@router.message(Command("link"))
async def extract_link_command(message: Message) -> None:
    """
    Извлекает ссылки из текста сообщения.

    Использование:
    /link (ответом на сообщение)
    """
    if not message.reply_to_message:
        await message.reply(
            "🔗 *Извлечение ссылок*\n\n"
            "Ответьте этой командой на сообщение, "
            "чтобы извлечь из него все ссылки",
            parse_mode="Markdown"
        )
        return

    text = message.reply_to_message.text or message.reply_to_message.caption

    if not text:
        await message.reply("⚠️ В сообщении нет текста")
        return

    # Ищем ссылки
    import re
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, text)

    if not urls:
        await message.reply("🔍 Ссылки не найдены")
        return

    # Формируем ответ
    response = f"🔗 *Найдено ссылок: {len(urls)}*\n\n"

    for i, url in enumerate(urls, 1):
        response += f"{i}. {url}\n"

    try:
        await message.reply(
            response,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        logger.info(f"Links extracted in chat {message.chat.id}: {len(urls)} links")
    except TelegramAPIError as e:
        logger.error(f"Failed to send links: {e}")


@router.message(Command("barcode"))
async def generate_barcode_command(message: Message) -> None:
    """
    Команда для генерации штрих-кода.

    Использование:
    /barcode 1234567890
    """
    command_parts = message.text.split(maxsplit=1)

    if len(command_parts) < 2:
        await message.reply(
            "📊 *Генератор штрих-кодов*\n\n"
            "Использование:\n"
            "`/barcode [число]`\n\n"
            "Примеры:\n"
            "`/barcode 1234567890`\n"
            "`/barcode 4607012345678`\n\n"
            "_Поддерживаются форматы EAN-13, EAN-8, Code 128_",
            parse_mode="Markdown"
        )
        return

    code = command_parts[1].strip()

    # Проверяем, что это только цифры
    if not code.isdigit():
        await message.reply("⚠️ Штрих-код должен содержать только цифры!")
        return

    # Ограничения
    if len(code) < 8:
        await message.reply("⚠️ Минимальная длина штрих-кода - 8 цифр!")
        return

    if len(code) > 13:
        await message.reply("⚠️ Максимальная длина штрих-кода - 13 цифр!")
        return

    try:
        # Генерируем штрих-код через API
        barcode_url = f"https://barcodeapi.org/api/auto/{code}"

        await message.reply_photo(
            photo=barcode_url,
            caption=f"📊 Штрих-код: `{code}`",
            parse_mode="Markdown"
        )

        logger.info(f"Barcode generated in chat {message.chat.id}")

    except TelegramAPIError as e:
        logger.error(f"Failed to send barcode: {e}")
        await message.reply("❌ Не удалось сгенерировать штрих-код. Попробуйте позже.")


@router.message(F.text.regexp(r"(?i)^(создай qr|сделай qr|qr код)\s+(.+)$"))
async def qr_text_trigger(message: Message) -> None:
    """
    Текстовый триггер для генерации QR-кода.

    Примеры:
    - "создай qr https://google.com"
    - "сделай qr для этой ссылки"
    """
    import re
    match = re.match(r"(?i)^(создай qr|сделай qr|qr код)\s+(.+)$", message.text)

    if not match:
        return

    data = match.group(2).strip()

    if len(data) > 500:
        await message.reply("⚠️ Слишком длинный текст!")
        return

    qr_url = generate_qr_url(data)

    try:
        await message.reply_photo(
            photo=qr_url,
            caption=f"📱 QR-код готов"
        )
    except TelegramAPIError as e:
        logger.error(f"Failed to send QR: {e}")
