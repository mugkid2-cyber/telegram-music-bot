import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent

# .env лежит не в папке приложения, а рядом с проектом (в PROJECT_ROOT).
# Если у вас он в другом месте — не обязательно трогать код, достаточно
# перед запуском задать переменную окружения ENV_FILE с полным путём,
# например: ENV_FILE=/etc/music_bot/.env python -m app
ENV_FILE_PATH = Path(os.environ.get("ENV_FILE", PROJECT_ROOT / ".env")).expanduser()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    BOT_TOKEN: str
    BOT_PROXY: str | None = None
    TELEGRAM_REQUEST_TIMEOUT: int = 60
    TELEGRAM_CONNECT_RETRIES: int = 5
    TELEGRAM_CONNECT_RETRY_DELAY: float = 3.0
    DOWNLOAD_DIR: Path = APP_DIR / "media" / "audio" / "cache"
    FFMPEG_PATH: str | None = None
    DATABASE_PATH: Path = APP_DIR / "data" / "bot.db"

    MAX_DURATION_SECONDS: int = 20 * 60
    SEARCH_RESULTS_LIMIT: int = 6  # Топ-6 самых релевантных
    SEARCH_PER_PLATFORM: int = 4  # По 4 с каждой платформы для выбора лучших
    MP3_BITRATE: str = "192"

    BIRTHDAY_ANNOUNCE_HOUR: int = 10

    @field_validator("BOT_TOKEN")
    @classmethod
    def validate_bot_token(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(
                "BOT_TOKEN не задан. Проверьте, что переменная есть в .env "
                f"({ENV_FILE_PATH}) или в окружении процесса."
            )
        return value

    @field_validator("DOWNLOAD_DIR", "DATABASE_PATH", mode="before")
    @classmethod
    def resolve_path(cls, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    @field_validator(
        "MAX_DURATION_SECONDS",
        "TELEGRAM_REQUEST_TIMEOUT",
        "TELEGRAM_CONNECT_RETRIES",
        "TELEGRAM_CONNECT_RETRY_DELAY",
        "SEARCH_RESULTS_LIMIT",
        "SEARCH_PER_PLATFORM",
    )
    @classmethod
    def validate_positive(cls, value: int | float, info) -> int | float:
        if value <= 0:
            raise ValueError(f"{info.field_name} должно быть больше нуля, получено {value}")
        return value

    @field_validator("MP3_BITRATE")
    @classmethod
    def validate_bitrate(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit():
            raise ValueError(f"MP3_BITRATE должен быть числом (например, '192'), получено {value!r}")
        return value

    @field_validator("BIRTHDAY_ANNOUNCE_HOUR")
    @classmethod
    def validate_announce_hour(cls, value: int) -> int:
        if not (0 <= value <= 23):
            raise ValueError(f"BIRTHDAY_ANNOUNCE_HOUR должен быть от 0 до 23, получено {value}")
        return value

    @model_validator(mode="after")
    def ensure_directories_exist(self) -> "Settings":
        self.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        return self

    @model_validator(mode="after")
    def validate_search_limits(self) -> "Settings":
        if self.SEARCH_PER_PLATFORM > self.SEARCH_RESULTS_LIMIT:
            raise ValueError(
                "SEARCH_PER_PLATFORM "
                f"({self.SEARCH_PER_PLATFORM}) не может быть больше "
                f"SEARCH_RESULTS_LIMIT ({self.SEARCH_RESULTS_LIMIT})"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()