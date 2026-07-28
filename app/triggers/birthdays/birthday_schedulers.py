import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.config import get_settings
from app.triggers.birthdays.birthday_service import BirthdayRecord, BirthdayService
from app.triggers.birthdays.chat_members_service import ChatMembersService
from app.utils.html_escape import escape_html
from app.utils.mentions import build_invisible_mentions, chunk_html_message
from app.utils.scheduler_state import SchedulerStateService

logger = logging.getLogger(__name__)

# Поздравляем по московскому времени, а не по времени сервера — иначе
# при развёртывании не в MSK-таймзоне "сегодня" для бота и "сегодня"
# по Москве расходятся на несколько часов в сутки, и дни рождения
# либо пропускаются, либо считаются в неверный день.
#
# На Windows (и на некоторых минимальных Linux-образах) нет системной
# базы IANA tzdata, и ZoneInfo падает при импорте — правильное решение
# это установить пакет `pip install tzdata`, но на всякий случай не
# роняем бота целиком: Москва не переходит на летнее время, поэтому
# фиксированный UTC+3 — надёжный запасной вариант.
try:
    MSK = ZoneInfo("Europe/Moscow")
except ZoneInfoNotFoundError:
    logger.warning(
        "Пакет tzdata не установлен (pip install tzdata) — "
        "использую фиксированный UTC+3 вместо Europe/Moscow"
    )
    MSK = timezone(timedelta(hours=3), name="MSK")


def _years_word(age: int) -> str:
    """Русское склонение: 1 год, 2-4 года, 5-20/25.../0 лет."""
    last_two = age % 100
    last_one = age % 10
    if 11 <= last_two <= 14:
        return "лет"
    if last_one == 1:
        return "год"
    if 2 <= last_one <= 4:
        return "года"
    return "лет"


