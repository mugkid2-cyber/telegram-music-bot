"""
Handler для работы с текстом и его анализа.
"""
import re
import logging
from collections import Counter
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

router = Router(name="text_tools")


def analyze_text(text: str) -> dict:
    """
    Анализирует текст и возвращает статистику.

    Args:
        text: Текст для анализа

    Returns:
        Словарь со статистикой
    """
    # Базовая статистика
    char_count = len(text)
    char_no_spaces = len(text.replace(" ", ""))
    word_count = len(text.split())
    line_count = text.count('\n') + 1

    # Подсчет букв и цифр
    letters = sum(c.isalpha() for c in text)
    digits = sum(c.isdigit() for c in text)
    spaces = text.count(' ')

    # Уникальные слова
    words = text.lower().split()
    unique_words = len(set(words))

    # Самые частые слова (топ 5)
    word_freq = Counter(words)
    top_words = word_freq.most_common(5)

    return {
        'char_count': char_count,
        'char_no_spaces': char_no_spaces,
        'word_count': word_count,
        'line_count': line_count,
        'letters': letters,
        'digits': digits,
        'spaces': spaces,
        'unique_words': unique_words,
        'top_words': top_words
    }


def reverse_text(text: str) -> str:
    """Переворачивает текст задом наперед."""
    return text[::-1]


