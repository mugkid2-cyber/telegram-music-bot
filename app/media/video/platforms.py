"""
Определение платформы по ссылке и извлечение самой ссылки из текста.

DEPRECATED: Этот файл оставлен для обратной совместимости.
Используйте app.media.video.platforms вместо этого модуля.
"""
from __future__ import annotations

from app.media.video.platforms import Platform, detect_platform, extract_url

__all__ = ["Platform", "detect_platform", "extract_url"]
