"""
Модуль фан-команд: триггеры на имена и слова с отправкой медиа.
"""
import re
from pathlib import Path
from typing import Optional

# Путь к медиа файлам
MEDIA_DIR = Path(__file__).parent / "media"

# Карта триггеров: паттерн -> файл
TRIGGERS = {
    "ivan": {
        "patterns": [
            r"\bиван\b",           # Кириллица
            r"\bivan\b",           # Латиница
            r"\bивана\b",          # Склонения
            r"\bивану\b",
            r"\bиваном\b",
            r"\bиване\b",
            r"\bивань\b",          # Уменьшительные
            r"\bваня\b",
            r"\bвань\b",
            r"\bванечка\b",
            r"\bванюша\b",
        ],
        "file": "ivan.mp4",
        "type": "video",
        "source": "local",
    },
}


def normalize_text(text: str) -> str:
    """Нормализует текст для проверки"""
    return text.lower().strip()


def check_trigger(text: str) -> Optional[dict]:
    """
    Проверяет, содержит ли текст триггер.
    Возвращает информацию о триггере или None.
    """
    if not text:
        return None

    normalized = normalize_text(text)

    for trigger_name, trigger_data in TRIGGERS.items():
        for pattern in trigger_data["patterns"]:
            if re.search(pattern, normalized, re.IGNORECASE | re.UNICODE):
                media_path = MEDIA_DIR / trigger_data["file"]
                if media_path.exists():
                    return {
                        "name": trigger_name,
                        "file": str(media_path),
                        "type": trigger_data["type"],
                        "source": "local",
                    }

    return None


def get_all_triggers() -> dict:
    """Возвращает все доступные триггеры"""
    return TRIGGERS
