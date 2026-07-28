"""
Handler для напоминаний и таймеров.
"""
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

router = Router(name="reminders")


def parse_time_string(time_str: str) -> Optional[int]:
    """
    Парсит строку времени и возвращает количество секунд.

    Поддерживаемые форматы:
    - "5м" или "5 минут" - минуты
    - "2ч" или "2 часа" - часы
    - "30с" или "30 секунд" - секунды

    Args:
        time_str: Строка с временем

    Returns:
        Количество секунд или None если не удалось распарсить
    """
    time_str = time_str.lower().strip()

    # Минуты
    if 'м' in time_str or 'мин' in time_str:
        match = re.search(r'(\d+)', time_str)
        if match:
            return int(match.group(1)) * 60

    # Часы
    if 'ч' in time_str or 'час' in time_str:
        match = re.search(r'(\d+)', time_str)
        if match:
            return int(match.group(1)) * 3600

    # Секунды
    if 'с' in time_str or 'сек' in time_str:
        match = re.search(r'(\d+)', time_str)
        if match:
            return int(match.group(1))

    # Просто число - считаем минутами
    match = re.search(r'^(\d+)$', time_str)
    if match:
        return int(match.group(1)) * 60

    return None


def format_time_remaining(seconds: int) -> str:
    """
    Форматирует секунды в читаемый формат.

    Args:
        seconds: Количество секунд

    Returns:
        Отформатированная строка
    """
    if seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes > 0:
            return f"{hours}ч {minutes}м"
        return f"{hours}ч"
    elif seconds >= 60:
        minutes = seconds // 60
        secs = seconds % 60
        if secs > 0:
            return f"{minutes}м {secs}с"
        return f"{minutes}м"
    else:
        return f"{seconds}с"


