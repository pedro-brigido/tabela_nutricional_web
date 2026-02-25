"""
Table service: create, list, get, delete, version nutrition tables.
"""

from __future__ import annotations

from app.extensions import db
from app.models.table import NutritionTable, TableVersion
from app.services.plan_service import has_entitlement
from app.services.usage_service import consume_table_quota


def create_table(
    *,
    user_id: int,
    title: str,
    product_data: dict,
    ingredients_data: list,
    result_data: dict,
    idempotency_key: str | None = None,
) -> NutritionTable | None:
    """
    Persist a finalized nutrition table and consume quota.
    Returns None if quota is exceeded.
    Uses idempotency_key to prevent double-counting on retries.
    """
    if idempotency_key:
        existing = NutritionTable.query.filter_by(
            idempotency_key=idempotency_key
        ).first()
        if existing:
            return existing

    if not consume_table_quota(user_id):
        return None

    table = NutritionTable(
        user_id=user_id,
        title=title,
        product_data=product_data,
        ingredients_data=ingredients_data,
        result_data=result_data,
        ingredient_count=len(ingredients_data),
        idempotency_key=idempotency_key,
        is_finalized=True,
    )
    db.session.add(table)
    db.session.commit()
    return table


def list_tables(user_id: int, page: int = 1, per_page: int = 20):
    """List user's tables, paginated, newest first."""
    return (
        NutritionTable.query.filter_by(user_id=user_id)
        .order_by(NutritionTable.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )


def get_table(table_id: int, user_id: int) -> NutritionTable | None:
    """Get a table by ID, ensuring it belongs to the user."""
    return NutritionTable.query.filter_by(
        id=table_id, user_id=user_id
    ).first()


def delete_table(table_id: int, user_id: int) -> bool:
    """Delete a table. Returns True if deleted."""
    table = get_table(table_id, user_id)
    if not table:
        return False
    db.session.delete(table)
    db.session.commit()
    return True


def save_version(table: NutritionTable) -> TableVersion | None:
    """Save a version snapshot (Flow Pro+ only). Returns None if not entitled."""
    if not has_entitlement(table.user_id, "has_version_history"):
        return None

    version = TableVersion(
        table_id=table.id,
        version_number=table.version,
        product_data=table.product_data,
        ingredients_data=table.ingredients_data,
        result_data=table.result_data,
    )
    db.session.add(version)
    table.version += 1
    db.session.commit()
    return version


def get_versions(table_id: int, user_id: int) -> list[TableVersion]:
    """Get version history for a table."""
    table = get_table(table_id, user_id)
    if not table:
        return []
    return (
        TableVersion.query.filter_by(table_id=table_id)
        .order_by(TableVersion.version_number.desc())
        .all()
    )
