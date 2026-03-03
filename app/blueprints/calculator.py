"""
Calculator blueprint: nutritional table calculation and Excel import.
"""

import io
import re
from pathlib import Path

from flask import Blueprint, jsonify, request
from flask_login import login_required

from app.extensions import csrf

calculator_bp = Blueprint("calculator", __name__, url_prefix="")

try:
    import openpyxl

    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


# ---- Excel helpers ----------------------------------------------------------


def _find_column(headers: list, terms: list) -> int:
    lower_headers = [str(h).lower().strip() for h in headers]
    for i, h in enumerate(lower_headers):
        for t in terms:
            if t in h:
                return i
    return -1


def _find_fat_column(headers: list) -> int:
    lower_headers = [str(h).lower().strip() for h in headers]
    for i, h in enumerate(lower_headers):
        if ("gord" in h or "lip" in h) and "sat" not in h and "trans" not in h:
            return i
    return -1


def _process_excel_data(file_bytes: bytes) -> list[dict]:
    """Parse Excel file and return list of ingredient dicts."""
    if not HAS_OPENPYXL:
        raise RuntimeError(
            "openpyxl is required for Excel import. Install with: pip install openpyxl"
        )

    wb = openpyxl.load_workbook(
        io.BytesIO(file_bytes), read_only=True, data_only=True
    )
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    if not rows or len(rows) < 2:
        raise ValueError("Arquivo vazio ou sem cabeçalho identificável.")

    headers = [str(c or "").strip() for c in rows[0]]

    map_index = {
        "name": _find_column(
            headers,
            ["nome", "ingrediente", "produto", "descrição", "descricao"],
        ),
        "quantity": _find_column(
            headers, ["qtd", "quantidade", "peso", "quant"]
        ),
        "energy": _find_column(
            headers,
            ["kcal", "energia", "calorias", "valor energético", "energ"],
        ),
        "carbs": _find_column(headers, ["carb", "carboidrato"]),
        "proteins": _find_column(
            headers, ["prot", "proteína", "proteina"]
        ),
        "totalFat": _find_fat_column(headers),
        "saturatedFat": _find_column(headers, ["sat", "saturada"]),
        "transFat": _find_column(headers, ["trans"]),
        "fiber": _find_column(headers, ["fibra"]),
        "sodium": _find_column(headers, ["sódio", "sodio", "na"]),
    }

    if map_index["name"] == -1:
        raise ValueError(
            "Não foi possível identificar a coluna de Nome do ingrediente. "
            "Verifique se o cabeçalho contém 'Nome' ou 'Ingrediente'."
        )

    def get_value(idx: int, row: tuple) -> float:
        if idx == -1 or idx >= len(row):
            return 0.0
        val = row[idx]
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val or "").replace(",", ".")
        try:
            return float(re.sub(r"[^\d.-]", "", s) or 0)
        except ValueError:
            return 0.0

    ingredients = []
    for i in range(1, len(rows)):
        row = rows[i]
        name = (
            str(row[map_index["name"]] or "").strip()
            if map_index["name"] < len(row)
            else ""
        )
        if not name:
            continue

        ingredients.append(
            {
                "id": i,
                "name": name,
                "quantity": get_value(map_index["quantity"], row),
                "nutritionalInfo": {
                    "energyKcal": get_value(map_index["energy"], row),
                    "carbs": get_value(map_index["carbs"], row),
                    "proteins": get_value(map_index["proteins"], row),
                    "totalFat": get_value(map_index["totalFat"], row),
                    "saturatedFat": get_value(
                        map_index["saturatedFat"], row
                    ),
                    "transFat": get_value(map_index["transFat"], row),
                    "fiber": get_value(map_index["fiber"], row),
                    "sodium": get_value(map_index["sodium"], row),
                },
            }
        )

    return ingredients


# ---- Routes -----------------------------------------------------------------


@calculator_bp.route("/api/quota", methods=["GET"])
@csrf.exempt
@login_required
def api_quota():
    """Return current user's quota status for the frontend."""
    from flask_login import current_user
    from app.services.usage_service import can_create_table, get_usage_summary

    summary = get_usage_summary(current_user.id)
    return jsonify(
        {
            "canCreate": can_create_table(current_user.id),
            "tablesCreated": summary["tables_created"],
            "tablesLimit": summary["tables_limit"],
            "planName": summary["plan_name"],
            "planSlug": summary["plan_slug"],
        }
    )


@calculator_bp.route("/api/tables/latest", methods=["GET"])
@csrf.exempt
@login_required
def api_latest_table():
    """Return the most recent finalized table with full data (for quota-exhausted view)."""
    from flask_login import current_user
    from app.models.table import NutritionTable

    table = (
        NutritionTable.query.filter_by(user_id=current_user.id, is_finalized=True)
        .order_by(NutritionTable.created_at.desc())
        .first()
    )
    if not table:
        return jsonify({"table": None})

    return jsonify(
        {
            "table": {
                "id": table.id,
                "title": table.title,
                "product_data": table.product_data,
                "ingredients_data": table.ingredients_data,
                "result_data": table.result_data,
                "ingredient_count": table.ingredient_count,
                "created_at": table.created_at.isoformat() if table.created_at else None,
            }
        }
    )


