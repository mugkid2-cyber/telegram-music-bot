import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Dispatcher
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.database.db import init_db
from app.triggers.birthdays.birthday_handlers import router as birthday_router
from app.triggers.birthdays.birthday_schedulers import BirthdayScheduler
from app.triggers.birthdays.birthday_service import BirthdayService
from app.triggers.birthdays.chat_member_tracking_middleware import ChatMemberTrackingMiddleware
from app.triggers.birthdays.chat_members_service import ChatMembersService
from app.triggers.shazam import router as shazam_router
# Отключённые модули для оптимизации деплоя на Render
# from app.triggers import router as triggers_router
# from app.triggers.nervy import get_nervy_trigger
# from app.triggers.message_cleaner import router as message_cleaner_router
# from app.triggers.decision_maker import router as decision_maker_router
# from app.triggers.random_content import router as random_content_router
# from app.triggers.reminders import router as reminders_router
# from app.triggers.password_generator import router as password_generator_router
# from app.triggers.text_tools import router as text_tools_router
# from app.triggers.user_info import router as user_info_router
# from app.triggers.converter import router as converter_router
# from app.triggers.polls import router as polls_router
# from app.triggers.qr_links import router as qr_links_router
from app.media.audio.handlers.music import router as music_router, _periodic_cleanup_search_state
from app.media.audio.handlers.start import router as start_router
from app.media.audio.favorites import router as favorites_router
from app.media.audio.favorites.db import FavoritesDB
from app.icons import QuoteLoggingMiddleware, quotes_router, setup_quote_scheduler
from app.icons.db import init_quotes_db
from app.utils.logger import setup_logging
from app.utils.telegram import create_bot, verify_telegram_connection
from app.utils.cache_manager import CacheManager
from app.utils.health_check import start_health_server, stop_health_server
from app.media.video.router import router as video_router, start_background_tasks
# from app.core.metrics import start_metrics_server, stop_metrics_server  # Временно отключено
from app.core.logging_config import setup_structured_logging
from app.core.backup import DatabaseBackup

logger = logging.getLogger(__name__)


async def main() -> None:
    # Настраиваем structured logging
    setup_structured_logging(level="INFO", log_file=Path("app/logs/bot.log"))

    settings = get_settings()

    settings.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    await init_db()
    await init_quotes_db()

    # Инициализация БД избранного
    favorites_db = FavoritesDB()
    await favorites_db.init()

    bot = create_bot(settings)
    dp = Dispatcher()

    # Единственные инстансы на всё приложение — их же передадим
    # хендлерам, middleware и планировщику, чтобы все работали
    # через одну и ту же точку доступа к БД, а не через несколько
    # независимых объектов.
    members_service = ChatMembersService()
    birthday_service = BirthdayService()
    scheduler = BirthdayScheduler(
        bot=bot,
        birthday_service=birthday_service,
        members_service=members_service,
    )
    quotes_scheduler = AsyncIOScheduler()
    setup_quote_scheduler(quotes_scheduler, bot)

    # Cache manager for automatic cleanup
    cache_manager = CacheManager(
        cache_dir=settings.DOWNLOAD_DIR / "cache",
        max_size_mb=500,
        check_interval_hours=6,
    )

    # Database backup
    backup_service = DatabaseBackup(
        db_path=settings.DATABASE_PATH,
        backup_dir=Path("app/backups"),
        interval_hours=24,
        keep_backups=7
    )

    # Initialize Nervy trigger (DISABLED)
    # nervy_trigger = get_nervy_trigger()
    # await nervy_trigger.initialize()

    # dp["..."] = ... кладёт объект в workflow_data — aiogram сам
    # подставит его в любой хендлер, у которого есть параметр
    # с таким же именем (см. birthday_service: BirthdayService и
    # birthday_scheduler: BirthdayScheduler в хендлерах).
    dp["birthday_service"] = birthday_service
    dp["members_service"] = members_service
    dp["birthday_scheduler"] = scheduler

    dp.message.middleware(ChatMemberTrackingMiddleware(members_service))
    dp.message.outer_middleware(QuoteLoggingMiddleware())

    dp.include_router(music_router)
    dp.include_router(start_router)
    dp.include_router(favorites_router)
    dp.include_router(birthday_router)
    dp.include_router(quotes_router)
    dp.include_router(video_router)
    dp.include_router(shazam_router)
    # Отключённые роутеры для оптимизации
    # dp.include_router(message_cleaner_router)  # Очистка сообщений
    # dp.include_router(decision_maker_router)  # Помощь в принятии решений
    # dp.include_router(random_content_router)  # Случайный контент
    # dp.include_router(reminders_router)  # Напоминания и таймеры
    # dp.include_router(password_generator_router)  # Генерация паролей
    # dp.include_router(text_tools_router)  # Работа с текстом
    # dp.include_router(user_info_router)  # Информация о пользователях
    # dp.include_router(converter_router)  # Конвертер единиц
    # dp.include_router(polls_router)  # Опросы и голосования
    # dp.include_router(qr_links_router)  # QR-коды и ссылки
    # dp.include_router(triggers_router)  # Триггеры: имена, калькулятор, переводчик
    @dp.startup()
    async def on_startup():
        await start_background_tasks()
        
    try:
        await verify_telegram_connection(
            bot,
            retries=settings.TELEGRAM_CONNECT_RETRIES,
            delay=settings.TELEGRAM_CONNECT_RETRY_DELAY,
        )
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Главное меню"),
                BotCommand(command="fav", description="Избранные треки"),
                BotCommand(command="bdl", description="Список дней рождения в чате"),
                BotCommand(command="qt", description="Создать цитату"),
                # Отключённые команды
                # BotCommand(command="cms", description="Очистить сообщения"),
                # BotCommand(command="choice", description="Помощь в выборе"),
                # BotCommand(command="fact", description="Интересный факт"),
                # BotCommand(command="remind", description="Напоминание"),
                # BotCommand(command="genpass", description="Сгенерировать пароль"),
                # BotCommand(command="count", description="Статистика текста"),
                # BotCommand(command="id", description="Получить ID"),
                # BotCommand(command="convert", description="Конвертер единиц"),
                # BotCommand(command="poll", description="Создать опрос"),
                # BotCommand(command="qr", description="Создать QR-код"),
            ]
        )
    except TelegramNetworkError:
        await bot.session.close()
        raise SystemExit(1) from None

    scheduler.start()
    quotes_scheduler.start()
    cache_manager.start()
    backup_service.start()

    # Запускаем периодическую очистку поисковых состояний
    asyncio.create_task(_periodic_cleanup_search_state())

    # Start health check server
    health_server = await start_health_server(host="0.0.0.0", port=8080)

    # Start metrics server (temporarily disabled due to dependency issues)
    # metrics_server = await start_metrics_server(host="0.0.0.0", port=9090)

    logger.info("Бот запущен и готов к работе")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.stop()
        quotes_scheduler.shutdown()
        cache_manager.stop()
        backup_service.stop()
        await stop_health_server()
        # await stop_metrics_server(metrics_server)  # Temporarily disabled
        await bot.session.close()


if __name__ == "__main__":
    if str(Path(__file__).resolve().parent.parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")