# Video Downloader Module

Модуль для скачивания видео с популярных платформ: TikTok, YouTube, Instagram.

## Поддерживаемые платформы

### 🎵 TikTok
- Обычные видео
- Сохранение в базу данных
- Команда `/tt` для случайного видео

### ▶️ YouTube
- Обычные видео
- YouTube Shorts
- Выбор качества
- Извлечение аудио

### 📷 Instagram
- Посты с видео
- Reels
- IGTV
- Обработка каруселей

## Использование

### В Telegram

1. Отправить ссылку на видео
2. Выбрать "Видео" или "Аудио"
3. Бот скачает и отправит файл

**Команды:**
- `/tt` - случайный TikTok из базы (последние 3 дня)

## Структура модуля

```
platforms/
├── common/base.py       # Platform enum, detect_platform()
├── tiktok/             # TikTok загрузчик + БД
├── youtube/            # YouTube загрузчик
└── instagram/          # Instagram загрузчик
```

## Добавление новой платформы

1. Создать `platforms/newplatform/downloader.py`
2. Добавить регулярное выражение в `platforms/common/base.py`
3. Зарегистрировать в `router.py`

Готово! ✅
