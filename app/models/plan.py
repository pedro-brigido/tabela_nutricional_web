"""
Plan, Subscription, and UsageRecord models.
"""

from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class Plan(db.Model):
    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    price_brl = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    stripe_price_id = db.Column(db.String(255), nullable=True)

    max_tables_per_month = db.Column(db.Integer, nullable=True)
    max_ingredients_per_table = db.Column(db.Integer, nullable=True)

    has_templates = db.Column(db.Boolean, default=False)
    has_pdf_export = db.Column(db.Boolean, default=False)
    has_png_export = db.Column(db.Boolean, default=False)
    has_version_history = db.Column(db.Boolean, default=False)
    has_branding = db.Column(db.Boolean, default=False)

    pulse_level = db.Column(db.String(30), default="none")
    pulse_max_topics = db.Column(db.Integer, default=0)
    pulse_has_alerts = db.Column(db.Boolean, default=False)
    pulse_has_radar = db.Column(db.Boolean, default=False)

    is_active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=_utcnow)

    def __repr__(self):
        return f"<Plan {self.slug}>"


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    plan_id = db.Column(
        db.Integer, db.ForeignKey("plans.id"), nullable=False
    )
    status = db.Column(db.String(20), nullable=False, default="active")
    started_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    assigned_by = db.Column(db.String(50), default="system")
    notes = db.Column(db.Text, nullable=True)
    stripe_subscription_id = db.Column(
        db.String(255), unique=True, nullable=True, index=True
    )
    stripe_status = db.Column(db.String(30), nullable=True)
    current_period_start = db.Column(db.DateTime, nullable=True)
    current_period_end = db.Column(db.DateTime, nullable=True)
    cancel_at_period_end = db.Column(db.Boolean, default=False)
    stripe_latest_event_id = db.Column(db.String(255), nullable=True)
    stripe_latest_event_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    user = db.relationship(
        "User", backref=db.backref("subscriptions", lazy="dynamic")
    )
    plan = db.relationship("Plan")

    __table_args__ = (
        db.Index("ix_sub_user_status", "user_id", "status"),
    )

    def __repr__(self):
        return f"<Subscription user={self.user_id} plan={self.plan_id} status={self.status}>"


class UsageRecord(db.Model):
    __tablename__ = "usage_records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    period = db.Column(db.String(7), nullable=False)
    tables_created = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "period", name="uq_usage_user_period"
        ),
    )

    def __repr__(self):
        return f"<UsageRecord user={self.user_id} period={self.period} tables={self.tables_created}>"
