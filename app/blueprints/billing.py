"""
Billing blueprint (Stripe checkout, portal, webhook).
"""

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.extensions import csrf, limiter
from app.services.stripe_service import (
    DuplicateSubscriptionError,
    create_billing_portal_session,
    create_checkout_session,
    handle_webhook_event,
    verify_webhook_signature,
)


billing_bp = Blueprint("billing", __name__)


@billing_bp.before_request
def ensure_billing_enabled():
    if not current_app.config.get("STRIPE_ENABLED", False):
        abort(404)


@billing_bp.post("/billing/checkout")
@login_required
@limiter.limit("5 per minute")
def checkout():
    plan_slug = (request.form.get("plan_slug") or "").strip()
    if not plan_slug:
        flash("Plano inválido para checkout.", "error")
        return redirect(url_for("main.pricing"))

    try:
        checkout_url = create_checkout_session(
            user=current_user,
            plan_slug=plan_slug,
            success_url=url_for("billing.success", _external=True),
            cancel_url=url_for("billing.cancel", _external=True),
        )
    except DuplicateSubscriptionError:
        flash(
            "Você já possui uma assinatura ativa neste plano. "
            "Use o portal de cobrança para gerenciar.",
            "info",
        )
        return redirect(url_for("billing.portal_redirect"))
    except Exception as exc:
        current_app.logger.exception("Falha ao criar checkout Stripe: %s", exc)
        flash(
            "Não foi possível iniciar o checkout no momento. Tente novamente.",
            "error",
        )
        return redirect(url_for("main.pricing"))
    return redirect(checkout_url)


@billing_bp.post("/billing/portal")
@login_required
def portal():
    try:
        portal_url = create_billing_portal_session(
            user=current_user,
            return_url=url_for("account.dashboard", _external=True),
        )
    except Exception as exc:
        current_app.logger.exception("Falha ao criar billing portal Stripe: %s", exc)
        flash("Não foi possível abrir o portal de cobrança agora.", "error")
        return redirect(url_for("account.dashboard"))
    return redirect(portal_url)


@billing_bp.post("/billing/webhook")
@csrf.exempt
def webhook():
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = verify_webhook_signature(payload, sig_header)
    except Exception as exc:
        current_app.logger.warning("Webhook Stripe inválido: %s", exc)
        return {"ok": False}, 400

    try:
        handle_webhook_event(event)
    except Exception:
        current_app.logger.exception(
            "Erro ao processar webhook Stripe %s", event.get("id")
        )
        return {"ok": False}, 500
    return {"ok": True}, 200


@billing_bp.get("/billing/portal-redirect")
@login_required
def portal_redirect():
    """GET-safe portal redirect for duplicate subscription handling."""
    try:
        portal_url = create_billing_portal_session(
            user=current_user,
            return_url=url_for("account.dashboard", _external=True),
        )
    except Exception as exc:
        current_app.logger.exception("Falha ao criar billing portal Stripe: %s", exc)
        flash("Não foi possível abrir o portal de cobrança agora.", "error")
        return redirect(url_for("main.pricing"))
    return redirect(portal_url)


@billing_bp.get("/billing/success")
@login_required
def success():
    session_id = request.args.get("session_id", "").strip()
    verified = False
    if session_id:
        try:
            from app.services.stripe_service import _stripe_module
            stripe = _stripe_module()
            sess = stripe.checkout.Session.retrieve(session_id)
            if sess.get("status") == "complete" and sess.get("customer") == getattr(current_user, "stripe_customer_id", None):
                verified = True
        except Exception:
            current_app.logger.debug("Could not verify checkout session %s", session_id)
    return render_template("billing/success.html", verified=verified, session_id=session_id)


@billing_bp.get("/billing/cancel")
@login_required
def cancel():
    return render_template("billing/cancel.html")
