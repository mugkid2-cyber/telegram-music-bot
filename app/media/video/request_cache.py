"""
Callback_data в Telegram ограничен 64 байтами, так что полную ссылку
(и тем более всё остальное — chat_id, message_id, платформу) в кнопку
не засунуть. Поэтому храним контекст запроса в памяти процесса под
коротким req_id, который и кладём в callback_data.

Почему не FSMContext: FSM привязан к паре (chat_id, user_id) и плохо
подходит, если пользователь кинет подряд несколько ссылок — второй
запрос затрёт состояние первого. Отдельный кэш с TTL и своим id решает
это чище.

Если бот работает в нескольких процессах/на нескольких инстансах —
этот кэш нужно заменить на Redis (интерфейс put/get/pop оставить тем же).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from app.media.video import config
from .platforms import Platform


@dataclass
class DownloadRequest:
    url: str
    platform: Platform
    chat_id: int
    message_id: int  # id исходного сообщения со ссылкой — чтобы ответить на него
    user_id: int
    created_at: float = field(default_factory=time.monotonic)
    format_id: str | None = None  # выбранный формат видео (для YouTube)


class RequestCache:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, DownloadRequest] = {}
        self._lock = asyncio.Lock()

    async def put(self, req: DownloadRequest) -> str:
        req_id = uuid.uuid4().hex[:12]
        async with self._lock:
            self._store[req_id] = req
        return req_id

    async def get(self, req_id: str) -> DownloadRequest | None:
        async with self._lock:
            return self._store.get(req_id)

    async def pop(self, req_id: str) -> DownloadRequest | None:
        async with self._lock:
            return self._store.pop(req_id, None)

    async def cleanup_loop(self) -> None:
        """Фоновая задача: раз в минуту чистит протухшие (никем не нажатые) записи.

        Обязательно запустить через asyncio.create_task(...) при старте бота,
        иначе кэш будет расти бесконечно, если часть кнопок никто не нажал.
        """
        while True:
            await asyncio.sleep(60)
            now = time.monotonic()
            async with self._lock:
                expired = [k for k, v in self._store.items() if now - v.created_at > self._ttl]
                for k in expired:
                    self._store.pop(k, None)


request_cache = RequestCache(ttl_seconds=config.CALLBACK_TTL_SECONDS)
