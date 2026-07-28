"""Модель избранных треков."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FavoriteTrack:
    """Избранный трек пользователя."""
    user_id: int
    platform: str  # yt, sc, sf
    track_id: str
    title: str
    performer: str
    url: str
    added_at: datetime
