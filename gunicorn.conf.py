"""
Gunicorn runtime configuration.

Defaults are tuned for small VPS deployments and can be overridden with
GUNICORN_* environment variables.
"""

import os


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


bind = os.getenv("GUNICORN_BIND", "0.0.0.0:5000")
workers = _env_int("GUNICORN_WORKERS", 2)
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")
threads = _env_int("GUNICORN_THREADS", 4)
timeout = _env_int("GUNICORN_TIMEOUT", 120)
graceful_timeout = _env_int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _env_int("GUNICORN_KEEPALIVE", 5)
max_requests = _env_int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = _env_int("GUNICORN_MAX_REQUESTS_JITTER", 100)

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
capture_output = True
