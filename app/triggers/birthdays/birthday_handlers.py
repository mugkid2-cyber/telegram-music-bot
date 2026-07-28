import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, MessageEntityType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.triggers.birthdays.birthday_schedulers import BirthdayScheduler
from app.triggers.birthdays.birthday_service import BirthdayPermissionError, BirthdayService
from app.utils.html_escape import escape_html

# Та же таймзона (и тот же запасной вариант на случай отсутствия
# пакета tzdata), что и в планировщике — см. birthday_schedulers.py.
try:
    MSK = ZoneInfo("Europe/Moscow")
except ZoneInfoNotFoundError:
    MSK = timezone(timedelta(hours=3), name="MSK")

router = Router(name="birthday")

USERNAME_RE = re.compile(r"@(\w{4,32})")
DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{2})\b")

USAGE_TEXT = (
    "Использование: <code>/bday Имя @юзер дд.мм.гг</code>\n"
    "Например: <code>/bday Александр @alex_ivanov 15.07.98</code>\n\n"
    "Если у человека нет username — ответьте (reply) этой командой на "
    "его сообщение: <code>/bday Имя дд.мм.гг</code>. Либо начните "
    "печатать «@» и выберите его из подсказки Telegram — тогда вставится "
    "упоминание по имени, без @."
)

GROUP_CHAT_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}


def _resolve_birth_year(two_digit_year: int) -> int:
    """дд.мм.гг — год из двух цифр, век определяем эвристикой: если YY не
    больше текущих двух цифр года, считаем 2000-е, иначе 1900-е.
    Не идеально для редких краевых случаев, но покрывает подавляющее
    большинство реальных дат рождения ныне живущих людей."""
    current_two_digit = datetime.now().year % 100
    century = 2000 if two_digit_year <= current_two_digit else 1900
    return century + two_digit_year


def _extract_text_mention(message: Message, raw_args: str) -> tuple[int, str] | None:
    """Ищет entity text_mention в пределах текста аргументов команды —
    это упоминание без @, которое Telegram вставляет, когда после ввода
    "@" выбирают человека из подсказки, а у того нет username (или он
    скрыл его в настройках приватности): в тексте остаётся только имя,
    а user_id приходит отдельно вместе с самой entity.
    Возвращает (user_id, показанный текст упоминания) или None.

    offset/length у entity — в UTF-16 code units (так требует Bot API),
    поэтому вместо среза по индексу Python-строки текст извлекается через
    кодирование в UTF-16. args_start ищем как обычный python-индекс: это
    безопасно, так как префикс команды ("/bday" или "/bday@botname ")
    состоит только из ASCII-символов, для которых оба вида индексации
    совпадают.
    """
    if not message.entities or not message.text or not raw_args:
        return None

    args_start = message.text.rfind(raw_args)
    if args_start == -1:
        return None

    encoded_text = message.text.encode("utf-16-le")
    for entity in message.entities:
        if entity.type != MessageEntityType.TEXT_MENTION or entity.user is None:
            continue
        if entity.offset < args_start:
            continue
        start = entity.offset * 2
        end = start + entity.length * 2
        mention_text = encoded_text[start:end].decode("utf-16-le")
        return entity.user.id, mention_text

    return None


def _parse_bday_args(
    message: Message, raw_args: str
) -> tuple[str, str | None, int | None, int, int, int] | None:
    """Разбирает аргументы /bday. Возвращает (имя, username|None,
    user_id|None, день, месяц, год рождения) или None, если разобрать не
    удалось.

    Кого поздравлять, можно указать тремя способами (в таком порядке
    приоритета, если в сообщении подходит сразу несколько):
      1. @username в тексте команды;
      2. упоминание без @ из подсказки Telegram (для людей без username);
      3. reply на сообщение именинника — когда явного упоминания в
         тексте нет вовсе.
    """
    date_match = DATE_RE.search(raw_args)
    if not date_match:
        return None

    day, month, year_short = (int(part) for part in date_match.groups())
    birth_year = _resolve_birth_year(year_short)
    try:
        datetime(birth_year, month, day)  # проверка, что дата реально существует
    except ValueError:
        return None

    remaining = raw_args[: date_match.start()] + raw_args[date_match.end():]

    username_match = USERNAME_RE.search(remaining)
    if username_match:
        name = remaining[: username_match.start()] + remaining[username_match.end():]
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            return None
        return name, username_match.group(1), None, day, month, birth_year

    text_mention = _extract_text_mention(message, raw_args)
    if text_mention:
        mention_user_id, mention_text = text_mention
        # Обычно упоминание из подсказки — это и есть весь "адресат" в
        # аргументах, отдельного имени рядом не печатают. Но если
        # что-то ещё осталось (человек дописал своё имя), используем его
        # как явно заданное отображаемое имя.
        name = remaining.replace(mention_text, "", 1)
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            name = mention_text
        return name, None, mention_user_id, day, month, birth_year

    reply = message.reply_to_message
    if reply is not None and reply.from_user is not None and not reply.from_user.is_bot:
        name = re.sub(r"\s+", " ", remaining).strip()
        if not name:
            name = reply.from_user.full_name
        return name, None, reply.from_user.id, day, month, birth_year

    return None


