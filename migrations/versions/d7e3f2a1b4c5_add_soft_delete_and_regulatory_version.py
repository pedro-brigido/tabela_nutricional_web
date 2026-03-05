"""add soft delete and regulatory version to nutrition_tables

Revision ID: d7e3f2a1b4c5
Revises: c9d8f1a2b3c4
Create Date: 2025-01-01 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d7e3f2a1b4c5"
down_revision = "c9d8f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("nutrition_tables", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "regulatory_version",
                sa.String(length=64),
                nullable=True,
                server_default="IN_75_2020_RDC_429_2020_v1",
            )
        )
        batch_op.add_column(
            sa.Column("is_deleted", sa.Boolean(), nullable=True, server_default="0")
        )
        batch_op.add_column(
            sa.Column("deleted_at", sa.DateTime(), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_nutrition_tables_is_deleted"),
            ["is_deleted"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("nutrition_tables", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_nutrition_tables_is_deleted"))
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("is_deleted")
        batch_op.drop_column("regulatory_version")
