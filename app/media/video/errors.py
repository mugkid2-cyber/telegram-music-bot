"""Специфичные для модуля исключения — чтобы хендлеры могли давать
пользователю понятный ответ вместо голого traceback."""


class DownloaderError(Exception):
    """Базовая ошибка модуля скачивания видео."""


class UnsupportedURLError(DownloaderError):
    """Ссылка не относится ни к одной из поддерживаемых платформ."""


class VideoUnavailableError(DownloaderError):
    """Видео приватное, удалено, гео-заблокировано и т.п."""


class LoginRequiredError(DownloaderError):
    """Платформа требует авторизации — нужны или протухли cookies."""


class FileTooLargeError(DownloaderError):
    """Даже в минимальном доступном качестве файл больше лимита Telegram."""

    def __init__(self, size_bytes: int, limit_bytes: int):
        self.size_bytes = size_bytes
        self.limit_bytes = limit_bytes
        super().__init__(f"file size {size_bytes} exceeds limit {limit_bytes}")


class DownloadTimeoutError(DownloaderError):
    """Платформа не ответила вовремя (таймаут сети)."""