class BirthdayScheduler:
    def __init__(
        self,
        bot: Bot,
        birthday_service: BirthdayService,
        members_service: ChatMembersService,
    ) -> None:
        self._bot = bot
        self._birthdays = birthday_service
        self._members = members_service
        self._state = SchedulerStateService()
        self._task: asyncio.Task | None = None
        self._max_retries = 3
        self._retry_delay = 60  # seconds

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _run(self) -> None:
        # Check for missed executions during downtime
        await self._check_missed_birthdays()

        # Immediately check today's birthdays on startup
        try:
            await self._announce_todays_birthdays_with_retry()
        except Exception:
            logger.exception("Birthday scheduler catch-up run failed")

        while True:
            try:
                await self._sleep_until_next_run()
                await self._announce_todays_birthdays_with_retry()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Birthday scheduler iteration failed")
                await asyncio.sleep(self._retry_delay)

    async def _sleep_until_next_run(self) -> None:
        hour = get_settings().BIRTHDAY_ANNOUNCE_HOUR
        now = datetime.now(MSK)
        run_at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if run_at <= now:
            run_at += timedelta(days=1)
        await asyncio.sleep((run_at - now).total_seconds())

    async def _check_missed_birthdays(self) -> None:
        """Check if we missed any birthday announcements during downtime."""
        last_check = await self._state.get_last_birthday_check()
        if not last_check:
            logger.info("No previous birthday check recorded, skipping catch-up")
            return

        now = datetime.now(MSK)
        days_missed = (now.date() - last_check.date()).days

        if days_missed > 1:
            logger.warning(
                "Bot was down for %d days, may have missed birthday announcements",
                days_missed - 1
            )
            # Could implement catch-up logic here if needed

    async def _announce_todays_birthdays_with_retry(self) -> None:
        """Announce today's birthdays with retry logic."""
        for attempt in range(self._max_retries):
            try:
                await self._announce_todays_birthdays()
                # Record successful execution
                await self._state.set_last_birthday_check(datetime.now(MSK))
                return
            except Exception as e:
                if attempt < self._max_retries - 1:
                    logger.warning(
                        "Birthday announcement failed (attempt %d/%d): %s. Retrying in %ds...",
                        attempt + 1,
                        self._max_retries,
                        e,
                        self._retry_delay
                    )
                    await asyncio.sleep(self._retry_delay)
                else:
                    logger.exception("Birthday announcement failed after %d attempts", self._max_retries)
                    raise

    async def _announce_todays_birthdays(self) -> None:
        # Открепляем вчерашние поздравления в самом начале нового дня
        # по МСК — так закреплённое сообщение "живёт" ровно до конца
        # дня, в который его отправили.
        await self._unpin_previous_day_messages()

        today = datetime.now(MSK)
        records = await self._birthdays.get_todays_birthdays(today.day, today.month, today.year)
        for record in records:
            try:
                await self._announce_one(record, today.year)
            except Exception:
                logger.exception(
                    "Failed to announce birthday chat=%s username=%s",
                    record.chat_id,
                    record.username,
                )

    async def _unpin_previous_day_messages(self) -> None:
        today_str = datetime.now(MSK).date().isoformat()
        for record_id, chat_id, message_id, pinned_date in await self._birthdays.get_pinned_messages():
            if pinned_date == today_str:
                # Закреплено сегодня же (например, бота перезапустили в
                # тот же день) — рано открепять, оставляем до завтра.
                continue
            try:
                await self._bot.unpin_chat_message(chat_id=chat_id, message_id=message_id)
            except TelegramAPIError:
                # Сообщение могли открепить/удалить вручную — это не ошибка,
                # просто снимаем отметку в БД и идём дальше.
                logger.info(
                    "Could not unpin birthday message chat=%s message=%s (already gone?)",
                    chat_id,
                    message_id,
                )
            finally:
                await self._birthdays.set_pinned_message(record_id, None)

    async def announce_if_due(self, record: BirthdayRecord) -> None:
        """Вызывается сразу после добавления/обновления записи через /bday.
        Если день рождения — сегодня по МСК и в этом году ещё не
        поздравляли, поздравляет немедленно, не дожидаясь ночного
        прогона планировщика."""
        today = datetime.now(MSK)
        if record.birth_day != today.day or record.birth_month != today.month:
            return
        if record.last_greeted_year == today.year:
            return
        try:
            await self._announce_one(record, today.year)
        except Exception:
            logger.exception(
                "Failed to send immediate birthday greeting chat=%s username=%s",
                record.chat_id,
                record.username,
            )

    async def _announce_one(self, record: BirthdayRecord, current_year: int) -> None:
        age = current_year - record.birth_year
        if record.user_id:
            who = f'<a href="tg://user?id={record.user_id}">{escape_html(record.display_name)}</a>'
        else:
            who = f"{escape_html(record.display_name)} (@{escape_html(record.username)})"

        text = (
            f"🎉{who} отмечает день рождения! "
            f"{age} {_years_word(age)}.\n"
            f"Поздравляем! 🎂"
        )

        members = await self._members.get_members(record.chat_id, exclude_user_id=record.user_id)
        mention_fragments = build_invisible_mentions([member.user_id for member in members])

        chunks = chunk_html_message(text, mention_fragments)
        sent_first_message_id: int | None = None
        for chunk in chunks:
            try:
                sent = await self._bot.send_message(chat_id=record.chat_id, text=chunk)
                if sent_first_message_id is None:
                    sent_first_message_id = sent.message_id
            except TelegramAPIError:
                logger.exception("Failed to send birthday message to chat %s", record.chat_id)
                break

        await self._birthdays.mark_greeted(record.id, current_year)

        if sent_first_message_id is not None:
            try:
                await self._bot.pin_chat_message(
                    chat_id=record.chat_id,
                    message_id=sent_first_message_id,
                    disable_notification=True,
                )
            except TelegramAPIError:
                # Например, у бота нет прав "закреплять сообщения" в этом
                # чате — само поздравление уже отправлено, это не критично.
                logger.exception("Failed to pin birthday message chat=%s", record.chat_id)
            else:
                today_str = datetime.now(MSK).date().isoformat()
                await self._birthdays.set_pinned_message(record.id, sent_first_message_id, today_str)