def count_emoji(text: str) -> int:
    """Подсчитывает количество эмодзи в тексте."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # эмоции
        "\U0001F300-\U0001F5FF"  # символы и пиктограммы
        "\U0001F680-\U0001F6FF"  # транспорт и символы карт
        "\U0001F1E0-\U0001F1FF"  # флаги
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    return len(emoji_pattern.findall(text))


@router.message(Command("count"))
async def count_command(message: Message) -> None:
    """
    Команда для подсчета статистики текста.

    Использование:
    /count - ответом на сообщение
    /count текст - для указанного текста
    """
    # Получаем текст
    text = None

    # Если команда ответом на сообщение
    if message.reply_to_message and message.reply_to_message.text:
        text = message.reply_to_message.text
    else:
        # Извлекаем текст из команды
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) >= 2:
            text = command_parts[1]

    if not text:
        await message.reply(
            "📊 *Анализ текста*\n\n"
            "Использование:\n"
            "• Ответьте на сообщение командой `/count`\n"
            "• Или напишите `/count ваш текст`",
            parse_mode="Markdown"
        )
        return

    # Анализируем текст
    stats = analyze_text(text)
    emoji_count = count_emoji(text)

    response = (
        f"📊 *Статистика текста:*\n\n"
        f"📝 Символов: {stats['char_count']}\n"
        f"📝 Без пробелов: {stats['char_no_spaces']}\n"
        f"📖 Слов: {stats['word_count']}\n"
        f"🔤 Уникальных слов: {stats['unique_words']}\n"
        f"📄 Строк: {stats['line_count']}\n"
        f"🔤 Букв: {stats['letters']}\n"
        f"🔢 Цифр: {stats['digits']}\n"
        f"⬜ Пробелов: {stats['spaces']}\n"
        f"😀 Эмодзи: {emoji_count}"
    )

    # Добавляем топ слов если есть
    if stats['top_words'] and stats['word_count'] > 5:
        response += "\n\n*Частые слова:*\n"
        for word, count in stats['top_words'][:3]:
            if len(word) > 2:  # Игнорируем короткие слова
                response += f"• {word}: {count}\n"

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Text analysis in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send text stats: {e}")


@router.message(Command("reverse"))
async def reverse_command(message: Message) -> None:
    """
    Команда для переворота текста.

    Использование:
    /reverse - ответом на сообщение
    /reverse текст - для указанного текста
    """
    # Получаем текст
    text = None

    # Если команда ответом на сообщение
    if message.reply_to_message and message.reply_to_message.text:
        text = message.reply_to_message.text
    else:
        # Извлекаем текст из команды
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) >= 2:
            text = command_parts[1]

    if not text:
        await message.reply(
            "🔄 *Переворот текста*\n\n"
            "Использование:\n"
            "• Ответьте на сообщение командой `/reverse`\n"
            "• Или напишите `/reverse ваш текст`",
            parse_mode="Markdown"
        )
        return

    # Переворачиваем текст
    reversed_text = reverse_text(text)

    response = f"🔄 *Перевернутый текст:*\n\n{reversed_text}"

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Text reversed in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send reversed text: {e}")


@router.message(Command("upper"))
async def upper_command(message: Message) -> None:
    """
    Команда для преобразования текста в ВЕРХНИЙ РЕГИСТР.

    Использование:
    /upper - ответом на сообщение
    /upper текст - для указанного текста
    """
    # Получаем текст
    text = None

    if message.reply_to_message and message.reply_to_message.text:
        text = message.reply_to_message.text
    else:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) >= 2:
            text = command_parts[1]

    if not text:
        await message.reply(
            "⬆️ *ВЕРХНИЙ РЕГИСТР*\n\n"
            "Использование:\n"
            "• Ответьте на сообщение командой `/upper`\n"
            "• Или напишите `/upper текст`",
            parse_mode="Markdown"
        )
        return

    response = text.upper()

    try:
        await message.reply(response)
        logger.info(f"Text uppercased in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send uppercased text: {e}")


@router.message(Command("lower"))
async def lower_command(message: Message) -> None:
    """
    Команда для преобразования текста в нижний регистр.

    Использование:
    /lower - ответом на сообщение
    /lower текст - для указанного текста
    """
    # Получаем текст
    text = None

    if message.reply_to_message and message.reply_to_message.text:
        text = message.reply_to_message.text
    else:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) >= 2:
            text = command_parts[1]

    if not text:
        await message.reply(
            "⬇️ *нижний регистр*\n\n"
            "Использование:\n"
            "• Ответьте на сообщение командой `/lower`\n"
            "• Или напишите `/lower ТЕКСТ`",
            parse_mode="Markdown"
        )
        return

    response = text.lower()

    try:
        await message.reply(response)
        logger.info(f"Text lowercased in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send lowercased text: {e}")


@router.message(Command("capitalize"))
async def capitalize_command(message: Message) -> None:
    """
    Команда для преобразования Первой Буквы Каждого Слова.

    Использование:
    /capitalize - ответом на сообщение
    /capitalize текст - для указанного текста
    """
    # Получаем текст
    text = None

    if message.reply_to_message and message.reply_to_message.text:
        text = message.reply_to_message.text
    else:
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) >= 2:
            text = command_parts[1]

    if not text:
        await message.reply(
            "🔠 *Заглавные Буквы*\n\n"
            "Использование:\n"
            "• Ответьте на сообщение командой `/capitalize`\n"
            "• Или напишите `/capitalize текст для преобразования`",
            parse_mode="Markdown"
        )
        return

    response = text.title()

    try:
        await message.reply(response)
        logger.info(f"Text capitalized in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send capitalized text: {e}")


@router.message(F.text.regexp(r"(?i)^(посчитай слова|статистика текста|анализ текста)$"))
async def count_text_trigger(message: Message) -> None:
    """
    Текстовый триггер для анализа текста.

    Примеры:
    - "посчитай слова" (ответом на сообщение)
    - "статистика текста"
    """
    if not message.reply_to_message or not message.reply_to_message.text:
        await message.reply("⚠️ Ответьте этим на сообщение с текстом")
        return

    text = message.reply_to_message.text
    stats = analyze_text(text)

    response = (
        f"📊 *Статистика:*\n\n"
        f"Символов: {stats['char_count']}\n"
        f"Слов: {stats['word_count']}\n"
        f"Строк: {stats['line_count']}"
    )

    try:
        await message.reply(response, parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.error(f"Failed to send stats: {e}")
