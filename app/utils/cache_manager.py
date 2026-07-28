import asyncio
import logging
from pathlib import Path
from typing import List
import aiofiles.os

logger = logging.getLogger(__name__)


class CacheManager:
    """Manages cache size limits and automatic cleanup."""

    def __init__(
        self,
        cache_dir: Path,
        max_size_mb: int = 500,
        check_interval_hours: int = 6,
    ):
        """
        Args:
            cache_dir: Root cache directory
            max_size_mb: Maximum cache size in megabytes
            check_interval_hours: How often to check cache size
        """
        self.cache_dir = cache_dir
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.check_interval = check_interval_hours * 3600
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start automatic cache cleanup task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
            logger.info("Cache manager started: max_size=%dMB", self.max_size_bytes // (1024 * 1024))

    def stop(self) -> None:
        """Stop automatic cache cleanup task."""
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Cache manager stopped")

    async def _run(self) -> None:
        """Main loop for periodic cache cleanup."""
        while True:
            try:
                await asyncio.sleep(self.check_interval)
                await self.cleanup_if_needed()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Cache cleanup iteration failed")
                await asyncio.sleep(300)  # Wait 5 minutes on error

    async def get_cache_size(self) -> int:
        """Calculate total cache size in bytes."""
        total_size = 0
        if not self.cache_dir.exists():
            return 0

        for path in self.cache_dir.rglob("*"):
            if path.is_file():
                try:
                    stat = await aiofiles.os.stat(path)
                    total_size += stat.st_size
                except (OSError, FileNotFoundError):
                    continue

        return total_size

    async def get_cache_files(self) -> List[tuple[Path, float, int]]:
        """
        Get list of cache files with metadata.

        Returns:
            List of (file_path, access_time, size_bytes) sorted by access time (oldest first)
        """
        files = []
        if not self.cache_dir.exists():
            return files

        for path in self.cache_dir.rglob("*"):
            if path.is_file():
                try:
                    stat = await aiofiles.os.stat(path)
                    # Use access time for LRU
                    files.append((path, stat.st_atime, stat.st_size))
                except (OSError, FileNotFoundError):
                    continue

        # Sort by access time (oldest first)
        files.sort(key=lambda x: x[1])
        return files

    async def cleanup_if_needed(self) -> dict:
        """
        Check cache size and clean up old files if over limit.

        Returns:
            Dict with cleanup statistics
        """
        current_size = await self.get_cache_size()
        size_mb = current_size / (1024 * 1024)

        logger.info("Cache size check: %.2f MB / %.2f MB", size_mb, self.max_size_bytes / (1024 * 1024))

        if current_size <= self.max_size_bytes:
            return {
                "cleaned": False,
                "current_size_mb": size_mb,
                "files_removed": 0,
                "bytes_freed": 0,
            }

        logger.warning("Cache size %.2f MB exceeds limit, starting cleanup", size_mb)

        files = await self.get_cache_files()
        target_size = int(self.max_size_bytes * 0.8)  # Clean to 80% of limit
        bytes_to_free = current_size - target_size

        files_removed = 0
        bytes_freed = 0

        for file_path, _, file_size in files:
            if bytes_freed >= bytes_to_free:
                break

            try:
                await aiofiles.os.remove(file_path)
                files_removed += 1
                bytes_freed += file_size
                logger.debug("Removed cache file: %s (%.2f MB)", file_path.name, file_size / (1024 * 1024))
            except (OSError, FileNotFoundError):
                logger.warning("Failed to remove cache file: %s", file_path)
                continue

        # Clean up empty directories
        await self._cleanup_empty_dirs()

        logger.info(
            "Cache cleanup completed: removed %d files, freed %.2f MB",
            files_removed,
            bytes_freed / (1024 * 1024)
        )

        return {
            "cleaned": True,
            "files_removed": files_removed,
            "bytes_freed_mb": bytes_freed / (1024 * 1024),
            "current_size_mb": (current_size - bytes_freed) / (1024 * 1024),
        }

    async def _cleanup_empty_dirs(self) -> None:
        """Remove empty directories in cache."""
        if not self.cache_dir.exists():
            return

        for path in sorted(self.cache_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and path != self.cache_dir:
                try:
                    if not list(path.iterdir()):
                        await aiofiles.os.rmdir(path)
                        logger.debug("Removed empty directory: %s", path)
                except (OSError, FileNotFoundError):
                    continue

    async def clear_all(self) -> int:
        """
        Remove all cache files.

        Returns:
            Number of files removed
        """
        if not self.cache_dir.exists():
            return 0

        files_removed = 0
        for path in self.cache_dir.rglob("*"):
            if path.is_file():
                try:
                    await aiofiles.os.remove(path)
                    files_removed += 1
                except (OSError, FileNotFoundError):
                    continue

        await self._cleanup_empty_dirs()

        logger.info("Cleared all cache: %d files removed", files_removed)
        return files_removed

    async def get_stats(self) -> dict:
        """Get current cache statistics."""
        current_size = await self.get_cache_size()
        files = await self.get_cache_files()

        return {
            "size_mb": current_size / (1024 * 1024),
            "max_size_mb": self.max_size_bytes / (1024 * 1024),
            "usage_percent": (current_size / self.max_size_bytes * 100) if self.max_size_bytes > 0 else 0,
            "file_count": len(files),
            "oldest_file_age_hours": (asyncio.get_event_loop().time() - files[0][1]) / 3600 if files else 0,
        }