@calculator_bp.route("/api/calculate", methods=["POST"])
@csrf.exempt
@login_required
def api_calculate():
    """Calculate nutritional table from product and ingredients."""
    from tabela_nutricional import calculate_legacy as anvisa_calculate

    from app.services.usage_service import can_use_ingredients
    from flask_login import current_user

    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    product = data.get("product", {})
    ingredients = data.get("ingredients", [])
    portion_size = float(product.get("portionSize") or 0)

    if not ingredients:
        return jsonify({"error": "Adicione pelo menos um ingrediente."}), 400
    if portion_size <= 0:
        return (
            jsonify({"error": "Informe o tamanho da porção válido."}),
            400,
        )

    if not can_use_ingredients(current_user.id, len(ingredients)):
        from app.services.plan_service import get_user_plan

        plan = get_user_plan(current_user.id)
        return (
            jsonify(
                {
                    "error": f"Limite de {plan.max_ingredients_per_table} ingredientes no plano {plan.name}.",
                    "code": "INGREDIENT_LIMIT",
                }
            ),
            403,
        )

    try:
        result = anvisa_calculate(ingredients, portion_size)
    except Exception as e:
        return jsonify({"error": f"Erro ao calcular: {e}"}), 500

    if result is None:
        return (
            jsonify(
                {"error": "Erro ao calcular. Verifique os valores inseridos."}
            ),
            400,
        )

    # Soft quota warning — don't block preview, just inform
    from app.services.usage_service import can_create_table

    response = {"calculatedData": result}
    if not can_create_table(current_user.id):
        response["warning"] = "QUOTA_EXHAUSTED"

    return jsonify(response)


@calculator_bp.route("/api/import-excel", methods=["POST"])
@csrf.exempt
@login_required
def api_import_excel():
    """Parse Excel file and return ingredients list."""
    if not HAS_OPENPYXL:
        return (
            jsonify(
                {
                    "error": "Suporte a Excel não disponível. Instale: pip install openpyxl"
                }
            ),
            501,
        )

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Nenhum arquivo enviado."}), 400

    ext = Path(file.filename).suffix.lower()
    if ext != ".xlsx":
        return jsonify({"error": "Formato não suportado. Use .xlsx"}), 400

    try:
        data = file.read()
        ingredients = _process_excel_data(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Erro ao ler Excel: {e}"}), 500

    if not ingredients:
        return (
            jsonify({"error": "Nenhum ingrediente válido encontrado."}),
            400,
        )

    return jsonify({"ingredients": ingredients})


# ---- Table CRUD -------------------------------------------------------------


@calculator_bp.route("/api/tables", methods=["POST"])
@login_required
def api_save_table():
    """Save a finalized nutrition table and consume quota."""
    from flask_login import current_user
    from app.services.table_service import create_table

    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados inválidos."}), 400

    title = (data.get("title") or "").strip()[:255]
    if not title:
        title = "Tabela sem título"

    product_data = data.get("product", {})
    ingredients_data = data.get("ingredients", [])
    result_data = data.get("calculatedData", {})
    idempotency_key = data.get("idempotencyKey")

    if not result_data:
        return jsonify({"error": "Dados de resultado ausentes."}), 400

    table = create_table(
        user_id=current_user.id,
        title=title,
        product_data=product_data,
        ingredients_data=ingredients_data,
        result_data=result_data,
        idempotency_key=idempotency_key,
    )

    if table is None:
        return (
            jsonify(
                {
                    "error": "Limite de tabelas atingido este mês. Faça upgrade para continuar.",
                    "code": "QUOTA_EXCEEDED",
                }
            ),
            403,
        )

    return jsonify({"id": table.id, "title": table.title}), 201


@calculator_bp.route("/api/tables", methods=["GET"])
@csrf.exempt
@login_required
def api_list_tables():
    """List the current user's saved tables."""
    from flask_login import current_user
    from app.services.table_service import list_tables

    page = request.args.get("page", 1, type=int)
    pagination = list_tables(current_user.id, page=page)

    return jsonify(
        {
            "tables": [
                {
                    "id": t.id,
                    "title": t.title,
                    "ingredient_count": t.ingredient_count,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in pagination.items
            ],
            "total": pagination.total,
            "page": pagination.page,
            "pages": pagination.pages,
        }
    )


@calculator_bp.route("/api/tables/<int:table_id>", methods=["GET"])
@csrf.exempt
@login_required
def api_get_table(table_id):
    """Get a single table by ID."""
    from flask_login import current_user
    from app.services.table_service import get_table

    table = get_table(table_id, current_user.id)
    if not table:
        return jsonify({"error": "Tabela não encontrada."}), 404

    return jsonify(
        {
            "id": table.id,
            "title": table.title,
            "product_data": table.product_data,
            "ingredients_data": table.ingredients_data,
            "result_data": table.result_data,
            "ingredient_count": table.ingredient_count,
            "version": table.version,
            "created_at": table.created_at.isoformat() if table.created_at else None,
        }
    )


@calculator_bp.route("/api/tables/<int:table_id>", methods=["DELETE"])
@login_required
def api_delete_table(table_id):
    """Delete a table."""
    from flask_login import current_user
    from app.services.table_service import delete_table

    if delete_table(table_id, current_user.id):
        return jsonify({"ok": True})
    return jsonify({"error": "Tabela não encontrada."}), 404