async def _is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramAPIError:
        return False
    return member.status in {"administrator", "creator"}


@router.message(Command("bday"), F.chat.type.in_(GROUP_CHAT_TYPES))
async def handle_bday_add(
    message: Message,
    command: CommandObject,
    bot: Bot,
    birthday_service: BirthdayService,
    birthday_scheduler: BirthdayScheduler,
) -> None:
    if message.from_user is None:
        return

    raw_args = (command.args or "").strip()
    if not raw_args:
        await message.reply(USAGE_TEXT)
        return

    parsed = _parse_bday_args(message, raw_args)
    if parsed is None:
        await message.reply("❌ Не удалось разобрать команду.\n" + USAGE_TEXT)
        return

    name, username, mention_user_id, day, month, birth_year = parsed

    age_now = datetime.now(MSK).year - birth_year
    if not (0 <= age_now <= 119):
        await message.reply("❌ Похоже, дата рождения указана неверно.")
        return

    user_id: int | None = mention_user_id
    if username is not None:
        try:
            chat = await bot.get_chat(f"@{username}")
            user_id = chat.id
        except TelegramAPIError:
            # Не критично — просто не сможем сделать кликабельное упоминание
            # по user_id, останется обычный @username.
            user_id = None

    is_admin = await _is_chat_admin(bot, message.chat.id, message.from_user.id)

    try:
        record = await birthday_service.add_or_update(
            chat_id=message.chat.id,
            username=username,
            display_name=name,
            birth_day=day,
            birth_month=month,
            birth_year=birth_year,
            added_by_user_id=message.from_user.id,
            user_id=user_id,
            requester_is_admin=is_admin,
        )
    except BirthdayPermissionError:
        await message.reply(
            "❌ Эта запись уже добавлена другим участником. "
            "Изменить её может только тот, кто добавил, или админ чата."
        )
        return

    username_part = f" (@{escape_html(username)})" if username else ""
    await message.reply(
        f"✅ Запомнил: <b>{escape_html(name)}</b>{username_part} — "
        f"{day:02d}.{month:02d}.{birth_year}."
    )

    # Если сегодня как раз день рождения — поздравляем сразу, не дожидаясь
    # ночного прогона планировщика (например, добавили запись уже после
    # полуночи по МСК, когда сегодняшнее поздравление ещё не отправляли).
    await birthday_scheduler.announce_if_due(record)


@router.message(Command("bday_del"), F.chat.type.in_(GROUP_CHAT_TYPES))
async def handle_bday_delete(
    message: Message, command: CommandObject, bot: Bot, birthday_service: BirthdayService
) -> None:
    if message.from_user is None:
        return

    raw_args = (command.args or "").strip()

    username: str | None = None
    user_id: int | None = None

    username_match = USERNAME_RE.search(raw_args)
    if username_match:
        username = username_match.group(1)
    else:
        text_mention = _extract_text_mention(message, raw_args)
        if text_mention:
            user_id = text_mention[0]
        elif message.reply_to_message is not None and message.reply_to_message.from_user is not None:
            user_id = message.reply_to_message.from_user.id

    if username is None and user_id is None:
        await message.reply(
            "Использование: <code>/bday_del @юзер</code>\n"
            "Либо ответьте (reply) этой командой на сообщение именинника, "
            "либо упомяните его через подсказку Telegram, если у него нет "
            "username."
        )
        return

    is_admin = await _is_chat_admin(bot, message.chat.id, message.from_user.id)

    try:
        deleted = await birthday_service.delete(
            chat_id=message.chat.id,
            username=username,
            user_id=user_id,
            requester_user_id=message.from_user.id,
            requester_is_admin=is_admin,
        )
    except BirthdayPermissionError:
        await message.reply("❌ Удалить может только тот, кто добавил запись, или админ чата.")
        return

    if deleted:
        await message.reply("🗑 Запись удалена.")
    else:
        await message.reply("Такой записи не найдено.")


@router.message(Command("bdl"), F.chat.type.in_(GROUP_CHAT_TYPES))
async def handle_bday_list(message: Message, birthday_service: BirthdayService) -> None:
    records = await birthday_service.list_for_chat(message.chat.id)
    if not records:
        await message.reply("В этом чате пока никто не добавил дату рождения.")
        return

    today = datetime.now(MSK).date()

    def days_until(record) -> int:
        try:
            next_date = today.replace(month=record.birth_month, day=record.birth_day)
        except ValueError:
            # 29 февраля в невисокосный год — переносим на 1 марта
            next_date = today.replace(month=3, day=1)
        if next_date < today:
            next_date = next_date.replace(year=today.year + 1)
        return (next_date - today).days

    records_sorted = sorted(records, key=days_until)

    lines = ["🎂 Дни рождения в этом чате:"]
    for record in records_sorted:
        who = escape_html(record.display_name)
        if record.username:
            who += f" (@{escape_html(record.username)})"
        lines.append(f"{record.birth_day:02d}.{record.birth_month:02d} — {who}")

    await message.reply("\n".join(lines))