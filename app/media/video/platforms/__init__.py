"""
Платформы для скачивания видео.

Каждая платформа находится в своей подпапке с собственным downloader.
"""
from .common.base import Platform, detect_platform, extract_url

__all__ = ["Platform", "detect_platform", "extract_url"]
