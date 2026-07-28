"""
Health check HTTP server for monitoring bot status.
Runs alongside the bot on a separate port.
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from aiohttp import web

logger = logging.getLogger(__name__)


class HealthCheckServer:
    """Simple HTTP server for health checks and metrics."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self.start_time = datetime.now()

        # Setup routes
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/metrics", self.metrics)
        self.app.router.add_get("/ready", self.ready)

    async def start(self) -> None:
        """Start the health check server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        # Try to start on the specified port, if fails try alternative ports
        ports_to_try = [self.port, 8081, 8082, 8083, 0]  # 0 means any available port
        last_error = None

        for port in ports_to_try:
            try:
                self.site = web.TCPSite(self.runner, self.host, port, reuse_address=True)
                await self.site.start()
                self.port = port
                logger.info("Health check server started on http://%s:%d", self.host, self.port)
                return
            except OSError as e:
                last_error = e
                if port == ports_to_try[-1]:
                    raise RuntimeError(f"Failed to start health check server on any port: {last_error}") from last_error
                logger.warning("Port %d is busy, trying next port...", port)
                continue

    async def stop(self) -> None:
        """Stop the health check server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        logger.info("Health check server stopped")

    async def health(self, request: web.Request) -> web.Response:
        """
        Basic health check endpoint.
        Returns 200 if bot is running.
        """
        return web.json_response({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
        })

    async def ready(self, request: web.Request) -> web.Response:
        """
        Readiness check endpoint.
        Returns 200 if bot is ready to handle requests.
        """
        # Could add more sophisticated checks here
        # (database connection, Telegram API reachable, etc.)
        return web.json_response({
            "status": "ready",
            "timestamp": datetime.now().isoformat(),
        })

    async def metrics(self, request: web.Request) -> web.Response:
        """
        Metrics endpoint with bot statistics.
        """
        from app.config import get_settings
        from app.utils.cache_manager import CacheManager

        settings = get_settings()

        # Gather metrics
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "bot": {
                "version": "1.0.0",  # Could be from config
                "environment": "production",
            },
        }

        # Cache statistics
        try:
            cache_manager = CacheManager(settings.DOWNLOAD_DIR / "cache")
            cache_stats = await cache_manager.get_stats()
            metrics["cache"] = cache_stats
        except Exception as e:
            logger.warning("Failed to get cache stats: %s", e)
            metrics["cache"] = {"error": str(e)}

        # Database statistics
        try:
            db_path = settings.DATABASE_PATH
            if db_path.exists():
                db_size = db_path.stat().st_size
                metrics["database"] = {
                    "size_mb": db_size / (1024 * 1024),
                    "path": str(db_path),
                }
        except Exception as e:
            logger.warning("Failed to get database stats: %s", e)
            metrics["database"] = {"error": str(e)}

        # Rate limiter statistics (if available)
        try:
            from app.media.audio.handlers.music import rate_limiter
            metrics["rate_limiter"] = rate_limiter.get_stats()
        except Exception as e:
            logger.warning("Failed to get rate limiter stats: %s", e)

        return web.json_response(metrics)


# Global instance
_health_server: HealthCheckServer | None = None


async def start_health_server(host: str = "0.0.0.0", port: int = 8080) -> HealthCheckServer:
    """Start the health check server."""
    global _health_server
    _health_server = HealthCheckServer(host, port)
    await _health_server.start()
    return _health_server


async def stop_health_server() -> None:
    """Stop the health check server."""
    global _health_server
    if _health_server:
        await _health_server.stop()
        _health_server = None
