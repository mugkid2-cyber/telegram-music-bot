"""Общие компоненты для всех платформ."""
from .base import Platform, detect_platform, extract_url

__all__ = ["Platform", "detect_platform", "extract_url"]
