"""
Модуль сжатия видео для обхода ограничений Telegram.

Автоматически сжимает видео, которые превышают лимит Telegram (50 МБ),
сохраняя приемлемое качество.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VideoCompressor:
    """Сжатие видео через ffmpeg."""

    def __init__(self, max_size_mb: int = 50):
        """
        Args:
            max_size_mb: Максимальный размер файла в МБ
        """
        self.max_size_bytes = max_size_mb * 1024 * 1024
        # Запас на неточность (95% от лимита)
        self.target_size_bytes = int(self.max_size_bytes * 0.95)

    async def compress_if_needed(self, video_path: Path) -> Path:
        """
        Сжать видео если оно превышает лимит.

        Args:
            video_path: Путь к исходному видео

        Returns:
            Path к сжатому видео или исходному, если сжатие не требовалось
        """
        size = video_path.stat().st_size

        if size <= self.max_size_bytes:
            logger.info("Video size OK: %.2f MB", size / (1024 * 1024))
            return video_path

        logger.info(
            "Video too large: %.2f MB, compressing to ~%.2f MB",
            size / (1024 * 1024),
            self.target_size_bytes / (1024 * 1024),
        )

        # Получаем информацию о видео
        duration = await self._get_duration(video_path)
        if not duration:
            logger.error("Failed to get video duration")
            return video_path

        # Вычисляем целевой битрейт
        target_bitrate = self._calculate_bitrate(duration)

        # Сжимаем видео
        compressed_path = video_path.with_name(f"{video_path.stem}_compressed{video_path.suffix}")
        success = await self._compress(video_path, compressed_path, target_bitrate)

        if not success:
            logger.error("Compression failed, using original")
            return video_path

        # Проверяем результат
        compressed_size = compressed_path.stat().st_size
        logger.info(
            "Compression complete: %.2f MB -> %.2f MB (%.1f%%)",
            size / (1024 * 1024),
            compressed_size / (1024 * 1024),
            (compressed_size / size) * 100,
        )

        # Если всё ещё больше лимита, попробуем агрессивное сжатие
        if compressed_size > self.max_size_bytes:
            logger.warning("Still too large, trying aggressive compression")
            aggressive_path = video_path.with_name(f"{video_path.stem}_aggressive{video_path.suffix}")
            aggressive_bitrate = int(target_bitrate * 0.6)  # 60% от первой попытки

            success = await self._compress(video_path, aggressive_path, aggressive_bitrate)
            if success and aggressive_path.stat().st_size <= self.max_size_bytes:
                compressed_path.unlink(missing_ok=True)
                return aggressive_path

        return compressed_path if compressed_size <= self.max_size_bytes else video_path

    async def _get_duration(self, video_path: Path) -> float | None:
        """Получить длительность видео в секундах."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error("ffprobe error: %s", stderr.decode())
                return None

            return float(stdout.decode().strip())

        except Exception as e:
            logger.exception("Failed to get duration: %s", e)
            return None

    def _calculate_bitrate(self, duration: float) -> int:
        """
        Вычислить целевой битрейт для достижения нужного размера.

        Args:
            duration: Длительность видео в секундах

        Returns:
            Битрейт в кбит/с
        """
        # Резервируем ~10% на аудио
        video_size_bytes = self.target_size_bytes * 0.9

        # Битрейт = (размер в битах) / длительность в секундах / 1000 (для кбит/с)
        bitrate_kbps = int((video_size_bytes * 8) / duration / 1000)

        # Ограничиваем разумными пределами
        # Минимум 100 кбит/с, максимум 5000 кбит/с
        bitrate_kbps = max(100, min(5000, bitrate_kbps))

        logger.info("Calculated target bitrate: %d kbps for %.1fs video", bitrate_kbps, duration)
        return bitrate_kbps

    async def _compress(self, input_path: Path, output_path: Path, bitrate_kbps: int) -> bool:
        """
        Сжать видео с заданным битрейтом.

        Args:
            input_path: Исходное видео
            output_path: Путь для сжатого видео
            bitrate_kbps: Целевой битрейт видео в кбит/с

        Returns:
            True если успешно
        """
        # Аудио битрейт (96 кбит/с для речи, 128 для музыки)
        audio_bitrate = "96k"

        cmd = [
            "ffmpeg",
            "-i", str(input_path),
            "-c:v", "libx264",  # H.264 кодек
            "-preset", "medium",  # Баланс скорости и качества
            "-b:v", f"{bitrate_kbps}k",  # Видео битрейт
            "-maxrate", f"{int(bitrate_kbps * 1.5)}k",  # Пиковый битрейт
            "-bufsize", f"{bitrate_kbps * 2}k",  # Размер буфера
            "-c:a", "aac",  # AAC кодек для аудио
            "-b:a", audio_bitrate,  # Аудио битрейт
            "-movflags", "+faststart",  # Оптимизация для стриминга
            "-y",  # Перезаписать выходной файл
            str(output_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)  # 5 минут таймаут

            if proc.returncode != 0:
                logger.error("ffmpeg error: %s", stderr.decode())
                return False

            return output_path.exists()

        except asyncio.TimeoutError:
            logger.error("Compression timeout")
            try:
                proc.kill()
            except:
                pass
            return False

        except Exception as e:
            logger.exception("Compression failed: %s", e)
            return False


# Глобальный экземпляр компрессора
_compressor: VideoCompressor | None = None


def get_compressor(max_size_mb: int = 50) -> VideoCompressor:
    """Получить глобальный экземпляр компрессора."""
    global _compressor
    if _compressor is None:
        _compressor = VideoCompressor(max_size_mb)
    return _compressor
