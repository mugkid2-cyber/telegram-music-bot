"""Prometheus метрики для мониторинга бота."""
import logging
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from aiohttp import web

logger = logging.getLogger(__name__)

# Метрики скачивания музыки
downloads_total = Counter(
    'music_downloads_total',
    'Total music downloads',
    ['platform', 'status']
)

download_duration = Histogram(
    'music_download_duration_seconds',
    'Time spent downloading music',
    ['platform'],
    buckets=(1, 2, 5, 10, 20, 30, 60, 120, 300)
)

# Метрики поиска
search_duration = Histogram(
    'music_search_duration_seconds',
    'Time spent searching music',
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20)
)

search_results_count = Histogram(
    'music_search_results_count',
    'Number of search results returned',
    buckets=(0, 1, 3, 5, 10, 15, 20)
)

# Метрики кеша
cache_hits = Counter(
    'cache_hits_total',
    'Cache hit rate',
    ['cache_type']
)

cache_misses = Counter(
    'cache_misses_total',
    'Cache miss rate',
    ['cache_type']
)

cache_size = Gauge(
    'cache_size_items',
    'Current cache size in items',
    ['cache_type']
)

# Метрики активности
active_downloads = Gauge(
    'active_downloads',
    'Number of active downloads'
)

active_searches = Gauge(
    'active_searches',
    'Number of active searches'
)

# Метрики rate limiting
rate_limit_rejections = Counter(
    'rate_limit_rejections_total',
    'Rate limit rejections',
    ['user_type']
)

# Метрики команд
command_executions = Counter(
    'command_executions_total',
    'Total command executions',
    ['command', 'status']
)

# Метрики ошибок
errors_total = Counter(
    'errors_total',
    'Total errors',
    ['error_type', 'module']
)

# Метрики дней рождения
birthday_announcements = Counter(
    'birthday_announcements_total',
    'Total birthday announcements',
    ['status']
)

# Метрики TikTok
tiktok_downloads = Counter(
    'tiktok_downloads_total',
    'Total TikTok downloads',
    ['type', 'status']
)


async def metrics_handler(request: web.Request) -> web.Response:
    """Prometheus metrics endpoint."""
    return web.Response(
        body=generate_latest(),
        content_type=CONTENT_TYPE_LATEST
    )


async def start_metrics_server(host: str = "0.0.0.0", port: int = 9090):
    """Запускает Prometheus metrics сервер."""
    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info("Metrics server started on %s:%s", host, port)
    return runner


async def stop_metrics_server(runner: web.AppRunner):
    """Останавливает metrics сервер."""
    await runner.cleanup()
    logger.info("Metrics server stopped")
