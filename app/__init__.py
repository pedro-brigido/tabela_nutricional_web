"""
Terracota | Calculadora Nutricional
Application factory.
"""

import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent

# Load .env before anything reads os.environ (config classes use it at import time)
_env_file = _root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(_env_file)

# Ensure src/ is on sys.path so `import tabela_nutricional` works
_src = str(_root / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


def create_app(config_name: str | None = None) -> "Flask":
    from flask import Flask
    from werkzeug.middleware.proxy_fix import ProxyFix

    from app.config import config_map
    from app.extensions import csrf, db, limiter, login_manager, migrate

    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "production")

    flask_app = Flask(
        __name__,
        template_folder=str(_root / "templates"),
        static_folder=str(_root / "static"),
        static_url_path="/static",
    )
    flask_app.config.from_object(config_map[config_name])
    flask_app.config["STRIPE_PRICE_MAP"] = {
        "flow_start": flask_app.config.get("STRIPE_PRICE_ID_FLOW_START", ""),
        "flow_pro": flask_app.config.get("STRIPE_PRICE_ID_FLOW_PRO", ""),
        "flow_studio": flask_app.config.get("STRIPE_PRICE_ID_FLOW_STUDIO", ""),
    }
    flask_app.config["STRIPE_ENABLED"] = bool(
        flask_app.config.get("STRIPE_SECRET_KEY")
        and flask_app.config.get("STRIPE_WEBHOOK_SECRET")
    )

    flask_app.wsgi_app = ProxyFix(
        flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )

    # Extensions
    db.init_app(flask_app)
    login_manager.init_app(flask_app)
    csrf.init_app(flask_app)
    limiter.init_app(flask_app)
    migrate.init_app(flask_app, db)

    # Enable SQLite WAL mode for better concurrency with multiple workers
    if "sqlite" in flask_app.config.get("SQLALCHEMY_DATABASE_URI", ""):
        from sqlalchemy import event

        with flask_app.app_context():
            @event.listens_for(db.engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

    # Import all models so Alembic can see them
    import app.models  # noqa: F401

    # Blueprints
    from app.blueprints.auth import auth_bp, init_oauth
    from app.blueprints.calculator import calculator_bp
    from app.blueprints.main import main_bp
    from app.blueprints.account import account_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.support import support_bp
    from app.blueprints.billing import billing_bp
    from app.blueprints.product import product_bp
    from app.blueprints.legacy import legacy_bp
    from app.blueprints.ai_support import ai_support_bp

    init_oauth(flask_app)

    # Diagnostic: confirm Google OAuth credentials are loaded
    import logging as _logging

    _startup_logger = _logging.getLogger(__name__)
    if flask_app.config.get("GOOGLE_CLIENT_ID") and flask_app.config.get(
        "GOOGLE_CLIENT_SECRET"
    ):
        _startup_logger.info("Google OAuth credentials loaded successfully.")
    else:
        _startup_logger.warning(
            "Google OAuth credentials are MISSING – "
            "Google login will be unavailable. "
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env"
        )

    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(main_bp)
    flask_app.register_blueprint(calculator_bp)
    flask_app.register_blueprint(account_bp)
    flask_app.register_blueprint(admin_bp)
    flask_app.register_blueprint(support_bp)
    flask_app.register_blueprint(billing_bp)
    flask_app.register_blueprint(product_bp)
    flask_app.register_blueprint(legacy_bp)
    flask_app.register_blueprint(ai_support_bp)

    @flask_app.context_processor
    def inject_billing_flags():
        return {"stripe_enabled": flask_app.config.get("STRIPE_ENABLED", False)}

    @flask_app.context_processor
    def inject_chatbot_flags():
        return {"chatbot_enabled": flask_app.config.get("CHATBOT_ENABLED", False)}

    @flask_app.context_processor
    def inject_usage_context():
        from flask_login import current_user

        if current_user.is_authenticated:
            from app.services.usage_service import get_usage_summary

            return {"app_usage": get_usage_summary(current_user.id)}
        return {"app_usage": None}

    # Security middleware
    from app.middleware import register_request_logging, register_security_headers

    register_security_headers(flask_app)
    register_request_logging(flask_app)

    with flask_app.app_context():
        from app.services.chatbot_service import ensure_chatbot_storage

        ensure_chatbot_storage()

    # Error handlers
    from app.errors import register_error_handlers

    register_error_handlers(flask_app)

    # CLI commands
    from app.cli import register_cli

    register_cli(flask_app)

    # Login manager callbacks
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import jsonify, redirect, request, url_for

        if (
            request.is_json
            or request.accept_mimetypes.best == "application/json"
        ):
            return jsonify({"error": "Não autorizado. Faça login."}), 401
        return redirect(url_for("auth.login", next=request.url))

    return flask_app
