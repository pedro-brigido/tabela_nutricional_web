"""Tests for Excel import parser in calculator blueprint."""

import pytest

from app.blueprints.calculator import MAX_EXCEL_ROWS, _process_excel_data

openpyxl = pytest.importorskip("openpyxl")


def _build_workbook_bytes(rows: list[list]):
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    from io import BytesIO

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_process_excel_data_parses_sugars_columns():
    data = _build_workbook_bytes(
        [
            [
                "Nome",
                "Quantidade",
                "Kcal",
                "Carboidratos",
                "Proteínas",
                "Gorduras",
                "Saturadas",
                "Trans",
                "Fibra",
                "Sódio",
                "Açúcar Total",
                "Açúcar Adicionado",
            ],
            ["Farinha", 100, 350, 76, 10, 1, 0.2, 0, 2, 1, 2, 1],
        ]
    )
    ingredients, truncated, parse_warnings = _process_excel_data(data)
    assert truncated is False
    assert len(ingredients) == 1
    nutri = ingredients[0]["nutritionalInfo"]
    assert nutri["totalSugars"] == 2
    assert nutri["addedSugars"] == 1


def test_process_excel_data_requires_name_column():
    data = _build_workbook_bytes([["Peso", "Kcal"], [10, 100]])
    with pytest.raises(ValueError):
        _process_excel_data(data)


def test_process_excel_data_limits_rows():
    rows = [["Nome", "Quantidade", "Kcal"]]
    for i in range(MAX_EXCEL_ROWS + 10):
        rows.append([f"Ingrediente {i}", 1, 1])
    data = _build_workbook_bytes(rows)
    ingredients, truncated, _warnings = _process_excel_data(data)
    assert truncated is True
    assert len(ingredients) == MAX_EXCEL_ROWS
