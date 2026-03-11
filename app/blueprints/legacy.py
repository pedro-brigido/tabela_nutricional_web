"""
Legacy redirects: 301 permanent redirects from old URL structure to new /app prefix.
These ensure bookmarks, search engines, and external links continue to work.
Also preserves the Stripe webhook at its original path for backwards compatibility.
"""

from flask import Blueprint, redirect, request

from app.extensions import csrf

legacy_bp = Blueprint("legacy", __name__)


@legacy_bp.route("/account")
@legacy_bp.route("/account/<path:subpath>")
def account_redirect(subpath=""):
    """Redirect /account/* → /app/account/*"""
    qs = request.query_string.decode()
    target = f"/app/account/{subpath}" if subpath else "/app/account/"
    if qs:
        target += f"?{qs}"
    return redirect(target, code=301)


@legacy_bp.route("/api/quota")
@legacy_bp.route("/api/calculate", methods=["GET", "POST"])
@legacy_bp.route("/api/import-excel", methods=["GET", "POST"])
@legacy_bp.route("/api/tables", methods=["GET", "POST"])
@legacy_bp.route("/api/tables/<path:subpath>", methods=["GET", "POST", "DELETE"])
@legacy_bp.route("/api/allergens")
@legacy_bp.route("/api/portion-references")
@legacy_bp.route("/api/taco/search")
@legacy_bp.route("/api/tables/latest")
def api_redirect(subpath=""):
    """Redirect /api/* → /app/api/*"""
    path = request.path
    qs = request.query_string.decode()
    target = f"/app{path}"
    if qs:
        target += f"?{qs}"
    return redirect(target, code=301)


@legacy_bp.route("/billing/checkout", methods=["GET", "POST"])
@legacy_bp.route("/billing/portal", methods=["GET", "POST"])
@legacy_bp.route("/billing/portal-redirect")
@legacy_bp.route("/billing/cancel-subscription", methods=["GET", "POST"])
@legacy_bp.route("/billing/success")
@legacy_bp.route("/billing/cancel")
def billing_redirect():
    """Redirect /billing/* → /app/billing/*"""
    path = request.path
    qs = request.query_string.decode()
    target = f"/app{path}"
    if qs:
        target += f"?{qs}"
    return redirect(target, code=301)


@legacy_bp.post("/billing/webhook")
@csrf.exempt
def billing_webhook_legacy():
    """Forward Stripe webhook to the new /app/billing/webhook endpoint.

    POST redirects lose their body, so we proxy the request directly
    to the billing blueprint handler instead of redirecting.
    """
    from app.services.stripe_service import (
        handle_webhook_event,
        verify_webhook_signature,
    )
    from flask import current_app

    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = verify_webhook_signature(payload, sig_header)
    except Exception as exc:
        current_app.logger.warning("Webhook Stripe inválido (legacy): %s", exc)
        return {"ok": False}, 400

    try:
        handle_webhook_event(event)
    except Exception:
        current_app.logger.exception(
            "Erro ao processar webhook Stripe (legacy) %s", event.get("id")
        )
        return {"ok": False}, 500
    return {"ok": True}, 200
