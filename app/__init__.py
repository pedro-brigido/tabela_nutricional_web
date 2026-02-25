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

    flask_app.wsgi_app = ProxyFix(
        flask_app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )

    # Extensions
    db.init_app(flask_app)
    login_manager.init_app(flask_app)
    csrf.init_app(flask_app)
    limiter.init_app(flask_app)
    migrate.init_app(flask_app, db)

    # Import all models so Alembic can see them
    import app.models  # noqa: F401

    # Blueprints
    from app.blueprints.auth import auth_bp, init_oauth
    from app.blueprints.calculator import calculator_bp
    from app.blueprints.main import main_bp
    from app.blueprints.account import account_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.support import support_bp

    init_oauth(flask_app)
    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(main_bp)
    flask_app.register_blueprint(calculator_bp)
    flask_app.register_blueprint(account_bp)
    flask_app.register_blueprint(admin_bp)
    flask_app.register_blueprint(support_bp)

    # Security middleware
    from app.middleware import register_request_logging, register_security_headers

    register_security_headers(flask_app)
    register_request_logging(flask_app)

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
