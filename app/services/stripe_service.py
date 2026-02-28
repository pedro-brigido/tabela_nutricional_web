"""
Stripe service: checkout, billing portal, webhook verification and processing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.billing import StripeEvent
from app.models.plan import Plan, Subscription
from app.models.user import User
from app.services.audit_service import log_action
from app.services.plan_service import get_user_subscription


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_dt(ts: int | None) -> datetime | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def _require_stripe_enabled() -> None:
    if not current_app.config.get("STRIPE_ENABLED"):
        raise ValueError("Stripe billing is not enabled in this environment.")


def _stripe_module():
    try:
        import stripe
    except ImportError as exc:
        raise RuntimeError(
            "stripe dependency missing. Install dependencies before enabling billing."
        ) from exc

    stripe.api_key = current_app.config.get("STRIPE_SECRET_KEY")
    return stripe


def _plan_from_slug(plan_slug: str) -> Plan:
    plan = Plan.query.filter_by(slug=plan_slug, is_active=True).first()
    if not plan:
        raise ValueError("Plano inválido ou inativo.")
    if plan.slug == "free":
        raise ValueError("Plano Free não utiliza checkout.")
    return plan


def get_or_create_stripe_customer(user: User) -> str:
    _require_stripe_enabled()
    if user.stripe_customer_id:
        return user.stripe_customer_id

    stripe = _stripe_module()
    customer = stripe.Customer.create(
        email=user.email,
        name=user.name,
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer["id"]
    db.session.commit()
    return user.stripe_customer_id


def create_checkout_session(
    *, user: User, plan_slug: str, success_url: str, cancel_url: str
) -> str:
    _require_stripe_enabled()
    plan = _plan_from_slug(plan_slug)

    price_id = (plan.stripe_price_id or "").strip()
    if not price_id:
        raise ValueError("Plano sem price_id da Stripe configurado.")

    customer_id = get_or_create_stripe_customer(user)
    stripe = _stripe_module()

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": str(user.id), "plan_slug": plan_slug},
        subscription_data={
            "metadata": {"user_id": str(user.id), "plan_slug": plan_slug}
        },
    )
    return session["url"]


def create_billing_portal_session(*, user: User, return_url: str) -> str:
    _require_stripe_enabled()
    if not user.stripe_customer_id:
        raise ValueError(
            "Usuário ainda não tem customer Stripe. Assine um plano primeiro."
        )

    stripe = _stripe_module()
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id, return_url=return_url
    )
    return session["url"]


def verify_webhook_signature(payload: bytes, sig_header: str | None) -> dict:
    _require_stripe_enabled()
    if not sig_header:
        raise ValueError("Missing Stripe-Signature header.")
    stripe = _stripe_module()
    return stripe.Webhook.construct_event(
        payload=payload,
        sig_header=sig_header,
        secret=current_app.config["STRIPE_WEBHOOK_SECRET"],
    )


def _price_id_to_plan_slug(price_id: str | None) -> str | None:
    if not price_id:
        return None
    row = Plan.query.filter_by(stripe_price_id=price_id, is_active=True).first()
    if row:
        return row.slug
    return None


def _extract_subscription_payload(subscription: dict[str, Any]) -> dict[str, Any]:
    price_id = None
    items = (subscription.get("items") or {}).get("data") or []
    if items:
        price = items[0].get("price") or {}
        price_id = price.get("id")

    plan_slug = _price_id_to_plan_slug(price_id)
    return {
        "stripe_subscription_id": subscription.get("id"),
        "stripe_status": subscription.get("status"),
        "plan_slug": plan_slug,
        "current_period_start": _as_dt(subscription.get("current_period_start")),
        "current_period_end": _as_dt(subscription.get("current_period_end")),
        "cancel_at_period_end": bool(
            subscription.get("cancel_at_period_end", False)
        ),
        "customer_id": subscription.get("customer"),
    }


def _get_or_create_subscription_record(
    user_id: int, stripe_subscription_id: str | None
) -> Subscription:
    sub = None
    if stripe_subscription_id:
        sub = Subscription.query.filter_by(
            stripe_subscription_id=stripe_subscription_id
        ).first()
    if not sub:
        sub = get_user_subscription(user_id)
    if not sub:
        free = Plan.query.filter_by(slug="free").first()
        if not free:
            raise ValueError("Plano Free não encontrado. Rode `flask seed-plans`.")
        sub = Subscription(
            user_id=user_id, plan_id=free.id, status="cancelled", assigned_by="stripe"
        )
        db.session.add(sub)
        db.session.flush()
    return sub


def apply_subscription_state(
    *,
    user_id: int,
    plan_slug: str | None,
    stripe_status: str | None,
    stripe_subscription_id: str | None,
    current_period_start: datetime | None,
    current_period_end: datetime | None,
    cancel_at_period_end: bool,
    event_id: str,
) -> Subscription:
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError(f"Usuário {user_id} não encontrado.")

    sub = _get_or_create_subscription_record(user_id, stripe_subscription_id)
    effective_plan_slug = (
        plan_slug if plan_slug and plan_slug != "free" else "free"
    )
    plan = Plan.query.filter_by(slug=effective_plan_slug, is_active=True).first()
    if not plan:
        raise ValueError(f"Plano '{effective_plan_slug}' não encontrado.")

    # keep access during past_due grace period; canceled/incomplete revert to free
    active_like = {"active", "trialing", "past_due"}
    is_active_state = (stripe_status or "") in active_like and plan.slug != "free"

    if is_active_state:
        sub.status = "active"
        sub.plan_id = plan.id
    else:
        sub.status = "cancelled"
        free = Plan.query.filter_by(slug="free", is_active=True).first()
        if free:
            sub.plan_id = free.id

    sub.assigned_by = "stripe"
    sub.stripe_subscription_id = stripe_subscription_id
    sub.stripe_status = stripe_status
    sub.current_period_start = current_period_start
    sub.current_period_end = current_period_end
    sub.cancel_at_period_end = cancel_at_period_end
    sub.expires_at = current_period_end
    sub.stripe_latest_event_id = event_id
    sub.stripe_latest_event_at = _utcnow()
    if sub.status == "cancelled":
        sub.cancelled_at = _utcnow()

    # Ensure only one active subscription per user.
    if sub.status == "active":
        (
            Subscription.query.filter(
                Subscription.user_id == user_id,
                Subscription.id != sub.id,
                Subscription.status == "active",
            ).update({"status": "cancelled", "cancelled_at": _utcnow()})
        )

    db.session.flush()
    return sub


def _resolve_user_id(customer_id: str | None, fallback_user_id: str | None) -> int | None:
    if customer_id:
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            return user.id
    if fallback_user_id and str(fallback_user_id).isdigit():
        user = db.session.get(User, int(fallback_user_id))
        if user:
            return user.id
    return None


def _handle_checkout_completed(obj: dict[str, Any], event_id: str) -> None:
    stripe = _stripe_module()
    subscription_id = obj.get("subscription")
    customer_id = obj.get("customer")
    metadata = obj.get("metadata") or {}
    user_id = _resolve_user_id(customer_id, metadata.get("user_id"))
    if not user_id or not subscription_id:
        return

    subscription = stripe.Subscription.retrieve(subscription_id)
    parsed = _extract_subscription_payload(subscription)
    apply_subscription_state(
        user_id=user_id,
        plan_slug=parsed["plan_slug"],
        stripe_status=parsed["stripe_status"],
        stripe_subscription_id=parsed["stripe_subscription_id"],
        current_period_start=parsed["current_period_start"],
        current_period_end=parsed["current_period_end"],
        cancel_at_period_end=parsed["cancel_at_period_end"],
        event_id=event_id,
    )


def _handle_subscription_updated(obj: dict[str, Any], event_id: str) -> None:
    metadata = obj.get("metadata") or {}
    parsed = _extract_subscription_payload(obj)
    user_id = _resolve_user_id(parsed["customer_id"], metadata.get("user_id"))
    if not user_id:
        return
    apply_subscription_state(
        user_id=user_id,
        plan_slug=parsed["plan_slug"],
        stripe_status=parsed["stripe_status"],
        stripe_subscription_id=parsed["stripe_subscription_id"],
        current_period_start=parsed["current_period_start"],
        current_period_end=parsed["current_period_end"],
        cancel_at_period_end=parsed["cancel_at_period_end"],
        event_id=event_id,
    )


def _handle_subscription_deleted(obj: dict[str, Any], event_id: str) -> None:
    metadata = obj.get("metadata") or {}
    parsed = _extract_subscription_payload(obj)
    user_id = _resolve_user_id(parsed["customer_id"], metadata.get("user_id"))
    if not user_id:
        return
    apply_subscription_state(
        user_id=user_id,
        plan_slug="free",
        stripe_status="canceled",
        stripe_subscription_id=parsed["stripe_subscription_id"],
        current_period_start=parsed["current_period_start"],
        current_period_end=parsed["current_period_end"],
        cancel_at_period_end=bool(obj.get("cancel_at_period_end", False)),
        event_id=event_id,
    )


def _handle_invoice_event(obj: dict[str, Any], event_id: str) -> None:
    subscription_id = obj.get("subscription")
    customer_id = obj.get("customer")
    if not subscription_id:
        return
    stripe = _stripe_module()
    subscription = stripe.Subscription.retrieve(subscription_id)
    parsed = _extract_subscription_payload(subscription)
    user_id = _resolve_user_id(customer_id, (subscription.get("metadata") or {}).get("user_id"))
    if not user_id:
        return
    apply_subscription_state(
        user_id=user_id,
        plan_slug=parsed["plan_slug"],
        stripe_status=parsed["stripe_status"],
        stripe_subscription_id=parsed["stripe_subscription_id"],
        current_period_start=parsed["current_period_start"],
        current_period_end=parsed["current_period_end"],
        cancel_at_period_end=parsed["cancel_at_period_end"],
        event_id=event_id,
    )


def handle_webhook_event(event: dict[str, Any]) -> None:
    event_id = event["id"]
    event_type = event["type"]

    existing = StripeEvent.query.filter_by(event_id=event_id).first()
    if existing:
        return

    try:
        db.session.add(
            StripeEvent(
                event_id=event_id,
                event_type=event_type,
                payload_summary={
                    "livemode": bool(event.get("livemode")),
                    "created": event.get("created"),
                },
            )
        )
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return

    obj = event.get("data", {}).get("object", {})
    if event_type == "checkout.session.completed":
        _handle_checkout_completed(obj, event_id)
    elif event_type == "customer.subscription.updated":
        _handle_subscription_updated(obj, event_id)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(obj, event_id)
    elif event_type in {"invoice.payment_succeeded", "invoice.payment_failed"}:
        _handle_invoice_event(obj, event_id)

    db.session.commit()

    # Keep observability simple and searchable.
    log_action(
        "billing.webhook.processed",
        resource_type="stripe_event",
        details={"event_id": event_id, "event_type": event_type},
    )
