"""Модуль избранных треков."""
from app.media.audio.favorites.handlers import router
from app.media.audio.favorites.db import FavoritesDB

__all__ = ["router", "FavoritesDB"]