@router.message(Command("remind"))
async def remind_command(message: Message) -> None:
    """
    Команда для установки напоминания.

    Использование:
    /remind 5м купить молоко
    /remind 1ч позвонить маме
    /remind 30с проверить чайник
    """
    command_parts = message.text.split(maxsplit=2)

    if len(command_parts) < 3:
        await message.reply(
            "⏰ *Напоминания*\n\n"
            "Использование:\n"
            "`/remind [время] [текст]`\n\n"
            "Примеры:\n"
            "`/remind 5м купить молоко`\n"
            "`/remind 1ч позвонить маме`\n"
            "`/remind 30с проверить духовку`\n\n"
            "Время: с (секунды), м (минуты), ч (часы)",
            parse_mode="Markdown"
        )
        return

    time_str = command_parts[1]
    reminder_text = command_parts[2]

    # Парсим время
    seconds = parse_time_string(time_str)

    if seconds is None:
        await message.reply("⚠️ Не могу понять время. Используй формат: 5м, 1ч, 30с")
        return

    # Ограничения
    max_time = 24 * 3600  # 24 часа
    if seconds > max_time:
        await message.reply("⚠️ Максимальное время напоминания - 24 часа!")
        return

    if seconds < 10:
        await message.reply("⚠️ Минимальное время напоминания - 10 секунд!")
        return

    # Подтверждение
    time_formatted = format_time_remaining(seconds)
    reminder_time = datetime.now() + timedelta(seconds=seconds)

    confirmation = (
        f"⏰ *Напоминание установлено!*\n\n"
        f"📝 {reminder_text}\n"
        f"⏱️ Через: {time_formatted}\n"
        f"🕐 Время: {reminder_time.strftime('%H:%M')}"
    )

    try:
        status_msg = await message.reply(confirmation, parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.error(f"Failed to send reminder confirmation: {e}")
        return

    # Запускаем таймер в фоне
    asyncio.create_task(
        send_reminder(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            reminder_text=reminder_text,
            seconds=seconds,
            reply_to_message_id=message.message_id
        )
    )

    logger.info(
        f"Reminder set: {seconds}s for user {message.from_user.id} "
        f"in chat {message.chat.id}"
    )


async def send_reminder(
    bot,
    chat_id: int,
    user_id: int,
    reminder_text: str,
    seconds: int,
    reply_to_message_id: int
) -> None:
    """
    Отправляет напоминание после ожидания.

    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        user_id: ID пользователя
        reminder_text: Текст напоминания
        seconds: Секунд до напоминания
        reply_to_message_id: ID сообщения для ответа
    """
    try:
        # Ждём
        await asyncio.sleep(seconds)

        # Отправляем напоминание
        reminder_msg = (
            f"⏰ *НАПОМИНАНИЕ!*\n\n"
            f"📝 {reminder_text}"
        )

        await bot.send_message(
            chat_id=chat_id,
            text=reminder_msg,
            reply_to_message_id=reply_to_message_id,
            parse_mode="Markdown"
        )

        logger.info(f"Reminder sent to user {user_id} in chat {chat_id}")

    except asyncio.CancelledError:
        logger.info(f"Reminder cancelled for user {user_id}")
    except Exception as e:
        logger.error(f"Error sending reminder: {e}")


@router.message(Command("timer"))
async def timer_command(message: Message) -> None:
    """
    Команда для простого таймера.

    Использование:
    /timer 5м
    /timer 1ч
    """
    command_parts = message.text.split(maxsplit=1)

    if len(command_parts) < 2:
        await message.reply(
            "⏱️ *Таймер*\n\n"
            "Использование:\n"
            "`/timer [время]`\n\n"
            "Примеры:\n"
            "`/timer 5м`\n"
            "`/timer 1ч`\n"
            "`/timer 30с`",
            parse_mode="Markdown"
        )
        return

    time_str = command_parts[1]

    # Парсим время
    seconds = parse_time_string(time_str)

    if seconds is None:
        await message.reply("⚠️ Не могу понять время. Используй формат: 5м, 1ч, 30с")
        return

    # Ограничения
    max_time = 24 * 3600  # 24 часа
    if seconds > max_time:
        await message.reply("⚠️ Максимальное время таймера - 24 часа!")
        return

    if seconds < 10:
        await message.reply("⚠️ Минимальное время таймера - 10 секунд!")
        return

    # Подтверждение
    time_formatted = format_time_remaining(seconds)

    confirmation = f"⏱️ Таймер запущен на {time_formatted}"

    try:
        await message.reply(confirmation)
    except TelegramAPIError as e:
        logger.error(f"Failed to send timer confirmation: {e}")
        return

    # Запускаем таймер
    asyncio.create_task(
        send_timer_notification(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            seconds=seconds,
            reply_to_message_id=message.message_id
        )
    )

    logger.info(
        f"Timer set: {seconds}s for user {message.from_user.id} "
        f"in chat {message.chat.id}"
    )


async def send_timer_notification(
    bot,
    chat_id: int,
    user_id: int,
    seconds: int,
    reply_to_message_id: int
) -> None:
    """
    Отправляет уведомление о завершении таймера.

    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        user_id: ID пользователя
        seconds: Секунд таймера
        reply_to_message_id: ID сообщения для ответа
    """
    try:
        # Ждём
        await asyncio.sleep(seconds)

        # Отправляем уведомление
        time_formatted = format_time_remaining(seconds)

        notification = f"⏱️ *ВРЕМЯ ВЫШЛО!*\n\nТаймер на {time_formatted} завершён! ⏰"

        await bot.send_message(
            chat_id=chat_id,
            text=notification,
            reply_to_message_id=reply_to_message_id,
            parse_mode="Markdown"
        )

        logger.info(f"Timer notification sent to user {user_id} in chat {chat_id}")

    except asyncio.CancelledError:
        logger.info(f"Timer cancelled for user {user_id}")
    except Exception as e:
        logger.error(f"Error sending timer notification: {e}")


@router.message(F.text.regexp(r"(?i)^напомни через\s+(.+?)\s+(.+)$"))
async def remind_text_trigger(message: Message) -> None:
    """
    Текстовый триггер для напоминаний.

    Примеры:
    - "напомни через 5м купить молоко"
    - "напомни через 1ч позвонить"
    """
    match = re.match(r"(?i)^напомни через\s+(.+?)\s+(.+)$", message.text)
    if not match:
        return

    time_str = match.group(1).strip()
    reminder_text = match.group(2).strip()

    # Парсим время
    seconds = parse_time_string(time_str)

    if seconds is None:
        await message.reply("⚠️ Не могу понять время. Используй: 5м, 1ч, 30с")
        return

    # Ограничения
    if seconds > 24 * 3600:
        await message.reply("⚠️ Максимум 24 часа!")
        return

    if seconds < 10:
        await message.reply("⚠️ Минимум 10 секунд!")
        return

    # Подтверждение
    time_formatted = format_time_remaining(seconds)

    confirmation = f"⏰ Хорошо, напомню через {time_formatted}"

    try:
        await message.reply(confirmation)
    except TelegramAPIError as e:
        logger.error(f"Failed to send reminder confirmation: {e}")
        return

    # Запускаем таймер
    asyncio.create_task(
        send_reminder(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            reminder_text=reminder_text,
            seconds=seconds,
            reply_to_message_id=message.message_id
        )
    )
