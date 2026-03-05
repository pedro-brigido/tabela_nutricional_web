"""
Tests for allergens module — RDC 429/2020 §3.3, RDC 26/2015.
"""

from tabela_nutricional.allergens import (
    VALID_ALLERGEN_KEYS,
    ALLERGEN_LABELS,
    ALLERGEN_GROUPS,
    GLUTEN_LABELS,
    validate_allergens,
    format_allergen_declaration,
    validate_gluten_status,
)


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------


def test_all_allergen_keys_have_labels():
    for key in VALID_ALLERGEN_KEYS:
        assert key in ALLERGEN_LABELS


def test_allergen_groups_cover_all_keys():
    keys_in_groups = set()
    for group_keys in ALLERGEN_GROUPS.values():
        keys_in_groups.update(group_keys)
    assert VALID_ALLERGEN_KEYS == keys_in_groups


def test_gluten_labels_has_both_options():
    assert "contains_gluten" in GLUTEN_LABELS
    assert "gluten_free" in GLUTEN_LABELS


# ---------------------------------------------------------------------------
# validate_allergens
# ---------------------------------------------------------------------------


def test_validate_valid_allergens():
    valid, invalid = validate_allergens(["milk", "eggs", "wheat"])
    assert valid == ["milk", "eggs", "wheat"]
    assert invalid == []


def test_validate_invalid_allergen():
    valid, invalid = validate_allergens(["milk", "kiwi", "eggs"])
    assert "milk" in valid
    assert "eggs" in valid
    assert "kiwi" in invalid


def test_validate_strips_whitespace():
    valid, _ = validate_allergens(["  milk ", "EGGS"])
    assert "milk" in valid
    assert "eggs" in valid


def test_validate_deduplicates():
    valid, _ = validate_allergens(["milk", "milk", "milk"])
    assert valid == ["milk"]


def test_validate_empty_list():
    valid, invalid = validate_allergens([])
    assert valid == []
    assert invalid == []


def test_validate_ignores_empty_strings():
    valid, invalid = validate_allergens(["", "  ", "milk"])
    assert valid == ["milk"]
    assert invalid == []


# ---------------------------------------------------------------------------
# format_allergen_declaration
# ---------------------------------------------------------------------------


def test_format_single_allergen():
    text = format_allergen_declaration(["milk"])
    assert "ALÉRGICOS: CONTÉM LEITE." in text


def test_format_multiple_allergens():
    text = format_allergen_declaration(["milk", "eggs", "wheat"])
    assert "LEITE" in text
    assert "OVOS" in text
    assert "TRIGO" in text
    assert text.startswith("ALÉRGICOS: CONTÉM ")


def test_format_with_gluten():
    text = format_allergen_declaration(["milk"], gluten_status="contains_gluten")
    assert "CONTÉM GLÚTEN." in text


def test_format_gluten_free():
    text = format_allergen_declaration([], gluten_status="gluten_free")
    assert "NÃO CONTÉM GLÚTEN." in text


def test_format_with_custom_allergens():
    text = format_allergen_declaration(["milk"], custom_allergens="kiwi")
    assert "KIWI" in text
    assert "LEITE" in text


def test_format_empty_returns_empty():
    text = format_allergen_declaration([])
    assert text == ""


def test_format_allergens_deduplicates_labels():
    text = format_allergen_declaration(["milk", "milk"])
    assert text.count("LEITE") == 1


# ---------------------------------------------------------------------------
# validate_gluten_status
# ---------------------------------------------------------------------------


def test_gluten_contains():
    assert validate_gluten_status("contains_gluten") == "contains_gluten"


def test_gluten_free():
    assert validate_gluten_status("gluten_free") == "gluten_free"


def test_gluten_portuguese_contains():
    assert validate_gluten_status("contém glúten") == "contains_gluten"


def test_gluten_portuguese_free():
    assert validate_gluten_status("não contém glúten") == "gluten_free"


def test_gluten_none():
    assert validate_gluten_status(None) is None


def test_gluten_empty():
    assert validate_gluten_status("") is None


def test_gluten_invalid():
    assert validate_gluten_status("maybe") is None
