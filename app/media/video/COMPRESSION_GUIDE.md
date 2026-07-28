# Обход ограничения размера файлов Telegram

## Проблема

Telegram Bot API имеет жёсткий лимит на размер отправляемых файлов:
- **Облачный Bot API**: 50 МБ
- **Локальный Bot API**: до 2000 МБ (2 ГБ)

## Решения

### 1. ✅ Автоматическое сжатие (уже реализовано)

Бот автоматически сжимает видео, которые превышают лимит.

**Как работает:**
1. Видео скачивается в исходном качестве
2. Если размер > 50 МБ, запускается сжатие
3. Вычисляется оптимальный битрейт для достижения 95% от лимита
4. ffmpeg сжимает видео с H.264 кодеком
5. Если всё ещё большое, применяется агрессивное сжатие (60% битрейт)

**Параметры сжатия:**
```python
# Видео
- Кодек: libx264 (H.264)
- Пресет: medium (баланс скорости/качества)
- Битрейт: автоматически вычисляется
- Оптимизация: faststart для стриминга

# Аудио
- Кодек: AAC
- Битрейт: 96 кбит/с (речь) или 128 кбит/с (музыка)
```

**Пример:**
```
Исходный файл: 306 МБ, 10 минут
↓ Сжатие
Результат: ~47 МБ, 10 минут
Качество: приемлемое для просмотра в Telegram
```

**Преимущества:**
- ✅ Работает автоматически
- ✅ Не требует настройки
- ✅ Сохраняет приемлемое качество
- ✅ Бесплатно

**Недостатки:**
- ❌ Потеря качества
- ❌ Время сжатия (~1-3 минуты на 10 минут видео)
- ❌ Очень длинные видео могут не влезть даже после сжатия

### 2. Локальный Bot API сервер (рекомендуется для больших файлов)

Telegram предоставляет возможность развернуть собственный Bot API сервер с лимитом до **2000 МБ**.

#### Установка на Windows

1. **Скачать Bot API сервер:**
```bash
# Официальный репозиторий
https://github.com/tdlib/telegram-bot-api

# Готовые бинарники
https://github.com/tdlib/telegram-bot-api/releases
```

2. **Запустить сервер:**
```bash
telegram-bot-api.exe --api-id=YOUR_API_ID --api-hash=YOUR_API_HASH --local
```

3. **Получить API credentials:**
   - Зайти на https://my.telegram.org
   - Создать приложение
   - Скопировать `api_id` и `api_hash`

4. **Настроить бота:**
```python
# app/config.py
BOT_API_URL = "http://localhost:8081/bot{token}/"  # Локальный сервер

# При создании бота
from aiogram import Bot

bot = Bot(
    token=BOT_TOKEN,
    base_url=BOT_API_URL  # Использовать локальный сервер
)
```

#### Установка на Linux (Docker)

```bash
docker run -d \
  --name telegram-bot-api \
  -p 8081:8081 \
  -e TELEGRAM_API_ID=YOUR_API_ID \
  -e TELEGRAM_API_HASH=YOUR_API_HASH \
  -v /var/telegram-bot-api:/var/telegram-bot-api \
  ghcr.io/tdlib/telegram-bot-api:latest
```

**Преимущества:**
- ✅ Лимит до 2000 МБ
- ✅ Без потери качества
- ✅ Быстрая отправка

**Недостатки:**
- ❌ Требует установки и настройки
- ❌ Нужны API credentials
- ❌ Дополнительные ресурсы сервера

### 3. Разделение на части (не рекомендуется)

Разбить видео на несколько частей по <50 МБ.

**Недостатки:**
- ❌ Неудобно для пользователя
- ❌ Сложная логика
- ❌ Telegram может объединить части некорректно

## Текущая реализация

В боте используется **автоматическое сжатие** как основное решение:

```python
# app/media/video/router.py

# Проверяем размер после скачивания
if original_size > config.MAX_FILE_SIZE_BYTES:
    # Уведомляем пользователя
    await call.message.edit_text("🔄 Видео слишком большое, сжимаю...")
    
    # Сжимаем
    compressor = get_compressor(config.MAX_FILE_SIZE_MB)
    path = await compressor.compress_if_needed(path)
    
    # Проверяем результат
    if compressed_size > config.MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(...)
```

## Настройка

### Изменить лимит сжатия

```python
# app/media/video/config.py

# Если используете локальный Bot API
MAX_FILE_SIZE_MB = 2000  # 2 ГБ вместо 50 МБ
```

### Настроить качество сжатия

```python
# app/media/video/compressor.py

# Более агрессивное сжатие (меньше размер, хуже качество)
self.target_size_bytes = int(self.max_size_bytes * 0.80)  # 80% вместо 95%

# Менее агрессивное (больше размер, лучше качество)
self.target_size_bytes = int(self.max_size_bytes * 0.98)  # 98%
```

### Отключить автосжатие

```python
# app/media/video/router.py

# Закомментировать блок сжатия:
# if original_size > config.MAX_FILE_SIZE_BYTES:
#     compressor = get_compressor(...)
#     path = await compressor.compress_if_needed(path)
```

## Рекомендации

**Для личного использования:**
- Используйте автоматическое сжатие (уже работает)

**Для публичного бота:**
- Настройте локальный Bot API сервер
- Лимит 2000 МБ покроет 99% случаев

**Для продакшн сервера:**
- Локальный Bot API на отдельном сервере
- Балансировка нагрузки
- Мониторинг дискового пространства

## Проблемы и решения

### "Сжатие занимает слишком много времени"
- Используйте более быстрый пресет: `ultrafast` вместо `medium`
- Уменьшите разрешение: добавьте `-vf scale=1280:-1`

### "Качество после сжатия плохое"
- Увеличьте целевой размер (95% → 98%)
- Используйте локальный Bot API вместо сжатия

### "ffmpeg не найден"
- Установите ffmpeg: https://ffmpeg.org/download.html
- Добавьте в PATH

### "Видео всё равно не влезает"
- Максимальная длительность ограничена
- Попросите пользователя отправить более короткое видео
- Используйте локальный Bot API с лимитом 2000 МБ

## Тестирование

```bash
# Проверка работы компрессора
cd C:/SOLOO/SOLO
python -c "
from app.media.video.compressor import get_compressor
from pathlib import Path

compressor = get_compressor(max_size_mb=50)
# Для теста нужен реальный файл > 50 МБ
"
```

## Дополнительная информация

- [Telegram Bot API Limits](https://core.telegram.org/bots/api#sending-files)
- [Local Bot API Server](https://github.com/tdlib/telegram-bot-api)
- [ffmpeg Documentation](https://ffmpeg.org/ffmpeg.html)
