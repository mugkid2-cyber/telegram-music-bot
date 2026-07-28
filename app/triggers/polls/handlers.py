"""
Handler для создания опросов и голосований.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

router = Router(name="polls")


@router.message(Command("poll"))
async def create_poll_command(message: Message) -> None:
    """
    Команда для создания опроса.

    Использование:
    /poll Вопрос? | Вариант1 | Вариант2 | Вариант3
    """
    command_parts = message.text.split(maxsplit=1)

    if len(command_parts) < 2:
        await message.reply(
            "📊 *Создание опроса*\n\n"
            "Использование:\n"
            "`/poll Вопрос? | Вариант1 | Вариант2 | Вариант3`\n\n"
            "Примеры:\n"
            "`/poll Куда пойдем? | Кино | Парк | Кафе`\n"
            "`/poll Что заказать? | Пицца | Суши | Бургеры | Салаты`\n\n"
            "Минимум 2 варианта, максимум 10",
            parse_mode="Markdown"
        )
        return

    # Разбиваем на вопрос и варианты
    poll_data = command_parts[1].split('|')

    if len(poll_data) < 3:
        await message.reply("⚠️ Укажите вопрос и минимум 2 варианта через символ |")
        return

    question = poll_data[0].strip()
    options = [opt.strip() for opt in poll_data[1:] if opt.strip()]

    if len(options) < 2:
        await message.reply("⚠️ Нужно минимум 2 варианта ответа!")
        return

    if len(options) > 10:
        await message.reply("⚠️ Максимум 10 вариантов ответа!")
        return

    # Проверяем длину вопроса и вариантов
    if len(question) > 300:
        await message.reply("⚠️ Вопрос слишком длинный (максимум 300 символов)!")
        return

    for opt in options:
        if len(opt) > 100:
            await message.reply("⚠️ Вариант ответа слишком длинный (максимум 100 символов)!")
            return

    try:
        # Создаем опрос
        await message.bot.send_poll(
            chat_id=message.chat.id,
            question=question,
            options=options,
            is_anonymous=True,
            allows_multiple_answers=False
        )

        # Удаляем сообщение с командой
        try:
            await message.delete()
        except:
            pass

        logger.info(f"Poll created in chat {message.chat.id}: {question}")

    except TelegramAPIError as e:
        logger.error(f"Failed to create poll: {e}")
        await message.reply("❌ Не удалось создать опрос. Проверьте права бота.")


@router.message(Command("quiz"))
async def create_quiz_command(message: Message) -> None:
    """
    Команда для создания викторины.

    Использование:
    /quiz Вопрос? | Вариант1 | Вариант2 | Вариант3 | 2
    (Последняя цифра - номер правильного ответа, начиная с 1)
    """
    command_parts = message.text.split(maxsplit=1)

    if len(command_parts) < 2:
        await message.reply(
            "🎯 *Создание викторины*\n\n"
            "Использование:\n"
            "`/quiz Вопрос? | Вариант1 | Вариант2 | Вариант3 | N`\n"
            "где N - номер правильного ответа\n\n"
            "Пример:\n"
            "`/quiz Столица России? | Москва | Питер | Казань | 1`\n"
            "`/quiz 2+2=? | 3 | 4 | 5 | 2`",
            parse_mode="Markdown"
        )
        return

    # Разбиваем на части
    quiz_data = command_parts[1].split('|')

    if len(quiz_data) < 4:
        await message.reply("⚠️ Укажите вопрос, минимум 2 варианта и номер правильного ответа")
        return

    question = quiz_data[0].strip()

    # Последний элемент - номер правильного ответа
    try:
        correct_option_id = int(quiz_data[-1].strip()) - 1
    except ValueError:
        await message.reply("⚠️ Последнее значение должно быть номером правильного ответа (1, 2, 3...)")
        return

    # Варианты ответов
    options = [opt.strip() for opt in quiz_data[1:-1] if opt.strip()]

    if len(options) < 2:
        await message.reply("⚠️ Нужно минимум 2 варианта ответа!")
        return

    if len(options) > 10:
        await message.reply("⚠️ Максимум 10 вариантов ответа!")
        return

    if correct_option_id < 0 or correct_option_id >= len(options):
        await message.reply(f"⚠️ Номер правильного ответа должен быть от 1 до {len(options)}")
        return

    try:
        # Создаем викторину
        await message.bot.send_poll(
            chat_id=message.chat.id,
            question=question,
            options=options,
            type="quiz",
            correct_option_id=correct_option_id,
            is_anonymous=True
        )

        # Удаляем сообщение с командой
        try:
            await message.delete()
        except:
            pass

        logger.info(f"Quiz created in chat {message.chat.id}: {question}")

    except TelegramAPIError as e:
        logger.error(f"Failed to create quiz: {e}")
        await message.reply("❌ Не удалось создать викторину. Проверьте права бота.")


@router.message(Command("multipoll"))
async def create_multipoll_command(message: Message) -> None:
    """
    Команда для создания опроса с множественным выбором.

    Использование:
    /multipoll Вопрос? | Вариант1 | Вариант2 | Вариант3
    """
    command_parts = message.text.split(maxsplit=1)

    if len(command_parts) < 2:
        await message.reply(
            "📊 *Опрос с множественным выбором*\n\n"
            "Использование:\n"
            "`/multipoll Вопрос? | Вариант1 | Вариант2 | Вариант3`\n\n"
            "Пример:\n"
            "`/multipoll Что любите? | Кофе | Чай | Сок | Вода`\n\n"
            "_Можно выбрать несколько вариантов_",
            parse_mode="Markdown"
        )
        return

    # Разбиваем на вопрос и варианты
    poll_data = command_parts[1].split('|')

    if len(poll_data) < 3:
        await message.reply("⚠️ Укажите вопрос и минимум 2 варианта через символ |")
        return

    question = poll_data[0].strip()
    options = [opt.strip() for opt in poll_data[1:] if opt.strip()]

    if len(options) < 2:
        await message.reply("⚠️ Нужно минимум 2 варианта ответа!")
        return

    if len(options) > 10:
        await message.reply("⚠️ Максимум 10 вариантов ответа!")
        return

    try:
        # Создаем опрос с множественным выбором
        await message.bot.send_poll(
            chat_id=message.chat.id,
            question=question,
            options=options,
            is_anonymous=True,
            allows_multiple_answers=True
        )

        # Удаляем сообщение с командой
        try:
            await message.delete()
        except:
            pass

        logger.info(f"Multi-poll created in chat {message.chat.id}: {question}")

    except TelegramAPIError as e:
        logger.error(f"Failed to create multi-poll: {e}")
        await message.reply("❌ Не удалось создать опрос. Проверьте права бота.")


@router.message(Command("anon"))
async def toggle_anonymous_command(message: Message) -> None:
    """
    Информация об анонимных опросах.

    Использование:
    /anon
    """
    response = (
        "🕵️ *Анонимность опросов*\n\n"
        "Все опросы, создаваемые этим ботом, анонимные по умолчанию.\n\n"
        "Это означает:\n"
        "• Никто не видит, кто как проголосовал\n"
        "• Видны только общие результаты\n"
        "• Администраторы также не видят голоса\n\n"
        "_Для создания неанонимного опроса используйте "
        "встроенные возможности Telegram_"
    )

    try:
        await message.reply(response, parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.error(f"Failed to send anon info: {e}")
