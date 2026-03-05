"""
Table service: create, list, get, delete, version nutrition tables.
Includes soft-delete, audit logging, product data validation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.models.table import NutritionTable, TableVersion
from app.services.plan_service import has_entitlement
from app.services.usage_service import consume_table_quota

# Allowed top-level keys in product_data (whitelist)
_PRODUCT_DATA_ALLOWED_KEYS = frozenset({
    "name", "portionSize", "portionUnit", "foodForm", "unitBase",
    "foodCategory", "description", "allergens", "allergenKeys",
    "customAllergens", "glutenStatus", "groupCode",
    "gluten", "portionDesc",
})


def _sanitize_product_data(data: dict) -> dict:
    """Whitelist allowed keys in product_data."""
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k in _PRODUCT_DATA_ALLOWED_KEYS}


def _log_audit(action: str, user_id: int, table_id: int, details: dict | None = None) -> None:
    """Log table operation to audit trail (best-effort)."""
    try:
        from app.services.audit_service import log_action
        log_action(
            action,
            user_id=user_id,
            resource_type="nutrition_table",
            resource_id=table_id,
            details=details,
        )
    except Exception:
        pass  # Audit failure should not block main operation


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

    sanitized_product = _sanitize_product_data(product_data)

    table = NutritionTable(
        user_id=user_id,
        title=title,
        product_data=sanitized_product,
        ingredients_data=ingredients_data,
        result_data=result_data,
        ingredient_count=len(ingredients_data),
        idempotency_key=idempotency_key,
        is_finalized=True,
        regulatory_version="IN_75_2020_RDC_429_2020_v1",
    )
    db.session.add(table)
    db.session.commit()
    save_version(table)
    _log_audit("table_created", user_id, table.id, {"title": title})
    return table


def list_tables(user_id: int, page: int = 1, per_page: int = 20, search: str | None = None):
    """List user's active (not soft-deleted) tables, paginated, newest first."""
    query = NutritionTable.query.filter_by(user_id=user_id, is_deleted=False)
    if search and search.strip():
        query = query.filter(NutritionTable.title.ilike(f"%{search.strip()}%"))
    return (
        query
        .order_by(NutritionTable.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )


def get_table(table_id: int, user_id: int) -> NutritionTable | None:
    """Get a table by ID, ensuring it belongs to the user and is not soft-deleted."""
    return NutritionTable.query.filter_by(
        id=table_id, user_id=user_id, is_deleted=False
    ).first()


def delete_table(table_id: int, user_id: int) -> bool:
    """Soft-delete a table. Returns True if deleted."""
    table = get_table(table_id, user_id)
    if not table:
        return False
    table.is_deleted = True
    table.deleted_at = datetime.now(timezone.utc)
    db.session.commit()
    _log_audit("table_deleted", user_id, table_id)
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
