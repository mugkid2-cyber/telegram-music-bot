"""Временное хранилище URL треков между поиском и скачиванием."""

_urls: dict[str, str] = {}


def _key(platform: str, track_id: str) -> str:
    return f"{platform}:{track_id}"


def store_url(platform: str, track_id: str, url: str) -> None:
    if url:
        _urls[_key(platform, track_id)] = url


def get_url(platform: str, track_id: str) -> str | None:
    return _urls.get(_key(platform, track_id))


def pop_url(platform: str, track_id: str) -> str | None:
    return _urls.pop(_key(platform, track_id), None)
