"""
Tests for portion_reference module — IN 75/2020 Anexo V.
"""

from decimal import Decimal

from tabela_nutricional.portion_reference import (
    PORTION_REFERENCES,
    PORTION_BY_CODE,
    validate_portion_size,
    list_portion_groups,
)


def test_portion_references_not_empty():
    assert len(PORTION_REFERENCES) > 20


def test_portion_by_code_matches_list():
    assert len(PORTION_BY_CODE) == len(PORTION_REFERENCES)
    for ref in PORTION_REFERENCES:
        assert ref.group_code in PORTION_BY_CODE


def test_validate_within_tolerance():
    # Pães: 50g, ±30% → 35g–65g
    result = validate_portion_size(Decimal("50"), "I_A")
    assert result["is_valid"] is True
    assert result["warning"] is None


def test_validate_at_lower_bound():
    # 50g * 0.7 = 35g
    result = validate_portion_size(Decimal("35"), "I_A")
    assert result["is_valid"] is True


def test_validate_at_upper_bound():
    # 50g * 1.3 = 65g
    result = validate_portion_size(Decimal("65"), "I_A")
    assert result["is_valid"] is True


def test_validate_below_tolerance():
    result = validate_portion_size(Decimal("20"), "I_A")
    assert result["is_valid"] is False
    assert result["warning"]
    assert "porção de referência" in result["warning"].lower()


def test_validate_above_tolerance():
    result = validate_portion_size(Decimal("100"), "I_A")
    assert result["is_valid"] is False
    assert result["warning"]


def test_validate_no_group_code():
    result = validate_portion_size(Decimal("50"))
    assert result["is_valid"] is True
    assert result["reference"] is None


def test_validate_unknown_group_code():
    result = validate_portion_size(Decimal("50"), "UNKNOWN")
    assert result["is_valid"] is True
    assert result["reference"] is None


def test_list_portion_groups_returns_dicts():
    groups = list_portion_groups()
    assert len(groups) == len(PORTION_REFERENCES)
    for g in groups:
        assert "code" in g
        assert "name" in g
        assert "portion_g" in g
        assert "household_measure" in g
        assert "food_form" in g
        assert g["food_form"] in ("solid", "liquid", "both")


def test_list_portion_groups_filter_solid():
    groups = list_portion_groups(food_form="solid")
    for g in groups:
        assert g["food_form"] in ("solid", "both")
    # Should exclude pure liquid groups like Leite fluido, Sucos
    codes = {g["code"] for g in groups}
    assert "IV_A" not in codes  # Leite fluido is liquid-only
    assert "III_C" not in codes  # Sucos is liquid-only


def test_list_portion_groups_filter_liquid():
    groups = list_portion_groups(food_form="liquid")
    for g in groups:
        assert g["food_form"] in ("liquid", "both")
    # Should exclude pure solid groups like Pães
    codes = {g["code"] for g in groups}
    assert "I_A" not in codes  # Pães is solid-only
    assert "IV_A" in codes  # Leite fluido is liquid


def test_list_portion_groups_filter_none_returns_all():
    all_groups = list_portion_groups()
    none_groups = list_portion_groups(food_form=None)
    assert len(all_groups) == len(none_groups)


def test_list_portion_groups_filter_invalid_returns_all():
    all_groups = list_portion_groups()
    invalid_groups = list_portion_groups(food_form="invalid")
    assert len(all_groups) == len(invalid_groups)


def test_food_form_classification():
    """Verify specific food_form classifications."""
    assert PORTION_BY_CODE["III_C"].food_form == "liquid"  # Sucos
    assert PORTION_BY_CODE["IV_A"].food_form == "liquid"   # Leite fluido
    assert PORTION_BY_CODE["IV_D"].food_form == "liquid"   # Iogurtes
    assert PORTION_BY_CODE["VIII_C"].food_form == "liquid"  # Sopas
    assert PORTION_BY_CODE["VI_A"].food_form == "both"     # Óleos
    assert PORTION_BY_CODE["VIII_A"].food_form == "both"   # Molhos
    assert PORTION_BY_CODE["I_A"].food_form == "solid"     # Pães
    assert PORTION_BY_CODE["V_A"].food_form == "solid"     # Carnes


def test_known_references():
    """Spot-check known portion references."""
    # Leite fluido: 200ml
    ref = PORTION_BY_CODE.get("IV_A")
    assert ref is not None
    assert ref.portion_g == Decimal("200")
    assert ref.group_name == "Leite fluido"

    # Ovos: 50g
    ref = PORTION_BY_CODE.get("V_C")
    assert ref is not None
    assert ref.portion_g == Decimal("50")
