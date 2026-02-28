"""add stripe billing fields and stripe_events table

Revision ID: c9d8f1a2b3c4
Revises: 5f47422a0b6d
Create Date: 2026-02-26 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9d8f1a2b3c4"
down_revision = "5f47422a0b6d"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("stripe_customer_id", sa.String(length=255), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_users_stripe_customer_id"),
            ["stripe_customer_id"],
            unique=True,
        )

    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("stripe_price_id", sa.String(length=255), nullable=True)
        )

    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("stripe_status", sa.String(length=30), nullable=True)
        )
        batch_op.add_column(
            sa.Column("current_period_start", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("current_period_end", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("cancel_at_period_end", sa.Boolean(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("stripe_latest_event_id", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("stripe_latest_event_at", sa.DateTime(), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_subscriptions_stripe_subscription_id"),
            ["stripe_subscription_id"],
            unique=True,
        )

    op.create_table(
        "stripe_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_summary", sa.JSON(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )
    with op.batch_alter_table("stripe_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_stripe_events_event_id"), ["event_id"], unique=True
        )


def downgrade():
    with op.batch_alter_table("stripe_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stripe_events_event_id"))
    op.drop_table("stripe_events")

    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_subscriptions_stripe_subscription_id"))
        batch_op.drop_column("stripe_latest_event_at")
        batch_op.drop_column("stripe_latest_event_id")
        batch_op.drop_column("cancel_at_period_end")
        batch_op.drop_column("current_period_end")
        batch_op.drop_column("current_period_start")
        batch_op.drop_column("stripe_status")
        batch_op.drop_column("stripe_subscription_id")

    with op.batch_alter_table("plans", schema=None) as batch_op:
        batch_op.drop_column("stripe_price_id")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_stripe_customer_id"))
        batch_op.drop_column("stripe_customer_id")
