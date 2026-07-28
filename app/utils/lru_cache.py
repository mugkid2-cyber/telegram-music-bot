"""Simple LRU Cache with TTL support."""
from collections import OrderedDict
from time import time
from typing import Any, Optional


class LRUCache:
    """LRU cache с автоматическим истечением времени жизни."""

    def __init__(self, max_size: int = 1000, ttl: int = 300):
        """
        Args:
            max_size: Максимальное количество элементов
            ttl: Время жизни элемента в секундах
        """
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        """Получает значение из кеша."""
        if key not in self._cache:
            return None

        value, timestamp = self._cache[key]
        if time() - timestamp > self._ttl:
            del self._cache[key]
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        """Сохраняет значение в кеш."""
        if key in self._cache:
            del self._cache[key]
        elif len(self._cache) >= self._max_size:
            # Remove oldest item
            self._cache.popitem(last=False)

        self._cache[key] = (value, time())

    def clear(self) -> None:
        """Очищает весь кеш."""
        self._cache.clear()

    def __len__(self) -> int:
        """Возвращает текущий размер кеша."""
        return len(self._cache)

    def cleanup_expired(self) -> int:
        """Удаляет истёкшие элементы. Возвращает количество удалённых."""
        now = time()
        expired = [
            key for key, (_, timestamp) in self._cache.items()
            if now - timestamp > self._ttl
        ]
        for key in expired:
            del self._cache[key]
        return len(expired)
