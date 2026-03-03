"""
Plan service: entitlement checks, user plan retrieval.
"""

from __future__ import annotations

from app.extensions import db
from app.models.plan import Plan, Subscription
from app.plan_seed_data import PLANS_SEED


_FREE_PLAN_SLUG = "free"
_MARKETING_PLANS_SEED = PLANS_SEED


def get_user_plan(user_id: int) -> Plan:
    """Return the active Plan for a user. Falls back to Free."""
    sub = (
        Subscription.query
        .filter_by(user_id=user_id, status="active")
        .order_by(Subscription.started_at.desc())
        .first()
    )
    if sub:
        return sub.plan

    free = Plan.query.filter_by(slug=_FREE_PLAN_SLUG).first()
    if free:
        return free

    return _synthetic_free_plan()


def get_user_subscription(user_id: int) -> Subscription | None:
    return (
        Subscription.query
        .filter_by(user_id=user_id, status="active")
        .order_by(Subscription.started_at.desc())
        .first()
    )


def has_entitlement(user_id: int, feature: str) -> bool:
    """Check if user's plan grants a boolean feature (e.g. 'has_templates')."""
    plan = get_user_plan(user_id)
    return bool(getattr(plan, feature, False))


def assign_plan(
    user_id: int, plan_slug: str, assigned_by: str = "system", notes: str | None = None
) -> Subscription:
    """Create a new active subscription, deactivating the previous one."""
    plan = Plan.query.filter_by(slug=plan_slug, is_active=True).first()
    if not plan:
        raise ValueError(f"Plan '{plan_slug}' not found or inactive.")

    old_sub = get_user_subscription(user_id)
    if old_sub:
        old_sub.status = "cancelled"

    sub = Subscription(
        user_id=user_id,
        plan_id=plan.id,
        status="active",
        assigned_by=assigned_by,
        notes=notes,
    )
    db.session.add(sub)
    db.session.commit()
    return sub


def list_plans(active_only: bool = True) -> list[Plan]:
    q = Plan.query
    if active_only:
        q = q.filter_by(is_active=True)
    return q.order_by(Plan.display_order).all()


def marketing_plans() -> list[Plan]:
    """
    Return in-memory Plan objects for marketing/UI when the DB is empty
    or not initialized yet. This should not be used for entitlement checks.
    """
    return [_synthetic_plan(p) for p in _MARKETING_PLANS_SEED]


def _synthetic_plan(plan_data: dict) -> Plan:
    p = Plan()
    for k, v in plan_data.items():
        setattr(p, k, v)
    p.is_active = True
    return p


def _synthetic_free_plan() -> Plan:
    """In-memory Plan object when the DB has no plans seeded yet."""
    p = Plan()
    p.slug = "free"
    p.name = "Free"
    p.price_brl = 0
    p.max_tables_per_month = 1
    p.max_ingredients_per_table = 10
    p.has_templates = False
    p.has_pdf_export = False
    p.has_png_export = False
    p.has_version_history = False
    p.has_branding = False
    p.pulse_level = "digest"
    p.pulse_max_topics = 0
    p.pulse_has_alerts = False
    p.pulse_has_radar = False
    return p
