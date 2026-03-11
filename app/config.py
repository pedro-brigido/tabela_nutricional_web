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
    _TRUE_VALUES = {"1", "true", "yes", "sim", "on"}

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

    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
    _chatbot_enabled_raw = os.environ.get("CHATBOT_ENABLED")
    if _chatbot_enabled_raw is None or not _chatbot_enabled_raw.strip():
        CHATBOT_ENABLED = bool(OPENAI_API_KEY)
    else:
        CHATBOT_ENABLED = _chatbot_enabled_raw.strip().lower() in _TRUE_VALUES
    CHATBOT_MODEL = os.environ.get("CHATBOT_MODEL", "gpt-4o-mini").strip()
    CHATBOT_FALLBACK_MODEL = os.environ.get(
        "CHATBOT_FALLBACK_MODEL", "gpt-5-mini"
    ).strip()
    CHATBOT_EMBEDDING_MODEL = os.environ.get(
        "CHATBOT_EMBEDDING_MODEL", "text-embedding-3-small"
    ).strip()
    CHATBOT_MODERATION_MODEL = os.environ.get(
        "CHATBOT_MODERATION_MODEL", "omni-moderation-latest"
    ).strip()
    CHATBOT_COOKIE_NAME = os.environ.get(
        "CHATBOT_COOKIE_NAME", "terracota_chat_anon"
    ).strip()
    CHATBOT_ANON_RETENTION_DAYS = int(
        os.environ.get("CHATBOT_ANON_RETENTION_DAYS", "30")
    )
    CHATBOT_AUTH_RETENTION_DAYS = int(
        os.environ.get("CHATBOT_AUTH_RETENTION_DAYS", "180")
    )
    CHATBOT_MAX_TURNS_BEFORE_SUMMARY = int(
        os.environ.get("CHATBOT_MAX_TURNS_BEFORE_SUMMARY", "6")
    )
    CHATBOT_OPENAI_TIMEOUT_SECONDS = int(
        os.environ.get("CHATBOT_OPENAI_TIMEOUT_SECONDS", "20")
    )
    CHATBOT_OPENAI_COOLDOWN_SECONDS = int(
        os.environ.get("CHATBOT_OPENAI_COOLDOWN_SECONDS", "180")
    )


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
