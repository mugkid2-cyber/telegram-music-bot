"""
Handler для удаления сообщений в чате.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from aiogram.enums import ChatType

logger = logging.getLogger(__name__)

router = Router(name="message_cleaner")


@router.message(Command("cms"))
async def clear_messages_command(message: Message) -> None:
    """
    Команда для удаления сообщений в чате.

    Использование:
    /cms [количество] - удалить указанное количество сообщений (максимум 50)

    Требования:
    - Работает только в группах/супергруппах
    - Пользователь должен быть администратором
    - Бот должен иметь права на удаление сообщений
    """
    # Проверяем, что команда в группе
    if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await message.reply("⚠️ Эта команда работает только в группах!")
        return

    # Проверяем права пользователя
    try:
        chat_member = await message.bot.get_chat_member(
            chat_id=message.chat.id,
            user_id=message.from_user.id
        )

        if chat_member.status not in ["creator", "administrator"]:
            await message.reply("⚠️ Только администраторы могут удалять сообщения!")
            return
    except TelegramAPIError as e:
        logger.error(f"Error checking admin status: {e}")
        await message.reply("❌ Не удалось проверить права администратора")
        return

    # Парсим количество сообщений
    command_parts = message.text.split(maxsplit=1)

    if len(command_parts) < 2:
        await message.reply(
            "📝 *Использование:*\n"
            "`/cms [количество]`\n\n"
            "Например: `/cms 10` - удалит 10 последних сообщений\n"
            "Максимум: 50 сообщений",
            parse_mode="Markdown"
        )
        return

    try:
        count = int(command_parts[1])
    except ValueError:
        await message.reply("⚠️ Укажите корректное число!")
        return

    # Проверяем ограничения
    if count < 1:
        await message.reply("⚠️ Количество должно быть больше 0!")
        return

    if count > 50:
        await message.reply("⚠️ Максимум 50 сообщений за раз!")
        return

    # Отправляем статус
    status_msg = await message.reply(f"🗑️ Удаляю {count} сообщений...")

    # Удаляем сообщения
    deleted_count = 0
    failed_count = 0

    # ID текущего сообщения команды
    current_message_id = message.message_id

    # Пытаемся удалить сообщения начиная с текущего и идя назад
    for i in range(count + 1):  # +1 чтобы включить само сообщение с командой
        message_id_to_delete = current_message_id - i

        if message_id_to_delete < 1:
            break

        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=message_id_to_delete
            )
            deleted_count += 1
        except TelegramAPIError as e:
            failed_count += 1
            # Логируем только первые несколько ошибок
            if failed_count <= 3:
                logger.warning(f"Failed to delete message {message_id_to_delete}: {e}")

    # Обновляем статус
    result_text = f"✅ Удалено: {deleted_count} сообщений"
    if failed_count > 0:
        result_text += f"\n⚠️ Не удалось удалить: {failed_count}"

    try:
        await status_msg.edit_text(result_text)

        # Удаляем статусное сообщение через 5 секунд
        import asyncio
        await asyncio.sleep(5)
        await status_msg.delete()
    except TelegramAPIError:
        pass

    logger.info(
        f"Messages cleared: deleted={deleted_count}, failed={failed_count}, "
        f"chat={message.chat.id}, user={message.from_user.id}"
    )


@router.message(F.text.regexp(r"^-смс\s+(\d+)$"))
async def clear_messages_text_trigger(message: Message) -> None:
    """
    Текстовый триггер для удаления сообщений.

    Примеры:
    - "-смс 10"
    - "-смс 25"
    """
    # Проверяем, что команда в группе
    if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await message.reply("⚠️ Эта команда работает только в группах!")
        return

    # Проверяем права пользователя
    try:
        chat_member = await message.bot.get_chat_member(
            chat_id=message.chat.id,
            user_id=message.from_user.id
        )

        if chat_member.status not in ["creator", "administrator"]:
            await message.reply("⚠️ Только администраторы могут удалять сообщения!")
            return
    except TelegramAPIError as e:
        logger.error(f"Error checking admin status: {e}")
        await message.reply("❌ Не удалось проверить права администратора")
        return

    # Извлекаем количество из регулярки
    import re
    match = re.match(r"^-смс\s+(\d+)$", message.text)
    count = int(match.group(1))

    # Проверяем ограничения
    if count < 1:
        await message.reply("⚠️ Количество должно быть больше 0!")
        return

    if count > 50:
        await message.reply("⚠️ Максимум 50 сообщений за раз!")
        return

    # Отправляем статус
    status_msg = await message.reply(f"🗑️ Удаляю {count} сообщений...")

    # Удаляем сообщения
    deleted_count = 0
    failed_count = 0

    # ID текущего сообщения
    current_message_id = message.message_id

    # Пытаемся удалить сообщения начиная с текущего и идя назад
    for i in range(count + 1):  # +1 чтобы включить само сообщение с командой
        message_id_to_delete = current_message_id - i

        if message_id_to_delete < 1:
            break

        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=message_id_to_delete
            )
            deleted_count += 1
        except TelegramAPIError as e:
            failed_count += 1
            # Логируем только первые несколько ошибок
            if failed_count <= 3:
                logger.warning(f"Failed to delete message {message_id_to_delete}: {e}")

    # Обновляем статус
    result_text = f"✅ Удалено: {deleted_count} сообщений"
    if failed_count > 0:
        result_text += f"\n⚠️ Не удалось удалить: {failed_count}"

    try:
        await status_msg.edit_text(result_text)

        # Удаляем статусное сообщение через 5 секунд
        import asyncio
        await asyncio.sleep(5)
        await status_msg.delete()
    except TelegramAPIError:
        pass

    logger.info(
        f"Messages cleared: deleted={deleted_count}, failed={failed_count}, "
        f"chat={message.chat.id}, user={message.from_user.id}"
    )
