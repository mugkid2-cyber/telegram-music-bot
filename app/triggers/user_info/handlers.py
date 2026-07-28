"""
Handler для получения информации о пользователе и чате.
"""
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from aiogram.enums import ChatType

logger = logging.getLogger(__name__)

router = Router(name="user_info")


def format_date(timestamp: int) -> str:
    """
    Форматирует timestamp в читаемую дату.

    Args:
        timestamp: Unix timestamp

    Returns:
        Отформатированная дата
    """
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%d.%m.%Y %H:%M")


@router.message(Command("id"))
async def id_command(message: Message) -> None:
    """
    Команда для получения ID пользователя и чата.

    Использование:
    /id - ваш ID
    /id (ответом на сообщение) - ID другого пользователя
    """
    target_user = message.from_user

    # Если команда ответом на сообщение
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user

    response = (
        f"🆔 *Информация об ID:*\n\n"
        f"👤 Пользователь: {target_user.first_name}\n"
        f"🆔 User ID: `{target_user.id}`\n"
    )

    if target_user.username:
        response += f"📱 Username: @{target_user.username}\n"

    response += f"💬 Chat ID: `{message.chat.id}`"

    # Если это группа
    if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        response += f"\n🏷️ Chat Type: {message.chat.type}"

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"ID info shown in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send ID info: {e}")


@router.message(Command("me"))
async def me_command(message: Message) -> None:
    """
    Команда для получения информации о себе.

    Использование:
    /me
    """
    user = message.from_user

    response = f"👤 *Информация о вас:*\n\n"

    if user.first_name:
        response += f"Имя: {user.first_name}\n"

    if user.last_name:
        response += f"Фамилия: {user.last_name}\n"

    if user.username:
        response += f"Username: @{user.username}\n"

    response += f"ID: `{user.id}`\n"

    if user.language_code:
        response += f"Язык: {user.language_code.upper()}\n"

    # Статус
    if user.is_bot:
        response += f"Статус: 🤖 Бот\n"
    elif user.is_premium:
        response += f"Статус: ⭐ Premium\n"

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"User info shown for {user.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send user info: {e}")


@router.message(Command("chatinfo"))
async def chatinfo_command(message: Message) -> None:
    """
    Команда для получения информации о чате.

    Использование:
    /chatinfo
    """
    chat = message.chat

    response = f"💬 *Информация о чате:*\n\n"

    if chat.title:
        response += f"Название: {chat.title}\n"

    response += f"ID: `{chat.id}`\n"
    response += f"Тип: {chat.type}\n"

    if chat.username:
        response += f"Username: @{chat.username}\n"

    # Для групп показываем количество участников
    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        try:
            members_count = await message.bot.get_chat_member_count(chat.id)
            response += f"👥 Участников: {members_count}\n"
        except:
            pass

        # Описание
        if chat.description:
            response += f"\n📝 Описание:\n{chat.description[:200]}\n"

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Chat info shown for {chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send chat info: {e}")


@router.message(Command("ping"))
async def ping_command(message: Message) -> None:
    """
    Команда для проверки скорости ответа бота.

    Использование:
    /ping
    """
    # Время получения сообщения
    received_time = datetime.now()

    # Отправляем ответ
    response_msg = await message.reply("🏓 Pong!")

    # Вычисляем задержку
    sent_time = datetime.now()
    delay = (sent_time - received_time).total_seconds() * 1000

    # Обновляем сообщение с задержкой
    try:
        await response_msg.edit_text(
            f"🏓 Pong!\n\n"
            f"⚡ Задержка: {delay:.0f}ms"
        )
        logger.info(f"Ping: {delay:.0f}ms in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to edit ping message: {e}")


@router.message(Command("status"))
async def status_command(message: Message) -> None:
    """
    Команда для получения статуса пользователя в чате.

    Использование:
    /status - ваш статус
    /status (ответом) - статус другого пользователя
    """
    # Проверяем, что это группа
    if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await message.reply("⚠️ Эта команда работает только в группах!")
        return

    target_user = message.from_user

    # Если команда ответом на сообщение
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user

    try:
        # Получаем информацию о пользователе в чате
        member = await message.bot.get_chat_member(
            chat_id=message.chat.id,
            user_id=target_user.id
        )

        response = f"👤 *{target_user.first_name}*\n\n"

        # Статус
        status_emoji = {
            "creator": "👑",
            "administrator": "⭐",
            "member": "👤",
            "restricted": "🚫",
            "left": "👋",
            "kicked": "❌"
        }

        status_text = {
            "creator": "Создатель",
            "administrator": "Администратор",
            "member": "Участник",
            "restricted": "Ограничен",
            "left": "Покинул чат",
            "kicked": "Исключен"
        }

        emoji = status_emoji.get(member.status, "❓")
        status = status_text.get(member.status, member.status)

        response += f"Статус: {emoji} {status}\n"

        # Права администратора
        if member.status == "administrator":
            response += "\n*Права:*\n"
            if member.can_delete_messages:
                response += "• Удаление сообщений ✅\n"
            if member.can_restrict_members:
                response += "• Ограничение участников ✅\n"
            if member.can_promote_members:
                response += "• Назначение администраторов ✅\n"
            if member.can_pin_messages:
                response += "• Закрепление сообщений ✅\n"

        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Status shown for user {target_user.id} in chat {message.chat.id}")

    except TelegramAPIError as e:
        logger.error(f"Failed to get member status: {e}")
        await message.reply("❌ Не удалось получить статус пользователя")


@router.message(F.text.regexp(r"(?i)^(мой ид|мой айди|мой id)$"))
async def my_id_text_trigger(message: Message) -> None:
    """
    Текстовый триггер для получения своего ID.

    Примеры:
    - "мой ид"
    - "мой айди"
    - "мой id"
    """
    user = message.from_user

    response = f"🆔 Ваш ID: `{user.id}`"

    try:
        await message.reply(response, parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.error(f"Failed to send ID: {e}")
