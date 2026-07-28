import re
import time
from collections import defaultdict
from typing import Optional
from pathlib import Path


def sanitize_track_id(track_id: str) -> str:
    """
    Validates and sanitizes track_id to prevent path traversal attacks.

    Args:
        track_id: Track identifier from yt-dlp or other sources

    Returns:
        Sanitized track_id safe for filesystem operations

    Raises:
        ValueError: If track_id contains dangerous characters
    """
    if not track_id:
        raise ValueError("track_id cannot be empty")

    # Check for path traversal attempts
    if ".." in track_id or "/" in track_id or "\\" in track_id:
        raise ValueError(f"Invalid track_id: contains path traversal characters")

    # Allow only alphanumeric, dash, underscore, dot
    if not re.match(r'^[\w\-\.]+$', track_id):
        raise ValueError(f"Invalid track_id: contains unsafe characters")

    # Prevent overly long identifiers
    if len(track_id) > 255:
        raise ValueError(f"Invalid track_id: too long (max 255 chars)")

    return track_id


def validate_file_path(file_path: Path, base_dir: Path) -> Path:
    """
    Ensures file_path is within base_dir to prevent directory traversal.

    Args:
        file_path: Path to validate
        base_dir: Base directory that should contain the file

    Returns:
        Resolved absolute path

    Raises:
        ValueError: If path escapes base_dir
    """
    try:
        resolved_path = file_path.resolve()
        resolved_base = base_dir.resolve()

        if not str(resolved_path).startswith(str(resolved_base)):
            raise ValueError(f"Path {file_path} is outside base directory {base_dir}")

        return resolved_path
    except Exception as e:
        raise ValueError(f"Invalid file path: {e}")


class RateLimiter:
    """
    Token bucket rate limiter with per-user and global limits.
    """

    def __init__(
        self,
        per_user_rate: int = 5,
        per_user_period: int = 60,
        global_rate: int = 50,
        global_period: int = 60,
    ):
        """
        Args:
            per_user_rate: Max requests per user per period
            per_user_period: Time window in seconds for per-user limit
            global_rate: Max total requests per period
            global_period: Time window in seconds for global limit
        """
        self.per_user_rate = per_user_rate
        self.per_user_period = per_user_period
        self.global_rate = global_rate
        self.global_period = global_period

        self._user_requests: dict[int, list[float]] = defaultdict(list)
        self._global_requests: list[float] = []

    def check_rate_limit(self, user_id: int) -> tuple[bool, Optional[int]]:
        """
        Check if request is allowed under rate limits.

        Args:
            user_id: Telegram user ID

        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        now = time.time()

        # Clean old requests
        self._clean_old_requests(now)

        # Check global limit
        if len(self._global_requests) >= self.global_rate:
            retry_after = int(self._global_requests[0] + self.global_period - now) + 1
            return False, retry_after

        # Check per-user limit
        user_reqs = self._user_requests[user_id]
        if len(user_reqs) >= self.per_user_rate:
            retry_after = int(user_reqs[0] + self.per_user_period - now) + 1
            return False, retry_after

        # Allow request
        self._user_requests[user_id].append(now)
        self._global_requests.append(now)
        return True, None

    def _clean_old_requests(self, now: float) -> None:
        """Remove requests outside time windows."""
        # Clean per-user requests
        for user_id in list(self._user_requests.keys()):
            self._user_requests[user_id] = [
                t for t in self._user_requests[user_id]
                if now - t < self.per_user_period
            ]
            if not self._user_requests[user_id]:
                del self._user_requests[user_id]

        # Clean global requests
        self._global_requests = [
            t for t in self._global_requests
            if now - t < self.global_period
        ]

    def reset_user(self, user_id: int) -> None:
        """Reset rate limit for specific user (for testing or admin override)."""
        if user_id in self._user_requests:
            del self._user_requests[user_id]

    def get_stats(self) -> dict:
        """Get current rate limiter statistics."""
        now = time.time()
        self._clean_old_requests(now)

        return {
            "active_users": len(self._user_requests),
            "global_requests_in_window": len(self._global_requests),
            "global_limit": self.global_rate,
            "per_user_limit": self.per_user_rate,
        }
