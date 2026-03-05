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


def test_known_references():
    """Spot-check known portion references."""
    # Leite fluido: 200ml
    ref = PORTION_BY_CODE.get("IV_A")
    assert ref is not None
    assert ref.portion_g == Decimal("200")
    assert ref.group_name == "Leite fluido (ml)"

    # Ovos: 50g
    ref = PORTION_BY_CODE.get("V_C")
    assert ref is not None
    assert ref.portion_g == Decimal("50")
