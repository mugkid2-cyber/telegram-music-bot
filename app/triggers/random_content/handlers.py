"""
Handler для генерации случайного контента (факты, цитаты, советы).
"""
import random
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)

router = Router(name="random_content")


# База интересных фактов
INTERESTING_FACTS = [
    "Медузы существуют более 500 миллионов лет, что делает их старше динозавров и акул",
    "Осьминоги имеют три сердца и голубую кровь",
    "Бананы - это ягоды, а клубника - нет",
    "Мед никогда не портится. Археологи находили горшки с медом в древнеегипетских гробницах возрастом 3000 лет",
    "Эйфелева башня может быть на 15 см выше летом из-за расширения металла от жары",
    "Коты спят 70% своей жизни",
    "Человек не может чихнуть с открытыми глазами",
    "Отпечатки языка у всех людей уникальны, как и отпечатки пальцев",
    "Крокодилы не могут высунуть язык",
    "Акулы существуют дольше, чем деревья",
    "Стрекозы могут летать в любом направлении, включая назад",
    "Самая маленькая кость в человеческом теле находится в среднем ухе",
    "Человеческий мозг генерирует около 70,000 мыслей в день",
    "Пингвины могут прыгать на высоту до 2 метров",
    "Совы не могут двигать глазами, поэтому поворачивают голову на 270 градусов",
]


MOTIVATIONAL_QUOTES = [
    "Не бойся медленно идти, бойся стоять на месте",
    "Единственный способ делать отличную работу - любить то, что ты делаешь",
    "Успех - это способность идти от неудачи к неудаче, не теряя энтузиазма",
    "Лучшее время посадить дерево было 20 лет назад. Второе лучшее время - сегодня",
    "Не ограничивай себя. Многие люди ограничивают себя тем, что они думают, что могут сделать",
    "Ты можешь быть разочарован, если потерпишь неудачу, но ты обречен, если не попытаешься",
    "Великие дела не делаются импульсивно, а складываются из множества мелких",
    "Начни с того места, где ты есть. Используй то, что у тебя есть. Делай то, что можешь",
    "Никогда не поздно стать тем, кем ты мог бы быть",
    "Сложно победить человека, который никогда не сдается",
]


LIFE_TIPS = [
    "💧 Выпивай стакан воды сразу после пробуждения - это запустит метаболизм",
    "🚶 Делай 10-минутную прогулку после каждого приема пищи для лучшего пищеварения",
    "📱 Убирай телефон за час до сна для качественного отдыха",
    "🧘 5 минут медитации утром помогут сохранить спокойствие весь день",
    "📝 Записывай 3 вещи, за которые благодарен каждый вечер",
    "🎯 Планируй завтра вечером, чтобы начать день продуктивно",
    "🏃 20 минут физической активности улучшают настроение на весь день",
    "📚 Читай хотя бы 10 страниц книги перед сном",
    "🥗 Начинай обед с овощей - так ты съешь их больше",
    "😴 Старайся ложиться спать в одно и то же время каждый день",
    "🎵 Слушай новую музыку раз в неделю - это развивает мозг",
    "🤝 Звони друзьям, а не пиши - голосовое общение укрепляет связи",
    "🌅 Просыпайся на 15 минут раньше для спокойного утра без спешки",
    "🧊 Принимай холодный душ 30 секунд - это бодрит и укрепляет иммунитет",
    "✍️ Веди дневник - это помогает разобраться в мыслях и эмоциях",
]


@router.message(Command("fact"))
async def random_fact_command(message: Message) -> None:
    """
    Команда для получения случайного интересного факта.

    Использование:
    /fact
    """
    fact = random.choice(INTERESTING_FACTS)

    response = f"💡 *Интересный факт:*\n\n_{fact}_"

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Random fact sent in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send fact: {e}")


@router.message(Command("motivation"))
async def motivation_command(message: Message) -> None:
    """
    Команда для получения мотивационной цитаты.

    Использование:
    /motivation
    """
    quote = random.choice(MOTIVATIONAL_QUOTES)

    response = f"✨ *Мотивация дня:*\n\n_{quote}_"

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Motivation sent in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send motivation: {e}")


@router.message(Command("tip"))
async def life_tip_command(message: Message) -> None:
    """
    Команда для получения полезного совета для жизни.

    Использование:
    /tip
    """
    tip = random.choice(LIFE_TIPS)

    response = f"💡 *Полезный совет:*\n\n{tip}"

    try:
        await message.reply(response, parse_mode="Markdown")
        logger.info(f"Life tip sent in chat {message.chat.id}")
    except TelegramAPIError as e:
        logger.error(f"Failed to send tip: {e}")


@router.message(F.text.regexp(r"(?i)^(расскажи факт|интересный факт|факт|дай факт)$"))
async def fact_text_trigger(message: Message) -> None:
    """
    Текстовый триггер для фактов.

    Примеры:
    - "расскажи факт"
    - "интересный факт"
    - "факт"
    """
    fact = random.choice(INTERESTING_FACTS)

    response = f"💡 *Интересный факт:*\n\n_{fact}_"

    try:
        await message.reply(response, parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.error(f"Failed to send fact: {e}")


@router.message(F.text.regexp(r"(?i)^(мотивация|мотивируй|вдохнови|цитата)$"))
async def motivation_text_trigger(message: Message) -> None:
    """
    Текстовый триггер для мотивации.

    Примеры:
    - "мотивация"
    - "мотивируй"
    - "вдохнови"
    """
    quote = random.choice(MOTIVATIONAL_QUOTES)

    response = f"✨ _{quote}_"

    try:
        await message.reply(response, parse_mode="Markdown")
    except TelegramAPIError as e:
        logger.error(f"Failed to send motivation: {e}")
