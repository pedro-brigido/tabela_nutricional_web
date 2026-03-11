"""
Access-control decorators for feature gating, quota enforcement, and roles.
"""

from functools import wraps

from flask import abort, jsonify, request
from flask_login import current_user, login_required

from app.services.plan_service import get_user_plan, has_entitlement
from app.services.usage_service import can_create_table, can_use_ingredients


def require_entitlement(feature: str):
    """Abort 403 if the user's plan lacks the given boolean feature."""

    def decorator(f):
        @wraps(f)
        @login_required
        def wrapper(*args, **kwargs):
            if not has_entitlement(current_user.id, feature):
                msg = f"Seu plano não inclui essa funcionalidade ({feature})."
                if _wants_json():
                    return jsonify({"error": msg}), 403
                abort(403, description=msg)
            return f(*args, **kwargs)

        return wrapper

    return decorator


def require_quota(resource: str):
    """Abort 403 if the user has exhausted their quota for the given resource."""

    def decorator(f):
        @wraps(f)
        @login_required
        def wrapper(*args, **kwargs):
            if resource == "table":
                data = request.get_json(silent=True) or {}
                idempotency_key = data.get("idempotencyKey")
                if idempotency_key:
                    from app.models.table import NutritionTable

                    existing = NutritionTable.query.filter_by(
                        user_id=current_user.id, idempotency_key=idempotency_key
                    ).first()
                    if existing:
                        return f(*args, **kwargs)
                if not can_create_table(current_user.id):
                    msg = "Limite de tabelas atingido este mês. Faça upgrade para continuar."
                    if _wants_json():
                        return jsonify({"error": msg, "code": "QUOTA_EXCEEDED"}), 403
                    abort(403, description=msg)

            elif resource == "ingredients":
                data = request.get_json(silent=True) or {}
                ingredients = data.get("ingredients", [])
                if not can_use_ingredients(current_user.id, len(ingredients)):
                    plan = get_user_plan(current_user.id)
                    limit = plan.max_ingredients_per_table
                    msg = f"Limite de {limit} ingredientes por tabela no seu plano."
                    if _wants_json():
                        return jsonify({"error": msg, "code": "INGREDIENT_LIMIT"}), 403
                    abort(403, description=msg)

            return f(*args, **kwargs)

        return wrapper

    return decorator


def require_role(role: str):
    """Abort 403 if the user does not have the given role."""

    def decorator(f):
        @wraps(f)
        @login_required
        def wrapper(*args, **kwargs):
            if role == "admin" and not current_user.is_admin:
                if _wants_json():
                    return jsonify({"error": "Acesso restrito."}), 403
                abort(403, description="Acesso restrito a administradores.")
            return f(*args, **kwargs)

        return wrapper

    return decorator


def _wants_json() -> bool:
    return (
        request.is_json
        or request.accept_mimetypes.best == "application/json"
    )
