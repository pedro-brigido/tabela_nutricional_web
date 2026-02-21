"""
Terracota | Calculadora Nutricional
Flask web application - Python translation of the original JS codebase.
"""

import io
import re
import sys
from pathlib import Path

# Allow importing tabela_nutricional from repo root without installing the package
_root = Path(__file__).resolve().parent
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))

from flask import Flask, jsonify, render_template, request

from tabela_nutricional import calculate_legacy as anvisa_calculate

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


def _find_column(headers: list, terms: list) -> int:
    """Find column index by header terms (case-insensitive)."""
    lower_headers = [str(h).lower().strip() for h in headers]
    for i, h in enumerate(lower_headers):
        for t in terms:
            if t in h:
                return i
    return -1


def _find_fat_column(headers: list) -> int:
    """Find total fat column (gord/lip but not sat/trans)."""
    lower_headers = [str(h).lower().strip() for h in headers]
    for i, h in enumerate(lower_headers):
        if ("gord" in h or "lip" in h) and "sat" not in h and "trans" not in h:
            return i
    return -1


def process_excel_data(file_bytes: bytes) -> list[dict]:
    """
    Parse Excel file and return list of ingredient dicts.
    Maps columns by common header names (nome, qtd, kcal, carb, etc.).
    """
    if not HAS_OPENPYXL:
        raise RuntimeError("openpyxl is required for Excel import. Install with: pip install openpyxl")

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    if not rows or len(rows) < 2:
        raise ValueError("Arquivo vazio ou sem cabeçalho identificável.")

    headers = [str(c or "").strip() for c in rows[0]]

    map_index = {
        "name": _find_column(headers, ["nome", "ingrediente", "produto", "descrição", "descricao"]),
        "quantity": _find_column(headers, ["qtd", "quantidade", "peso", "quant"]),
        "energy": _find_column(headers, ["kcal", "energia", "calorias", "valor energético", "energ"]),
        "carbs": _find_column(headers, ["carb", "carboidrato"]),
        "proteins": _find_column(headers, ["prot", "proteína", "proteina"]),
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
        if idx == -1:
            return 0.0
        if idx >= len(row):
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
        name = str(row[map_index["name"]] or "").strip() if map_index["name"] < len(row) else ""
        if not name:
            continue

        ingredients.append({
            "id": i,
            "name": name,
            "quantity": get_value(map_index["quantity"], row),
            "nutritionalInfo": {
                "energyKcal": get_value(map_index["energy"], row),
                "carbs": get_value(map_index["carbs"], row),
                "proteins": get_value(map_index["proteins"], row),
                "totalFat": get_value(map_index["totalFat"], row),
                "saturatedFat": get_value(map_index["saturatedFat"], row),
                "transFat": get_value(map_index["transFat"], row),
                "fiber": get_value(map_index["fiber"], row),
                "sodium": get_value(map_index["sodium"], row),
            },
        })

    return ingredients


@app.route("/")
def index():
    """Serve main application page."""
    return render_template("index.html")


@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    """Calculate nutritional table from product and ingredients."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    product = data.get("product", {})
    ingredients = data.get("ingredients", [])
    portion_size = float(product.get("portionSize") or 0)

    if not ingredients:
        return jsonify({"error": "Adicione pelo menos um ingrediente."}), 400
    if portion_size <= 0:
        return jsonify({"error": "Informe o tamanho da porção válido."}), 400

    try:
        result = anvisa_calculate(ingredients, portion_size)
    except Exception as e:
        return jsonify({"error": f"Erro ao calcular: {e}"}), 500

    if result is None:
        return jsonify({"error": "Erro ao calcular. Verifique os valores inseridos."}), 400

    return jsonify({"calculatedData": result})


@app.route("/api/import-excel", methods=["POST"])
def api_import_excel():
    """Parse Excel file and return ingredients list."""
    if not HAS_OPENPYXL:
        return jsonify({"error": "Suporte a Excel não disponível. Instale: pip install openpyxl"}), 501

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "Nenhum arquivo enviado."}), 400

    ext = Path(file.filename).suffix.lower()
    if ext != ".xlsx":
        return jsonify({"error": "Formato não suportado. Use .xlsx"}), 400

    try:
        data = file.read()
        ingredients = process_excel_data(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Erro ao ler Excel: {e}"}), 500

    if not ingredients:
        return jsonify({"error": "Nenhum ingrediente válido encontrado."}), 400

    return jsonify({"ingredients": ingredients})


def main():
    import os
    import sys
    
    # Fix for corrupted Python executable path in Flask's debug reloader
    # If sys.executable points to a non-existent file, disable the reloader
    use_reloader = True
    if not os.path.exists(sys.executable):
        # Disable reloader to avoid FileNotFoundError on restart
        use_reloader = False
    
    app.run(debug=True, port=5000, use_reloader=use_reloader)


if __name__ == "__main__":
    main()
