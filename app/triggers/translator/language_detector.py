"""
Определение языка текста без внешних зависимостей.
"""
import re
from typing import Optional, Tuple


class LanguageDetector:
    """Простой детектор языка на основе алфавитов и ключевых слов."""

    # Диапазоны Unicode для разных алфавитов
    CYRILLIC_PATTERN = re.compile(r'[Ѐ-ӿ]')
    LATIN_PATTERN = re.compile(r'[a-zA-Z]')
    CHINESE_PATTERN = re.compile(r'[一-鿿]')
    JAPANESE_PATTERN = re.compile(r'[぀-ゟ゠-ヿ]')
    KOREAN_PATTERN = re.compile(r'[가-힯]')
    ARABIC_PATTERN = re.compile(r'[؀-ۿ]')
    HEBREW_PATTERN = re.compile(r'[֐-׿]')
    THAI_PATTERN = re.compile(r'[ก-๛]')
    GREEK_PATTERN = re.compile(r'[Ͱ-Ͽ]')

    # Характерные буквы для украинского языка
    UKRAINIAN_LETTERS = {'є', 'і', 'ї', 'ґ', 'Є', 'І', 'Ї', 'Ґ'}

    # Характерные слова для русского языка
    RUSSIAN_WORDS = {
        'это', 'что', 'как', 'так', 'все', 'его', 'его', 'она', 'был', 'была', 'было',
        'были', 'быть', 'мне', 'тебе', 'ему', 'ней', 'нас', 'вас', 'них', 'меня',
        'тебя', 'него', 'неё', 'нём', 'или', 'где', 'когда', 'чтобы', 'если', 'очень',
        'только', 'теперь', 'всё', 'тоже', 'здесь', 'ещё', 'уже', 'может', 'можно'
    }

    # Характерные слова для украинского языка
    UKRAINIAN_WORDS = {
        'що', 'як', 'все', 'його', 'вона', 'був', 'була', 'було', 'були', 'бути',
        'мені', 'тобі', 'йому', 'їй', 'нам', 'вам', 'їм', 'мене', 'тебе', 'нього',
        'неї', 'або', 'де', 'коли', 'щоб', 'якщо', 'дуже', 'тільки', 'тепер',
        'теж', 'тут', 'ще', 'вже', 'може', 'можна', 'який', 'яка', 'яке', 'які',
        'цей', 'ця', 'це', 'ці', 'той', 'та', 'те', 'ті'
    }

    # Характерные слова для других языков
    LANGUAGE_KEYWORDS = {
        'en': ['the', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 'will', 'would', 'can', 'could', 'should', 'may', 'might', 'please', 'thank', 'you', 'your', 'this', 'that', 'with', 'from', 'they', 'them', 'their', 'there', 'where', 'when', 'what', 'how', 'why', 'who', 'which', 'been', 'being', 'some', 'such', 'into', 'just', 'only', 'over', 'both', 'each', 'most', 'than', 'then', 'very', 'more'],
        'de': ['der', 'die', 'das', 'und', 'ist', 'nicht', 'ein', 'eine', 'ich', 'du', 'er', 'sie', 'wir', 'ihr', 'mit', 'für', 'auf', 'von', 'zu', 'den', 'dem', 'des', 'auch', 'aber', 'oder', 'wenn', 'dass', 'wie', 'nach', 'bei', 'über', 'unter', 'sich', 'sein', 'haben', 'werden', 'können', 'müssen', 'sollen', 'wollen'],
        'fr': ['le', 'la', 'les', 'un', 'une', 'de', 'du', 'des', 'et', 'est', 'sont', 'dans', 'pour', 'avec', 'sur', 'par', 'pas', 'plus', 'ce', 'qui', 'que', 'nous', 'vous', 'ils', 'elles', 'je', 'tu', 'il', 'elle', 'au', 'aux', 'mais', 'ou', 'où', 'sont', 'était', 'été', 'avoir', 'être', 'faire', 'aller', 'voir', 'venir'],
        'es': ['el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'y', 'es', 'son', 'en', 'por', 'con', 'para', 'que', 'no', 'lo', 'se', 'su', 'sus', 'yo', 'tú', 'él', 'ella', 'nosotros', 'ustedes', 'ellos', 'ellas', 'está', 'están', 'pero', 'o', 'hay', 'ser', 'estar', 'tener', 'hacer', 'poder', 'decir', 'ir', 'ver', 'dar'],
        'it': ['il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'una', 'di', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra', 'è', 'sono', 'non', 'che', 'del', 'della', 'dei', 'delle', 'al', 'alla', 'ai', 'alle', 'nel', 'nella', 'nei', 'nelle', 'io', 'tu', 'lui', 'lei', 'noi', 'voi', 'loro', 'ma', 'o', 'e', 'essere', 'avere', 'fare', 'potere', 'volere'],
        'pt': ['o', 'a', 'os', 'as', 'um', 'uma', 'de', 'do', 'da', 'dos', 'das', 'e', 'é', 'são', 'em', 'no', 'na', 'nos', 'nas', 'por', 'para', 'com', 'que', 'não', 'se', 'mais', 'eu', 'você', 'ele', 'ela', 'nós', 'vocês', 'eles', 'elas', 'mas', 'ou', 'ser', 'estar', 'ter', 'fazer', 'poder', 'ver', 'dar'],
        'pl': ['i', 'w', 'na', 'z', 'do', 'o', 'że', 'nie', 'się', 'jest', 'są', 'był', 'była', 'było', 'byli', 'były', 'jak', 'co', 'to', 'ten', 'ta', 'te', 'dla', 'od', 'przez', 'po', 'przy', 'bez', 'pod', 'nad', 'przed', 'za', 'już', 'tylko', 'może', 'ale', 'lub', 'być', 'mieć', 'móc', 'wiedzieć'],
        'tr': ['ve', 'bir', 'bu', 'için', 'ile', 'de', 'da', 'mi', 'mı', 'mu', 'mü', 'ne', 'var', 'yok', 'gibi', 'kadar', 'daha', 'en', 'çok', 'şey', 'olan', 'olarak', 'değil', 'ama', 'veya', 'ya', 'olmak', 'etmek', 'yapmak', 'görmek'],
        'nl': ['de', 'het', 'een', 'van', 'en', 'in', 'is', 'dat', 'op', 'voor', 'met', 'aan', 'als', 'te', 'zijn', 'was', 'om', 'ook', 'maar', 'niet', 'bij', 'naar', 'er', 'uit', 'hij', 'zij', 'hebben', 'worden', 'kunnen', 'zullen'],
        'sv': ['och', 'i', 'att', 'det', 'en', 'som', 'är', 'på', 'för', 'av', 'med', 'till', 'den', 'har', 'de', 'inte', 'ett', 'om', 'var', 'kan', 'man', 'från', 'men', 'vid', 'han', 'hon', 'vara', 'ha', 'kunna', 'få', 'skulle'],
        'no': ['og', 'i', 'det', 'er', 'til', 'en', 'av', 'for', 'på', 'med', 'som', 'har', 'den', 'ikke', 'et', 'var', 'de', 'kan', 'om', 'fra', 'han', 'hun', 'være', 'ha', 'kunne', 'ville', 'skulle'],
        'da': ['og', 'i', 'det', 'er', 'til', 'en', 'af', 'for', 'på', 'med', 'som', 'har', 'den', 'ikke', 'et', 'var', 'de', 'kan', 'om', 'fra', 'han', 'hun', 'være', 'have', 'kunne', 'ville', 'skulle'],
        'cs': ['a', 'v', 'na', 'z', 'do', 'o', 'že', 'je', 'se', 'pro', 'byl', 'byla', 'bylo', 'být', 'mít', 'moci', 'vědět', 'jako', 'co', 'to', 'ten', 'ta', 'už', 'jen', 'také', 'tak'],
        'ro': ['și', 'în', 'de', 'la', 'cu', 'un', 'o', 'pe', 'este', 'sunt', 'pentru', 'că', 'ce', 'dar', 'sau', 'a', 'el', 'ea', 'eu', 'tu', 'fi', 'avea', 'face', 'putea'],
        'hu': ['a', 'az', 'és', 'van', 'hogy', 'nem', 'egy', 'be', 'ki', 'el', 'meg', 'fel', 'le', 'mit', 'még', 'csak', 'ezt', 'azt', 'aki', 'ami', 'lenni', 'lesz', 'volt'],
        'fi': ['ja', 'on', 'ei', 'se', 'että', 'en', 'oli', 'hän', 'kun', 'tai', 'voi', 'ei', 'niin', 'kuin', 'jos', 'mutta', 'mikä', 'olla', 'voida', 'tehdä', 'saada'],
    }

    # Флаги стран для языков
    LANGUAGE_FLAGS = {
        'en': '🇬🇧', 'de': '🇩🇪', 'fr': '🇫🇷', 'es': '🇪🇸', 'it': '🇮🇹',
        'pt': '🇵🇹', 'pl': '🇵🇱', 'uk': '🇺🇦', 'tr': '🇹🇷', 'zh': '🇨🇳',
        'ja': '🇯🇵', 'ko': '🇰🇷', 'ar': '🇸🇦', 'he': '🇮🇱', 'ru': '🇷🇺',
        'nl': '🇳🇱', 'sv': '🇸🇪', 'no': '🇳🇴', 'da': '🇩🇰', 'cs': '🇨🇿',
        'ro': '🇷🇴', 'hu': '🇭🇺', 'fi': '🇫🇮', 'th': '🇹🇭', 'el': '🇬🇷',
    }

    @classmethod
    def detect(cls, text: str) -> Optional[str]:
        """
        Определяет, является ли текст иностранным (не русским).

        Args:
            text: Текст для анализа

        Returns:
            'ru' для русского, 'foreign' для иностранного, None если не удалось определить
        """
        if not text or len(text.strip()) < 3:
            return None

        # Проверяем характерные украинские буквы
        if any(letter in text for letter in cls.UKRAINIAN_LETTERS):
            return 'foreign'

        # Проверяем украинские слова
        text_lower = text.lower()
        words = re.findall(r'\b[\w]+\b', text_lower)

        if words:
            ukrainian_matches = sum(1 for word in words if word in cls.UKRAINIAN_WORDS)
            russian_matches = sum(1 for word in words if word in cls.RUSSIAN_WORDS)

            # Если есть украинские слова - это иностранный
            if ukrainian_matches > 0:
                return 'foreign'

            # Если есть русские слова - это русский
            if russian_matches >= 2:
                return 'ru'

        # Убираем пробелы, знаки препинания и цифры для анализа
        clean_text = re.sub(r'[\s\d\W_]+', '', text)

        if not clean_text:
            return None

        # Подсчитываем символы разных алфавитов
        cyrillic_count = len(cls.CYRILLIC_PATTERN.findall(clean_text))
        latin_count = len(cls.LATIN_PATTERN.findall(clean_text))
        chinese_count = len(cls.CHINESE_PATTERN.findall(clean_text))
        japanese_count = len(cls.JAPANESE_PATTERN.findall(clean_text))
        korean_count = len(cls.KOREAN_PATTERN.findall(clean_text))
        arabic_count = len(cls.ARABIC_PATTERN.findall(clean_text))
        hebrew_count = len(cls.HEBREW_PATTERN.findall(clean_text))
        thai_count = len(cls.THAI_PATTERN.findall(clean_text))
        greek_count = len(cls.GREEK_PATTERN.findall(clean_text))

        total_chars = len(clean_text)

        # Если больше 50% кириллицы и есть русские слова - это русский
        if cyrillic_count / total_chars > 0.5 and russian_matches > 0:
            return 'ru'

        # Если есть значимое количество иностранных символов - это иностранный текст
        foreign_count = (latin_count + chinese_count + japanese_count +
                        korean_count + arabic_count + hebrew_count + thai_count + greek_count)

        if foreign_count / total_chars > 0.3:
            return 'foreign'

        # Если кириллица, но нет русских слов - возможно украинский
        if cyrillic_count / total_chars > 0.5:
            return 'foreign'

        return None

    @classmethod
    def detect_specific_language(cls, text: str) -> Tuple[Optional[str], str]:
        """
        Определяет конкретный язык текста.

        Args:
            text: Текст для анализа

        Returns:
            Кортеж (код языка, флаг страны)
        """
        if not text or len(text.strip()) < 3:
            return None, '🌐'

        text_lower = text.lower()
        clean_text = re.sub(r'[\s\d\W_]+', '', text)

        if not clean_text:
            return None, '🌐'

        # Проверяем украинский язык по характерным буквам
        if any(letter in text for letter in cls.UKRAINIAN_LETTERS):
            return 'uk', cls.LANGUAGE_FLAGS['uk']

        # Проверяем украинский по словам
        words = re.findall(r'\b[\w]+\b', text_lower)
        if words:
            ukrainian_matches = sum(1 for word in words if word in cls.UKRAINIAN_WORDS)
            if ukrainian_matches >= 2:
                return 'uk', cls.LANGUAGE_FLAGS['uk']

        # Проверяем неалфавитные языки
        chinese_count = len(cls.CHINESE_PATTERN.findall(clean_text))
        japanese_count = len(cls.JAPANESE_PATTERN.findall(clean_text))
        korean_count = len(cls.KOREAN_PATTERN.findall(clean_text))
        arabic_count = len(cls.ARABIC_PATTERN.findall(clean_text))
        hebrew_count = len(cls.HEBREW_PATTERN.findall(clean_text))
        thai_count = len(cls.THAI_PATTERN.findall(clean_text))
        greek_count = len(cls.GREEK_PATTERN.findall(clean_text))

        total_chars = len(clean_text)

        if chinese_count / total_chars > 0.5:
            return 'zh', cls.LANGUAGE_FLAGS['zh']
        if japanese_count / total_chars > 0.5:
            return 'ja', cls.LANGUAGE_FLAGS['ja']
        if korean_count / total_chars > 0.5:
            return 'ko', cls.LANGUAGE_FLAGS['ko']
        if arabic_count / total_chars > 0.5:
            return 'ar', cls.LANGUAGE_FLAGS['ar']
        if hebrew_count / total_chars > 0.5:
            return 'he', cls.LANGUAGE_FLAGS['he']
        if thai_count / total_chars > 0.5:
            return 'th', cls.LANGUAGE_FLAGS['th']
        if greek_count / total_chars > 0.5:
            return 'el', cls.LANGUAGE_FLAGS['el']

        # Для латинских и кириллических языков используем ключевые слова
        if not words:
            return None, '🌐'

        # Подсчитываем совпадения для каждого языка
        scores = {}
        for lang, keywords in cls.LANGUAGE_KEYWORDS.items():
            score = sum(1 for word in words if word in keywords)
            if score > 0:
                scores[lang] = score

        if not scores:
            # Если не нашли ключевых слов, возвращаем общий флаг
            return None, '🌐'

        # Выбираем язык с максимальным score
        best_lang = max(scores, key=scores.get)
        return best_lang, cls.LANGUAGE_FLAGS.get(best_lang, '🌐')
