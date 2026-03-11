"""
Billing-related models (Stripe webhook idempotency).
"""

from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class StripeEvent(db.Model):
    __tablename__ = "stripe_events"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(
        db.String(255), unique=True, nullable=False, index=True
    )
    event_type = db.Column(db.String(100), nullable=False)
    payload_summary = db.Column(db.JSON, nullable=True)
    processed_at = db.Column(db.DateTime, default=_utcnow, nullable=False)

    def __repr__(self):
        return f"<StripeEvent {self.event_type} {self.event_id}>"
