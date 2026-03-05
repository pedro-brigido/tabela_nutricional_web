"""
Calculator blueprint: nutritional table calculation and Excel import.
"""

import io
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import Blueprint, jsonify, request
from flask_login import login_required

from app.extensions import csrf, limiter
from app.decorators import require_quota

calculator_bp = Blueprint("calculator", __name__, url_prefix="")
MAX_EXCEL_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_EXCEL_ROWS = 500

_NUTRIENT_FIELDS = (
    "energyKcal",
    "carbs",
    "proteins",
    "totalFat",
    "saturatedFat",
    "transFat",
    "fiber",
    "sodium",
    "totalSugars",
    "addedSugars",
)

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
        if ("gord" in h or "lip" in h or "fat" in h or "total fat" in h) and "sat" not in h and "trans" not in h:
            return i
    return -1


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _is_non_negative_number(value) -> bool:
    return _to_decimal(value) >= 0


def _validate_ingredient(data: dict, index: int) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, f"Ingrediente #{index + 1} inválido."
    name = (data.get("name") or "").strip()
    if not name:
        return False, f"Ingrediente #{index + 1}: nome é obrigatório."
    quantity = _to_decimal(data.get("quantity"))
    if quantity <= 0:
        return False, f"Ingrediente #{index + 1}: quantidade deve ser maior que zero."
    nutritional_info = data.get("nutritionalInfo")
    if not isinstance(nutritional_info, dict):
        return False, f"Ingrediente #{index + 1}: dados nutricionais inválidos."
    for field in _NUTRIENT_FIELDS:
        if not _is_non_negative_number(nutritional_info.get(field, 0)):
            return False, (
                f"Ingrediente #{index + 1}: o campo {field} não pode ser negativo."
            )
    return True, ""


def _has_valid_result_data(result_data: dict) -> bool:
    if not isinstance(result_data, dict):
        return False
    return isinstance(result_data.get("perPortion"), dict) and isinstance(
        result_data.get("per100g"), dict
    )


def _process_excel_data(file_bytes: bytes) -> tuple[list[dict], bool]:
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
            ["nome", "ingrediente", "produto", "descrição", "descricao",
             "name", "ingredient", "product", "description"],
        ),
        "quantity": _find_column(
            headers, ["qtd", "quantidade", "peso", "quant",
                       "quantity", "weight", "amount"]
        ),
        "energy": _find_column(
            headers,
            ["kcal", "energia", "calorias", "valor energético", "energ",
             "energy", "calories", "cal"],
        ),
        "carbs": _find_column(headers, ["carb", "carboidrato",
                                         "carbohydrate", "carbohydr"]),
        "proteins": _find_column(
            headers, ["prot", "proteína", "proteina",
                       "protein"]
        ),
        "totalFat": _find_fat_column(headers),
        "saturatedFat": _find_column(headers, ["sat", "saturada",
                                                "saturated"]),
        "transFat": _find_column(headers, ["trans"]),
        "fiber": _find_column(headers, ["fibra", "fiber", "fibre"]),
        "sodium": _find_column(headers, ["sódio", "sodio", "na",
                                          "sodium"]),
        "totalSugars": _find_column(headers, ["açúcar", "acucar", "sugar",
                                               "total sugar"]),
        "addedSugars": _find_column(
            headers,
            ["adicionado", "adicionad", "add sugar", "açúcar adicionado",
             "acucar adicionado", "added sugar"],
        ),
    }

    if map_index["name"] == -1:
        detected = [h for h in headers if h.strip()]
        raise ValueError(
            "Não foi possível identificar a coluna de Nome do ingrediente. "
            "Verifique se o cabeçalho contém 'Nome', 'Ingrediente' ou 'Name'. "
            f"Colunas detectadas: {', '.join(detected[:10])}."
        )

    parse_warnings = []

    def get_value(idx: int, row: tuple, row_num: int = 0, col_name: str = "") -> float:
        if idx == -1 or idx >= len(row):
            return 0.0
        val = row[idx]
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val or "").strip()
        if not s:
            return 0.0
        # Handle Brazilian format: "1.234,56" → "1234.56"
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        try:
            cleaned = re.sub(r"[^\d.\-]", "", s)
            result = float(cleaned) if cleaned else 0.0
            if result < 0:
                parse_warnings.append(
                    f"Linha {row_num}, coluna '{col_name}': valor negativo ({val})."
                )
            return result
        except ValueError:
            parse_warnings.append(
                f"Linha {row_num}, coluna '{col_name}': valor não numérico ({val})."
            )
            return 0.0

    ingredients = []
    truncated = False
    for i in range(1, len(rows)):
        if len(ingredients) >= MAX_EXCEL_ROWS:
            truncated = True
            break
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
                "quantity": get_value(map_index["quantity"], row, i, "quantidade"),
                "nutritionalInfo": {
                    "energyKcal": get_value(map_index["energy"], row, i, "energia"),
                    "carbs": get_value(map_index["carbs"], row, i, "carboidratos"),
                    "proteins": get_value(map_index["proteins"], row, i, "proteínas"),
                    "totalFat": get_value(map_index["totalFat"], row, i, "gordura total"),
                    "saturatedFat": get_value(
                        map_index["saturatedFat"], row, i, "gordura saturada"
                    ),
                    "transFat": get_value(map_index["transFat"], row, i, "gordura trans"),
                    "fiber": get_value(map_index["fiber"], row, i, "fibra"),
                    "sodium": get_value(map_index["sodium"], row, i, "sódio"),
                    "totalSugars": get_value(map_index["totalSugars"], row, i, "açúcares totais"),
                    "addedSugars": get_value(map_index["addedSugars"], row, i, "açúcares adicionados"),
                },
            }
        )

    return ingredients, truncated, parse_warnings


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
@limiter.limit("30/minute")
@require_quota("ingredients")
def api_calculate():
    """Calculate nutritional table from product and ingredients."""
    from tabela_nutricional import calculate as anvisa_calculate
    from tabela_nutricional import to_legacy_output

    from flask_login import current_user

    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    product = data.get("product", {}) if isinstance(data.get("product"), dict) else {}
    ingredients = data.get("ingredients", [])
    if not isinstance(ingredients, list):
        return jsonify({"error": "Lista de ingredientes inválida."}), 400

    try:
        portion_size = Decimal(str(product.get("portionSize") or 0))
    except (InvalidOperation, ValueError, TypeError):
        return jsonify({"error": "Informe o tamanho da porção válido."}), 400

    if not ingredients:
        return jsonify({"error": "Adicione pelo menos um ingrediente."}), 400
    if portion_size <= 0:
        return (
            jsonify({"error": "Informe o tamanho da porção válido."}),
            400,
        )

    for idx, ingredient in enumerate(ingredients):
        valid, err = _validate_ingredient(ingredient, idx)
        if not valid:
            return jsonify({"error": err}), 400

    food_form = product.get("foodForm", "solid")
    portion_unit = product.get("portionUnit", "ml" if food_form == "liquid" else "g")
    unit_base = "100ml" if food_form == "liquid" else "100g"

    # Portion validation against ANVISA reference (Anexo V)
    group_code = product.get("groupCode") or None
    from tabela_nutricional.portion_reference import validate_portion_size

    portion_check = validate_portion_size(portion_size, group_code)

    try:
        result_obj = anvisa_calculate(
            ingredients,
            portion_size,
            food_form=food_form,
            unit_base=unit_base,
            portion_unit=portion_unit,
        )
    except Exception as e:
        return jsonify({"error": f"Erro ao calcular: {e}"}), 500

    if result_obj is None:
        return (
            jsonify(
                {"error": "Erro ao calcular. Verifique os valores inseridos."}
            ),
            400,
        )
    result = to_legacy_output(result_obj)

    # Soft quota warning — don't block preview, just inform
    from app.services.usage_service import can_create_table

    response = {"calculatedData": result}
    if not can_create_table(current_user.id):
        response["warning"] = "QUOTA_EXHAUSTED"

    # Forward calculation warnings to frontend
    calc_warnings = list(result.get("meta", {}).get("warnings", []))
    if portion_check.get("warning"):
        calc_warnings.append(portion_check["warning"])
    if calc_warnings:
        response["calculationWarnings"] = calc_warnings

    return jsonify(response)


