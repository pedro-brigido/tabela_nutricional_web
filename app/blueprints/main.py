"""
Main blueprint: landing page, health check, newsletter subscription.
"""

import re
import sqlite3
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, render_template, request
from sqlalchemy.exc import OperationalError

from app.extensions import csrf
from app.services.email_service import send_newsletter_notification

main_bp = Blueprint("main", __name__, url_prefix="")


def _get_subscribers_db() -> sqlite3.Connection:
    db_path = current_app.config["SUBSCRIBERS_DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS subscribers ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  email TEXT UNIQUE NOT NULL,"
        "  subscribed_at TEXT NOT NULL,"
        "  ip TEXT"
        ")"
    )
    conn.commit()
    return conn


@main_bp.route("/")
def index():
    """Serve main application page."""
    return render_template("index.html")


@main_bp.route("/pricing")
def pricing():
    """Pricing page with plan comparison."""
    from app.services.plan_service import list_plans, marketing_plans

    bootstrap_warning = None
    bootstrap_error = None

    try:
        plans = list_plans()
    except OperationalError:
        # Most common: migrations not applied yet (no such table: plans)
        plans = marketing_plans()
        bootstrap_error = (
            "Banco ainda não inicializado. Rode `flask db upgrade` e `flask seed-plans` "
            "para persistir os planos."
        )
    except Exception:
        plans = marketing_plans()
        bootstrap_error = (
            "Não foi possível carregar os planos do banco agora. "
            "Exibindo os planos padrão."
        )
    else:
        if not plans:
            plans = marketing_plans()
            bootstrap_warning = (
                "Planos ainda não foram carregados no banco. "
                "Rode `flask seed-plans` para persistir."
            )

    return render_template(
        "main/pricing.html",
        plans=plans,
        bootstrap_warning=bootstrap_warning,
        bootstrap_error=bootstrap_error,
    )


@main_bp.route("/privacy")
def privacy():
    """Privacy policy (LGPD)."""
    return render_template("main/privacy.html")


@main_bp.route("/health")
def health():
    """Health check endpoint for Docker — includes DB connectivity test."""
    from app.extensions import db

    try:
        db.session.execute(db.text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    status = "ok" if db_ok else "degraded"
    code = 200 if db_ok else 503
    return jsonify({"status": status, "db": "ok" if db_ok else "error"}), code


@main_bp.route("/api/subscribe", methods=["POST"])
@csrf.exempt
def api_subscribe():
    """Save newsletter email to SQLite."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"error": "E-mail inválido."}), 400

    try:
        conn = _get_subscribers_db()
        conn.execute(
            "INSERT OR IGNORE INTO subscribers (email, subscribed_at, ip) VALUES (?, ?, ?)",
            (
                email,
                datetime.now(timezone.utc).isoformat(),
                request.remote_addr,
            ),
        )
        conn.commit()
        conn.close()

        send_newsletter_notification(
            subscriber_email=email,
            notify_email=current_app.config["NEWSLETTER_NOTIFY_EMAIL"],
        )
    except Exception as e:
        return jsonify({"error": f"Erro ao salvar: {e}"}), 500

    return jsonify({"ok": True, "message": "E-mail cadastrado com sucesso!"})
