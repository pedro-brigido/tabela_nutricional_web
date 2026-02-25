"""
Usage service: quota checking, consumption, period management.
"""

from __future__ import annotations

from datetime import datetime

import pytz

from app.extensions import db
from app.models.plan import UsageRecord
from app.services.plan_service import get_user_plan

_SP_TZ = pytz.timezone("America/Sao_Paulo")


def current_period() -> str:
    """Current billing period as YYYY-MM in America/Sao_Paulo timezone."""
    return datetime.now(_SP_TZ).strftime("%Y-%m")


def get_usage(user_id: int, period: str | None = None) -> UsageRecord:
    """Get or create the UsageRecord for a user/period."""
    if period is None:
        period = current_period()
    usage = UsageRecord.query.filter_by(
        user_id=user_id, period=period
    ).first()
    if not usage:
        usage = UsageRecord(
            user_id=user_id, period=period, tables_created=0
        )
        db.session.add(usage)
        db.session.flush()
    return usage


def can_create_table(user_id: int) -> bool:
    """Check if user has remaining table quota this month."""
    plan = get_user_plan(user_id)
    if plan.max_tables_per_month is None:
        return True
    usage = get_usage(user_id)
    return usage.tables_created < plan.max_tables_per_month


def can_use_ingredients(user_id: int, count: int) -> bool:
    """Check if ingredient count is within plan limit."""
    plan = get_user_plan(user_id)
    if plan.max_ingredients_per_table is None:
        return True
    return count <= plan.max_ingredients_per_table


def consume_table_quota(user_id: int) -> bool:
    """
    Atomically increment table usage. Returns True if successful, False if quota exceeded.
    Uses a nested transaction for atomicity (SQLite: BEGIN IMMEDIATE via flush).
    """
    plan = get_user_plan(user_id)
    period = current_period()

    with db.session.begin_nested():
        usage = UsageRecord.query.filter_by(
            user_id=user_id, period=period
        ).with_for_update().first()

        if not usage:
            usage = UsageRecord(
                user_id=user_id, period=period, tables_created=0
            )
            db.session.add(usage)
            db.session.flush()

        if (
            plan.max_tables_per_month is not None
            and usage.tables_created >= plan.max_tables_per_month
        ):
            return False

        usage.tables_created += 1

    db.session.commit()
    return True


def get_usage_summary(user_id: int) -> dict:
    """Return usage summary for the current period."""
    plan = get_user_plan(user_id)
    usage = get_usage(user_id)
    return {
        "period": usage.period,
        "tables_created": usage.tables_created,
        "tables_limit": plan.max_tables_per_month,
        "ingredients_limit": plan.max_ingredients_per_table,
        "plan_name": plan.name,
        "plan_slug": plan.slug,
    }
