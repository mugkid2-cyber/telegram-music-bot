"""
Сервис перевода текста с использованием Google Translate API.
"""
import logging
import aiohttp
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class TranslatorService:
    """Сервис для перевода текста через Google Translate API."""

    BASE_URL = "https://translate.googleapis.com/translate_a/single"

    # Кеш сессий для повторного использования
    _session: Optional[aiohttp.ClientSession] = None

    # Маппинг кодов языков Google на эмодзи флагов
    LANGUAGE_FLAGS = {
        'en': '🇬🇧', 'de': '🇩🇪', 'fr': '🇫🇷', 'es': '🇪🇸', 'it': '🇮🇹',
        'pt': '🇵🇹', 'pl': '🇵🇱', 'uk': '🇺🇦', 'tr': '🇹🇷', 'zh': '🇨🇳',
        'zh-CN': '🇨🇳', 'zh-TW': '🇹🇼', 'ja': '🇯🇵', 'ko': '🇰🇷',
        'ar': '🇸🇦', 'he': '🇮🇱', 'ru': '🇷🇺', 'nl': '🇳🇱', 'sv': '🇸🇪',
        'no': '🇳🇴', 'da': '🇩🇰', 'cs': '🇨🇿', 'ro': '🇷🇴', 'hu': '🇭🇺',
        'fi': '🇫🇮', 'th': '🇹🇭', 'el': '🇬🇷', 'bg': '🇧🇬', 'sr': '🇷🇸',
        'hr': '🇭🇷', 'sk': '🇸🇰', 'sl': '🇸🇮', 'et': '🇪🇪', 'lv': '🇱🇻',
        'lt': '🇱🇹', 'vi': '🇻🇳', 'id': '🇮🇩', 'ms': '🇲🇾', 'hi': '🇮🇳',
        'bn': '🇧🇩', 'fa': '🇮🇷', 'ur': '🇵🇰', 'sw': '🇰🇪', 'af': '🇿🇦',
        'sq': '🇦🇱', 'az': '🇦🇿', 'be': '🇧🇾', 'ka': '🇬🇪', 'hy': '🇦🇲',
        'kk': '🇰🇿', 'uz': '🇺🇿', 'mn': '🇲🇳', 'ne': '🇳🇵', 'si': '🇱🇰',
        'km': '🇰🇭', 'lo': '🇱🇦', 'my': '🇲🇲', 'am': '🇪🇹', 'tl': '🇵🇭',
    }

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        """Получает или создает переиспользуемую сессию."""
        if cls._session is None or cls._session.closed:
            cls._session = aiohttp.ClientSession()
        return cls._session

    @classmethod
    async def close_session(cls) -> None:
        """Закрывает сессию."""
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None

    @classmethod
    async def translate(cls, text: str, target_lang: str = "ru") -> Tuple[Optional[str], Optional[str]]:
        """
        Переводит текст на целевой язык.

        Args:
            text: Текст для перевода
            target_lang: Целевой язык (по умолчанию русский)

        Returns:
            Кортеж (переведенный текст, код определённого языка) или (None, None) в случае ошибки
        """
        if not text or len(text.strip()) == 0:
            return None, None

        try:
            params = {
                "client": "gtx",
                "sl": "auto",
                "tl": target_lang,
                "dt": "t",
                "q": text
            }

            session = await cls.get_session()
            async with session.get(
                cls.BASE_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    logger.error(f"Translation API returned status {response.status}")
                    return None, None

                data = await response.json()

                # Парсим ответ Google Translate
                if not data or not isinstance(data, list) or len(data) == 0:
                    return None, None

                translations = data[0]
                if not translations or not isinstance(translations, list):
                    return None, None

                # Собираем все части перевода
                translated_parts = []
                for translation in translations:
                    if translation and isinstance(translation, list) and len(translation) > 0:
                        translated_parts.append(translation[0])

                if not translated_parts:
                    return None, None

                result = "".join(translated_parts)

                # Извлекаем определённый язык из ответа
                detected_lang = None
                if len(data) > 2 and data[2]:
                    detected_lang = data[2]

                return result.strip() if result else None, detected_lang

        except aiohttp.ClientError as e:
            logger.error(f"Network error during translation: {e}")
            return None, None
        except Exception as e:
            logger.exception(f"Unexpected error during translation: {e}")
            return None, None

    @classmethod
    def get_flag_emoji(cls, lang_code: Optional[str]) -> str:
        """
        Возвращает эмодзи флага для кода языка.

        Args:
            lang_code: Код языка (например, 'en', 'de', 'uk')

        Returns:
            Эмодзи флага или общий эмодзи 🌐
        """
        if not lang_code:
            return '🌐'

        return cls.LANGUAGE_FLAGS.get(lang_code, '🌐')

