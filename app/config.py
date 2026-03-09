"""
Configuration classes per environment.
"""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 30},
        "pool_pre_ping": True,
    }

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip('"').strip("'")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip('"').strip("'")
    NEWSLETTER_NOTIFY_EMAIL = os.environ.get(
        "NEWSLETTER_NOTIFY_EMAIL", "comercial@terracotabpo.com"
    )
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    STRIPE_PUBLISHABLE_KEY = os.environ.get(
        "STRIPE_PUBLISHABLE_KEY", ""
    ).strip()
    STRIPE_WEBHOOK_SECRET = os.environ.get(
        "STRIPE_WEBHOOK_SECRET", ""
    ).strip()
    STRIPE_PRICE_ID_FLOW_START = os.environ.get(
        "STRIPE_PRICE_ID_FLOW_START", ""
    ).strip()
    STRIPE_PRICE_ID_FLOW_PRO = os.environ.get(
        "STRIPE_PRICE_ID_FLOW_PRO", ""
    ).strip()
    STRIPE_PRICE_ID_FLOW_STUDIO = os.environ.get(
        "STRIPE_PRICE_ID_FLOW_STUDIO", ""
    ).strip()

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_DEFAULT = "200/hour"

    SUBSCRIBERS_DB_PATH = str(DATA_DIR / "subscribers.db")

    # AI Chat (OpenAI)
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    CHAT_MAX_HISTORY = int(os.environ.get("CHAT_MAX_HISTORY", "20"))
    CHAT_MAX_TOKENS = int(os.environ.get("CHAT_MAX_TOKENS", "500"))
    CHAT_SESSION_TTL_HOURS = int(os.environ.get("CHAT_SESSION_TTL_HOURS", "24"))
    CHAT_TEMPERATURE = float(os.environ.get("CHAT_TEMPERATURE", "0.3"))


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SERVER_NAME = "localhost"
    SUBSCRIBERS_DB_PATH = ":memory:"


class ProductionConfig(BaseConfig):
    SESSION_COOKIE_SECURE = True


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
