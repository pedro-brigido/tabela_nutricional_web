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
    """Serve landing page with full pricing section."""
    from app.services.plan_service import list_plans, marketing_plans

    bootstrap_warning = None
    bootstrap_error = None

    try:
        plans = list_plans()
    except OperationalError:
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

    current_plan = None
    try:
        from flask_login import current_user
        if current_user.is_authenticated:
            from app.services.plan_service import get_user_plan
            current_plan = get_user_plan(current_user.id)
    except Exception:
        pass

    return render_template(
        "landing/index.html",
        plans=plans,
        current_plan=current_plan,
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


@main_bp.route("/robots.txt")
def robots_txt():
    """Serve robots.txt for search engine crawlers."""
    from flask import make_response, url_for

    sitemap_url = url_for("main.sitemap_xml", _external=True)
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /app/\n"
        "Disallow: /admin/\n"
        "Disallow: /support/tickets\n"
        f"\nSitemap: {sitemap_url}\n"
    )
    resp = make_response(body, 200)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    return resp


@main_bp.route("/sitemap.xml")
def sitemap_xml():
    """Generate sitemap.xml dynamically from public routes."""
    from flask import make_response, url_for

    pages = [
        {"loc": url_for("main.index", _external=True), "priority": "1.0", "changefreq": "weekly"},
        {"loc": url_for("support.help_page", _external=True), "priority": "0.6", "changefreq": "monthly"},
        {"loc": url_for("support.contact", _external=True), "priority": "0.5", "changefreq": "monthly"},
        {"loc": url_for("main.privacy", _external=True), "priority": "0.3", "changefreq": "yearly"},
    ]

    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for p in pages:
        xml_parts.append("  <url>")
        xml_parts.append(f"    <loc>{p['loc']}</loc>")
        xml_parts.append(f"    <changefreq>{p['changefreq']}</changefreq>")
        xml_parts.append(f"    <priority>{p['priority']}</priority>")
        xml_parts.append("  </url>")
    xml_parts.append("</urlset>")

    resp = make_response("\n".join(xml_parts), 200)
    resp.headers["Content-Type"] = "application/xml; charset=utf-8"
    return resp
