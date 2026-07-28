import logging
import shutil
import subprocess
import sys
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

_FFMPEG_NAMES = ("ffmpeg.exe", "ffmpeg") if sys.platform == "win32" else ("ffmpeg",)


def _executable_candidates(path: Path) -> list[Path]:
    if path.is_dir():
        return [path / name for name in _FFMPEG_NAMES]
    return [path]


def resolve_ffmpeg_path() -> str | None:
    settings = get_settings()
    candidates: list[Path] = []

    if settings.FFMPEG_PATH:
        candidates.extend(_executable_candidates(Path(settings.FFMPEG_PATH)))

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
        logger.warning("FFMPEG_PATH candidate is not a file: %s", candidate)

    found = shutil.which("ffmpeg")
    if found:
        return found

    logger.warning("ffmpeg not found in PATH")
    return None


def resolve_ffmpeg_location() -> str | None:
    """Путь для yt-dlp: директория с ffmpeg или путь к исполняемому файлу."""
    settings = get_settings()
    if settings.FFMPEG_PATH:
        path = Path(settings.FFMPEG_PATH)
        if path.is_dir():
            return str(path)
        if path.is_file():
            return str(path.parent)
    executable = resolve_ffmpeg_path()
    if executable:
        return str(Path(executable).parent)
    return None


def ensure_ffmpeg_available() -> str:
    path = resolve_ffmpeg_path()
    if not path:
        raise RuntimeError(
            "ffmpeg не найден. Установите ffmpeg или укажите FFMPEG_PATH в .env "
            "(например C:/ffmpeg/bin/ffmpeg.exe)"
        )
    return path


def convert_image_to_jpg(source: Path, dest: Path) -> Path | None:
    """
    Конвертирует изображение в JPG формат с использованием ffmpeg.

    Args:
        source: Исходный файл изображения
        dest: Целевой путь для JPG файла

    Returns:
        Path к конвертированному файлу или None при ошибке
    """
    if not source.exists():
        return None

    if source.suffix.lower() in {".jpg", ".jpeg"}:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.unlink()
        try:
            source.rename(dest)
            return dest
        except OSError:
            logger.warning("Failed to move thumbnail: %s -> %s", source, dest)
            return None

    ffmpeg = resolve_ffmpeg_path()
    if not ffmpeg:
        logger.warning("Skip thumbnail conversion: ffmpeg not found")
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(source), "-q:v", "2", str(dest)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("ffmpeg conversion failed with code %d", result.returncode)
            return None
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg conversion timeout for %s", source)
        return None
    except (subprocess.CalledProcessError, PermissionError, OSError) as exc:
        logger.warning("Failed to convert thumbnail %s: %s", source, exc)
        return None
    finally:
        if source.exists() and source != dest:
            source.unlink(missing_ok=True)

    return dest if dest.exists() else None
