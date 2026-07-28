"""
Handler для помощи в принятии решений.
"""
import random
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

router = Router(name="decision_maker")


@router.message(Command("choice"))
async def make_choice_command(message: Message) -> None:
    """
    Команда для случайного выбора из вариантов.

    Использование:
    /choice вариант1, вариант2, вариант3
    """
    command_parts = message.text.split(maxsplit=1)

    if len(command_parts) < 2:
        await message.reply(
            "🎲 *Помощь в выборе*\n\n"
            "Использование:\n"
            "`/choice вариант1, вариант2, вариант3`\n\n"
            "Пример:\n"
            "`/choice пицца, суши, бургеры`\n"
            "`/choice идти гулять, остаться дома`",
            parse_mode="Markdown"
        )
        return

    # Разбиваем варианты по запятой или слову "или"
    options_text = command_parts[1]

    # Пробуем разделить по запятой
    if ',' in options_text:
        options = [opt.strip() for opt in options_text.split(',') if opt.strip()]
    # Иначе по слову "или"
    elif ' или ' in options_text.lower():
        options = [opt.strip() for opt in options_text.lower().split(' или ') if opt.strip()]
    else:
        # Если нет разделителей, считаем что один вариант
        await message.reply(
            "⚠️ Укажите несколько вариантов через запятую или слово 'или'\n\n"
            "Пример: `/choice пицца, суши, бургеры`",
            parse_mode="Markdown"
        )
        return

    if len(options) < 2:
        await message.reply("⚠️ Нужно минимум 2 варианта для выбора!")
        return

    # Случайный выбор
    chosen = random.choice(options)

    # Формируем красивый ответ
    emojis = ["🎯", "✨", "🌟", "💫", "⭐", "🔮"]
    emoji = random.choice(emojis)

    response = (
        f"{emoji} *Мой выбор:*\n\n"
        f"**{chosen}**\n\n"
        f"_Из {len(options)} вариантов_"
    )

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Choice made from {len(options)} options in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send choice: {e}")


@router.message(Command("yesno"))
async def yes_no_command(message: Message) -> None:
    """
    Команда для простого ответа Да/Нет.

    Использование:
    /yesno [вопрос]
    """
    command_parts = message.text.split(maxsplit=1)
    question = command_parts[1] if len(command_parts) > 1 else None

    # Случайный ответ
    answers = [
        ("✅ **ДА**", "Определенно да!"),
        ("✅ **ДА**", "Да, можешь быть уверен"),
        ("✅ **ДА**", "Безусловно!"),
        ("✅ **ДА**", "Конечно, действуй!"),
        ("❌ **НЕТ**", "Нет, лучше не стоит"),
        ("❌ **НЕТ**", "Определенно нет"),
        ("❌ **НЕТ**", "Я бы не советовал"),
        ("❌ **НЕТ**", "Воздержись"),
        ("🤔 **ВОЗМОЖНО**", "Возможно, всё зависит от тебя"),
        ("🤔 **ВОЗМОЖНО**", "Шансы 50/50"),
        ("🤔 **ВОЗМОЖНО**", "Попробуй, но будь осторожен"),
        ("⏰ **ПОКА НЕТ**", "Сейчас не лучшее время"),
    ]

    answer, explanation = random.choice(answers)

    response = "🎱 *МАГИЧЕСКИЙ ШАР ОТВЕТОВ*\n\n"
    if question:
        response += f"❓ _{question}_\n\n"

    response += f"{answer}\n_{explanation}_"

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Yes/No answered in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send yes/no: {e}")


@router.message(Command("dice"))
async def roll_dice_command(message: Message) -> None:
    """
    Команда для броска кубика.

    Использование:
    /dice - бросить 1 кубик
    /dice 3 - бросить 3 кубика
    /dice 2d20 - бросить 2 кубика с 20 гранями
    """
    command_parts = message.text.split(maxsplit=1)

    # По умолчанию 1 кубик с 6 гранями
    num_dice = 1
    num_sides = 6

    if len(command_parts) > 1:
        dice_text = command_parts[1].strip()

        # Формат XdY (например, 2d20)
        if 'd' in dice_text.lower():
            try:
                parts = dice_text.lower().split('d')
                num_dice = int(parts[0]) if parts[0] else 1
                num_sides = int(parts[1])
            except (ValueError, IndexError):
                await message.reply("⚠️ Неверный формат! Используйте: `/dice 2d20`", parse_mode="Markdown")
                return
        else:
            # Просто число кубиков
            try:
                num_dice = int(dice_text)
            except ValueError:
                await message.reply("⚠️ Укажите корректное число кубиков!", parse_mode="Markdown")
                return

    # Ограничения
    if num_dice < 1 or num_dice > 10:
        await message.reply("⚠️ Можно бросить от 1 до 10 кубиков!")
        return

    if num_sides < 2 or num_sides > 100:
        await message.reply("⚠️ Кубик может иметь от 2 до 100 граней!")
        return

    # Бросаем кубики
    rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
    total = sum(rolls)

    # Формируем ответ
    dice_emoji = "🎲"
    response = f"{dice_emoji} *БРОСОК КУБИКОВ*\n\n"

    if num_dice == 1:
        response += f"Результат: **{rolls[0]}**"
    else:
        response += f"Кубики ({num_dice}d{num_sides}):\n"
        response += " + ".join([f"**{r}**" for r in rolls])
        response += f"\n\n= **{total}**"

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Dice rolled: {num_dice}d{num_sides} in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send dice roll: {e}")


@router.message(F.text.regexp(r"(?i)^(выбери|выбрать|что выбрать|помоги выбрать):?\s+.+"))
async def choice_text_trigger(message: Message) -> None:
    """
    Текстовый триггер для выбора.

    Примеры:
    - "выбери: пицца, суши, бургеры"
    - "что выбрать пойти гулять или остаться дома"
    """
    import re

    text = message.text
    # Удаляем триггерное слово и двоеточие
    clean_text = re.sub(r"(?i)^(выбери|выбрать|что выбрать|помоги выбрать):?\s*", "", text).strip()

    # Разбиваем варианты
    if ',' in clean_text:
        options = [opt.strip() for opt in clean_text.split(',') if opt.strip()]
    elif ' или ' in clean_text.lower():
        options = [opt.strip() for opt in clean_text.lower().split(' или ') if opt.strip()]
    else:
        # Пробуем разделить пробелами если нет других разделителей
        options = [opt.strip() for opt in clean_text.split() if opt.strip()]

    if len(options) < 2:
        await message.reply("⚠️ Не могу понять варианты. Перечисли их через запятую или слово 'или'")
        return

    # Случайный выбор
    chosen = random.choice(options)

    emojis = ["🎯", "✨", "🌟", "💫", "⭐", "🔮"]
    emoji = random.choice(emojis)

    response = f"{emoji} Я выбираю: **{chosen}**"

    try:
        await message.reply(response, parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.error(f"Failed to send choice: {e}")