@calculator_bp.route("/api/import-excel", methods=["POST"])
@csrf.exempt
@login_required
@limiter.limit("20/minute")
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
        if len(data) > MAX_EXCEL_FILE_SIZE:
            return (
                jsonify(
                    {
                        "error": "Arquivo muito grande. O limite é 5MB para importação."
                    }
                ),
                400,
            )
        ingredients, truncated, parse_warnings = _process_excel_data(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Erro ao ler Excel: {e}"}), 500

    if not ingredients:
        return (
            jsonify({"error": "Nenhum ingrediente válido encontrado."}),
            400,
        )

    response = {"ingredients": ingredients}
    warnings = []
    if truncated:
        warnings.append(
            f"Importação limitada às primeiras {MAX_EXCEL_ROWS} linhas válidas."
        )
    if parse_warnings:
        warnings.extend(parse_warnings[:20])  # limit warnings
    if warnings:
        response["warnings"] = warnings
    return jsonify(response)


# ---- Table CRUD -------------------------------------------------------------


@calculator_bp.route("/api/tables", methods=["POST"])
@login_required
@require_quota("table")
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

    if not _has_valid_result_data(result_data):
        return jsonify({"error": "Dados de resultado inválidos."}), 400

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
    search = request.args.get("search", None, type=str)
    pagination = list_tables(current_user.id, page=page, search=search)

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


# ---- Reference data endpoints -----------------------------------------------


@calculator_bp.route("/api/allergens", methods=["GET"])
@csrf.exempt
@login_required
def api_allergens():
    """Return list of valid allergens for UI checklist."""
    from tabela_nutricional.allergens import ALLERGEN_REGISTRY, GLUTEN_LABELS

    allergens = [
        {"key": key, "label": label, "group": group}
        for key, label, group in ALLERGEN_REGISTRY
    ]
    return jsonify({
        "allergens": allergens,
        "glutenOptions": [
            {"key": k, "label": v} for k, v in GLUTEN_LABELS.items()
        ],
    })


@calculator_bp.route("/api/portion-references", methods=["GET"])
@csrf.exempt
@login_required
def api_portion_references():
    """Return portion reference groups for UI dropdown."""
    from tabela_nutricional.portion_reference import list_portion_groups

    return jsonify({"groups": list_portion_groups()})


@calculator_bp.route("/api/taco/search", methods=["GET"])
@csrf.exempt
@login_required
def api_taco_search():
    """Search TACO food composition database by name."""
    from tabela_nutricional.taco import search as taco_search

    query = request.args.get("q", "").strip()
    try:
        limit = min(int(request.args.get("limit", 10)), 20)
    except (ValueError, TypeError):
        limit = 10

    results = taco_search(query, limit=limit)
    return jsonify({"results": results})
