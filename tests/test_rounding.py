"""Tests for rounding module — IN 75/2020 Anexo III, half-up."""

import pytest
from decimal import Decimal

from tabela_nutricional.rounding import (
    round_quantity,
    format_pt_br,
    round_quantity_to_decimal,
    RULE_ENERGY,
    RULE_MACRONUTRIENTS_G,
    RULE_SODIUM,
    RULE_TRANS_FAT,
    NUTRIENT_ROUNDING_RULE,
)


def test_half_up_one_decimal():
    """0.5 rounds up to 1; 0.4 rounds down to 0.4 (bankers would give 0)."""
    r = RULE_MACRONUTRIENTS_G
    # value 2.5 in band <10 -> 1 decimal -> 2.5 (half-up: 2.5 stays 2.5 for 1 decimal)
    # Actually 2.5 with 1 decimal place: quantize 0.1 -> 2.5. So 2.5.
    # 1.15 with 1 decimal: half-up -> 1.2 (1.15 rounds up)
    rounded = round_quantity(Decimal("1.15"), r)
    assert rounded.value == Decimal("1.2")
    # 1.14 with 1 decimal: half-up -> 1.1
    rounded2 = round_quantity(Decimal("1.14"), r)
    assert rounded2.value == Decimal("1.1")


def test_half_up_integer_band():
    """Values >= 10 g: integer. 10.5 -> 11 (half-up)."""
    r = RULE_MACRONUTRIENTS_G
    rounded = round_quantity(Decimal("10.5"), r)
    assert rounded.value == Decimal("11")
    rounded2 = round_quantity(Decimal("10.4"), r)
    assert rounded2.value == Decimal("10")


def test_energy_always_integer():
    """Energy in kcal always integer (Anexo III)."""
    rounded = round_quantity(Decimal("97.5"), RULE_ENERGY)
    assert rounded.value == Decimal("98")
    assert rounded.decimal_places == 0


def test_format_pt_br_comma():
    """PT-BR uses comma as decimal separator."""
    r = round_quantity(Decimal("1.5"), RULE_MACRONUTRIENTS_G)
    s = format_pt_br(r)
    assert "," in s
    assert s == "1,5"


def test_format_pt_br_suppress_trailing_zero():
    """Integer display without ,0."""
    r = round_quantity(Decimal("10"), RULE_MACRONUTRIENTS_G)
    s = format_pt_br(r)
    assert s == "10"
    assert ",0" not in s


def test_sodium_integer():
    rounded = round_quantity(Decimal("150.7"), RULE_SODIUM)
    assert rounded.value == Decimal("151")
    assert rounded.unit == "mg"


def test_round_quantity_to_decimal():
    v = round_quantity_to_decimal(Decimal("2.35"), RULE_MACRONUTRIENTS_G)
    assert v == Decimal("2.4")


def test_nutrient_rules_cover_all():
    expected = [
        "energy", "carbs", "proteins", "totalFat", "saturatedFat",
        "transFat", "fiber", "sodium", "totalSugars", "addedSugars",
    ]
    for k in expected:
        assert k in NUTRIENT_ROUNDING_RULE
