import re

from aiogram.filters import BaseFilter
from aiogram.types import Message

COMMAND_PREFIX = "мп3"
_PREFIX_LEN = len(COMMAND_PREFIX)
_MENTION_PREFIX = re.compile(r"^@\w+\s+", re.UNICODE)


def parse_music_command(text: str) -> str | None:
    """
    Разбор текстовой команды «мп3 …».

    None  — не команда
    ''    — команда без запроса (только «мп3»)
    str   — поисковый запрос
    """
    cleaned = _MENTION_PREFIX.sub("", text.strip())
    if not cleaned:
        return None

    folded = cleaned.casefold()
    prefix = COMMAND_PREFIX.casefold()

    if not folded.startswith(prefix):
        return None

    if len(folded) == _PREFIX_LEN:
        return ""

    if folded[_PREFIX_LEN] != " ":
        return None

    query = cleaned[_PREFIX_LEN:].strip()
    return query


class MusicCommandFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if not message.text:
            return False
        return parse_music_command(message.text) is not None
