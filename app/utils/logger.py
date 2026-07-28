import logging
import sys
import io


class ColoredFormatter(logging.Formatter):
    """Цветной форматтер с эмодзи для красивых логов"""

    # Цвета для Windows Terminal
    COLORS = {
        "DEBUG": "\033[36m",      # Cyan
        "INFO": "\033[32m",       # Green
        "WARNING": "\033[33m",    # Yellow
        "ERROR": "\033[31m",      # Red
        "CRITICAL": "\033[35m",   # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Эмодзи для уровней
    EMOJI = {
        "DEBUG": "🔍",
        "INFO": "✅",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "CRITICAL": "🔥",
    }

    # Короткие русские названия модулей
    MODULE_NAMES = {
        "app.database.db": "База",
        "quotes.db": "Цитаты",
        "apscheduler.scheduler": "Планировщик",
        "utils.telegram": "Telegram",
        "__main__": "Бот",
        "video_downloader.router": "TikTok",
        "media.audio.handlers.music": "Музыка",
        "media.audio.services.download_service": "Загрузка",
        "bday.birthday_schedulers": "Дни рождения",
        "aiogram": "Aiogram",
        "yt_dlp": "yt-dlp",
    }

    def format(self, record):
        # Уровень с цветом и эмодзи
        level = record.levelname
        emoji = self.EMOJI.get(level, "•")
        color = self.COLORS.get(level, "")

        # Короткое имя модуля
        module_name = self.MODULE_NAMES.get(record.name, record.name.split(".")[-1])

        # Время без даты (только время)
        time_str = self.formatTime(record, "%H:%M:%S")

        # Формируем сообщение
        if level == "INFO":
            # INFO: только эмодзи и сообщение, без времени и модуля (максимально чисто)
            return f"{emoji} {record.getMessage()}"
        elif level in ("WARNING", "ERROR", "CRITICAL"):
            # Ошибки: с временем и модулем
            return f"{color}{emoji} [{time_str}] {module_name}: {record.getMessage()}{self.RESET}"
        else:
            # DEBUG: подробно
            return f"{self.DIM}{emoji} [{time_str}] {module_name}: {record.getMessage()}{self.RESET}"


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    # Настройка UTF-8 для Windows консоли
    if sys.platform == "win32":
        # Перенаправляем stdout в UTF-8 обертку
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter())

    root.setLevel(level)
    root.addHandler(handler)

    # Приглушаем шумные библиотеки
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("yt_dlp").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
