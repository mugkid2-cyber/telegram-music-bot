"""Structured logging configuration with beautiful colored output."""
import logging
import sys
from pathlib import Path
from datetime import datetime


# ANSI Color codes
class Colors:
    """ANSI escape codes for colors."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # Bright foreground
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'

    # Background colors
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'


# Level icons and colors
LEVEL_CONFIG = {
    'DEBUG': {
        'icon': '🔍',
        'color': Colors.BRIGHT_BLACK,
        'name_color': Colors.DIM + Colors.WHITE,
    },
    'INFO': {
        'icon': '✨',
        'color': Colors.BRIGHT_CYAN,
        'name_color': Colors.CYAN,
    },
    'WARNING': {
        'icon': '⚠️',
        'color': Colors.BRIGHT_YELLOW,
        'name_color': Colors.YELLOW,
    },
    'ERROR': {
        'icon': '❌',
        'color': Colors.BRIGHT_RED,
        'name_color': Colors.RED,
    },
    'CRITICAL': {
        'icon': '🔥',
        'color': Colors.BG_RED + Colors.BRIGHT_WHITE + Colors.BOLD,
        'name_color': Colors.BG_RED + Colors.BRIGHT_WHITE,
    },
}


class BeautifulFormatter(logging.Formatter):
    """Beautiful colored formatter with icons and structure."""

    def __init__(self, use_colors=True):
        super().__init__()
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        """Форматирует лог-запись красиво."""
        # Фильтруем aiogram ошибки конфликтов
        if 'aiogram' in record.name and 'Conflict' in record.getMessage():
            return ""  # Пропускаем эти логи

        # Получаем конфиг для уровня
        level_config = LEVEL_CONFIG.get(record.levelname, LEVEL_CONFIG['INFO'])

        if self.use_colors:
            # Временная метка (серая)
            timestamp = f"{Colors.BRIGHT_BLACK}{datetime.now().strftime('%H:%M:%S')}{Colors.RESET}"

            # Уровень с иконкой и цветом
            level_icon = level_config['icon']
            level_color = level_config['color']
            level_text = f"{level_icon}"

            # Имя логгера (укороченное)
            name_parts = record.name.split('.')
            short_name = name_parts[-1] if len(name_parts) > 1 else record.name
            name_color = level_config['name_color']
            logger_name = f"{name_color}{short_name:15s}{Colors.RESET}"

            # Сообщение (жирное для важных уровней)
            message = record.getMessage()
            if record.levelno >= logging.WARNING:
                message = f"{Colors.BOLD}{message}{Colors.RESET}"

            # Собираем строку (без location)
            parts = [timestamp, level_icon, logger_name, message]
            result = " ".join(parts)

            # Добавляем extra данные если есть (упрощённо)
            if hasattr(record, "extra_data") and record.extra_data:
                extra_parts = []
                for k, v in record.extra_data.items():
                    extra_parts.append(f"{k}={v}")
                if extra_parts:
                    result += f" {Colors.DIM}({', '.join(extra_parts)}){Colors.RESET}"

            # Exception info
            if record.exc_info:
                result += f"\n{Colors.BRIGHT_RED}{self.formatException(record.exc_info)}{Colors.RESET}"

        else:
            # Без цветов (для файла)
            timestamp = datetime.utcnow().strftime('%H:%M:%S.%f')[:-3]
            level_text = f"{record.levelname:8s}"
            logger_name = f"{record.name:30s}"
            message = record.getMessage()
            location = f"[{record.filename}:{record.lineno}]"

            parts = [timestamp, level_text, logger_name, message, location]
            result = " ".join(parts)

            if hasattr(record, "extra_data") and record.extra_data:
                extra_str = " ".join(f"{k}={v}" for k, v in record.extra_data.items())
                result += f" | {extra_str}"

            if record.exc_info:
                result += f"\n{self.formatException(record.exc_info)}"

        return result


def setup_structured_logging(level: str = "INFO", log_file: Path | None = None):
    """
    Настраивает beautiful structured logging.

    Args:
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
        log_file: Путь к файлу для логов (опционально)
    """
    # Console handler с цветами
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(BeautifulFormatter(use_colors=True))

    # File handler без цветов
    handlers = [console_handler]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(BeautifulFormatter(use_colors=False))
        handlers.append(file_handler)

    # Настраиваем root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Удаляем старые handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Добавляем новые
    for handler in handlers:
        root_logger.addHandler(handler)

    # Уменьшаем verbose внешних библиотек
    logging.getLogger("aiogram").setLevel(logging.CRITICAL)  # Скрываем все ошибки aiogram
    logging.getLogger("aiogram.dispatcher").setLevel(logging.CRITICAL)
    logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    logging.getLogger("yt_dlp").setLevel(logging.ERROR)
    logging.getLogger("apscheduler").setLevel(logging.ERROR)

    root_logger.info(
        "Логирование запущено",
        extra={"extra_data": {"level": level}}
    )


class LoggerAdapter(logging.LoggerAdapter):
    """Adapter для добавления контекста в логи."""

    def process(self, msg, kwargs):
        """Добавляет extra_data в kwargs."""
        if "extra" not in kwargs:
            kwargs["extra"] = {}
        if "extra_data" not in kwargs["extra"]:
            kwargs["extra"]["extra_data"] = {}
        kwargs["extra"]["extra_data"].update(self.extra)
        return msg, kwargs


def get_logger(name: str, **context) -> LoggerAdapter:
    """
    Получает logger с контекстом.

    Args:
        name: Имя logger'а
        **context: Дополнительный контекст для всех сообщений

    Example:
        logger = get_logger(__name__, user_id=123, chat_id=456)
        logger.info("Track downloaded", track_id="abc", platform="yt")
    """
    return LoggerAdapter(logging.getLogger(name), context)

