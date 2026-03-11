"""Tests for input validation module — validators.py."""

import pytest
from decimal import Decimal

from tabela_nutricional.validators import (
    validate_nutrient_ranges,
    validate_nutrient_relationships,
    validate_portion_size,
    validate_ingredient_quantity,
    validate_ingredients_full,
    ValidationResult,
    PORTION_SIZE_MIN,
    PORTION_SIZE_MAX,
)
from tabela_nutricional.types import NutritionalInfo


# ---------------------------------------------------------------------------
# validate_nutrient_ranges
# ---------------------------------------------------------------------------


def test_valid_nutrients_no_errors():
    data = {"carbs": 20, "proteins": 10, "totalFat": 5, "sodium": 500}
    result = validate_nutrient_ranges(data)
    assert result.is_valid
    assert not result.warnings


def test_negative_nutrient_is_error():
    data = {"carbs": -1}
    result = validate_nutrient_ranges(data)
    assert not result.is_valid
    assert any("negativo" in e for e in result.errors)


def test_extreme_nutrient_is_warning():
    data = {"carbs": 101}  # > 100 max
    result = validate_nutrient_ranges(data)
    assert result.is_valid  # warnings, not errors
    assert any("elevado" in w for w in result.warnings)


def test_sodium_extreme_is_warning():
    data = {"sodium": 200000}  # > 100000 max
    result = validate_nutrient_ranges(data)
    assert result.is_valid
    assert any("sódio" in w.lower() or "sodium" in w.lower() for w in result.warnings)


def test_zero_values_valid():
    data = {"carbs": 0, "proteins": 0, "totalFat": 0, "sodium": 0}
    result = validate_nutrient_ranges(data)
    assert result.is_valid
    assert not result.warnings


def test_label_prefix_in_messages():
    data = {"carbs": -5}
    result = validate_nutrient_ranges(data, label="Farinha")
    assert result.errors
    assert result.errors[0].startswith("Farinha:")


# ---------------------------------------------------------------------------
# validate_nutrient_relationships
# ---------------------------------------------------------------------------


def test_saturated_greater_than_total_fat_warns():
    ni = NutritionalInfo(
        carbs=Decimal("10"), proteins=Decimal("5"),
        totalFat=Decimal("3"), saturatedFat=Decimal("5"),
        transFat=Decimal("0"), fiber=Decimal("1"),
        sodium=Decimal("100"), totalSugars=Decimal("2"),
        addedSugars=Decimal("1"),
    )
    result = validate_nutrient_relationships(ni)
    assert any("saturada" in w.lower() for w in result.warnings)


def test_trans_greater_than_total_fat_warns():
    ni = NutritionalInfo(
        carbs=Decimal("10"), proteins=Decimal("5"),
        totalFat=Decimal("2"), saturatedFat=Decimal("1"),
        transFat=Decimal("5"), fiber=Decimal("1"),
        sodium=Decimal("100"), totalSugars=Decimal("2"),
        addedSugars=Decimal("1"),
    )
    result = validate_nutrient_relationships(ni)
    assert any("trans" in w.lower() for w in result.warnings)


def test_added_sugars_greater_than_total_sugars_warns():
    ni = NutritionalInfo(
        carbs=Decimal("20"), proteins=Decimal("5"),
        totalFat=Decimal("3"), saturatedFat=Decimal("1"),
        transFat=Decimal("0"), fiber=Decimal("1"),
        sodium=Decimal("100"), totalSugars=Decimal("5"),
        addedSugars=Decimal("8"),
    )
    result = validate_nutrient_relationships(ni)
    assert any("adicionados" in w.lower() for w in result.warnings)


def test_total_sugars_greater_than_carbs_warns():
    ni = NutritionalInfo(
        carbs=Decimal("5"), proteins=Decimal("5"),
        totalFat=Decimal("3"), saturatedFat=Decimal("1"),
        transFat=Decimal("0"), fiber=Decimal("1"),
        sodium=Decimal("100"), totalSugars=Decimal("10"),
        addedSugars=Decimal("2"),
    )
    result = validate_nutrient_relationships(ni)
    assert any("totais" in w.lower() and "carboidratos" in w.lower() for w in result.warnings)


def test_macro_sum_exceeds_100_warns():
    ni = NutritionalInfo(
        carbs=Decimal("50"), proteins=Decimal("30"),
        totalFat=Decimal("25"), saturatedFat=Decimal("5"),
        transFat=Decimal("0"), fiber=Decimal("5"),
        sodium=Decimal("100"), totalSugars=Decimal("10"),
        addedSugars=Decimal("5"),
    )
    # sum = 50+30+25+5 = 110 > 105
    result = validate_nutrient_relationships(ni)
    assert any("macronutrientes" in w.lower() for w in result.warnings)


def test_valid_relationships_no_warnings():
    ni = NutritionalInfo(
        carbs=Decimal("20"), proteins=Decimal("5"),
        totalFat=Decimal("10"), saturatedFat=Decimal("3"),
        transFat=Decimal("0.5"), fiber=Decimal("2"),
        sodium=Decimal("200"), totalSugars=Decimal("8"),
        addedSugars=Decimal("3"),
    )
    result = validate_nutrient_relationships(ni)
    assert not result.warnings


# ---------------------------------------------------------------------------
# validate_portion_size
# ---------------------------------------------------------------------------


def test_portion_valid():
    result = validate_portion_size(Decimal("100"))
    assert result.is_valid


def test_portion_too_small_is_error():
    result = validate_portion_size(Decimal("0.001"))
    assert not result.is_valid
    assert any("mínimo" in e for e in result.errors)


def test_portion_too_large_is_warning():
    result = validate_portion_size(Decimal("20000"))
    assert result.is_valid  # warning, not error
    assert any("limite" in w for w in result.warnings)


def test_portion_boundary_min_valid():
    result = validate_portion_size(PORTION_SIZE_MIN)
    assert result.is_valid


def test_portion_boundary_max_valid():
    result = validate_portion_size(PORTION_SIZE_MAX)
    assert result.is_valid


# ---------------------------------------------------------------------------
# validate_ingredient_quantity
# ---------------------------------------------------------------------------


def test_quantity_valid():
    result = validate_ingredient_quantity(Decimal("100"))
    assert result.is_valid


def test_quantity_too_small():
    result = validate_ingredient_quantity(Decimal("0.0001"))
    assert not result.is_valid


def test_quantity_too_large_is_warning():
    result = validate_ingredient_quantity(Decimal("200000"))
    assert result.is_valid
    assert result.warnings


# ---------------------------------------------------------------------------
# validate_ingredients_full
# ---------------------------------------------------------------------------


def test_full_validation_valid_ingredients():
    ingredients = [
        {
            "name": "Farinha",
            "quantity": 100,
            "nutritionalInfo": {
                "carbs": 76, "proteins": 10, "totalFat": 1,
                "saturatedFat": 0.2, "transFat": 0,
                "fiber": 2, "sodium": 1, "totalSugars": 2,
                "addedSugars": 0,
            },
        }
    ]
    result = validate_ingredients_full(ingredients)
    assert result.is_valid


def test_full_validation_negative_nutrient():
    ingredients = [
        {
            "name": "Bad",
            "quantity": 100,
            "nutritionalInfo": {"carbs": -5},
        }
    ]
    result = validate_ingredients_full(ingredients)
    assert not result.is_valid


def test_full_validation_multiple_ingredients_with_warnings():
    ingredients = [
        {
            "name": "OK",
            "quantity": 100,
            "nutritionalInfo": {"carbs": 20, "proteins": 5, "totalFat": 10},
        },
        {
            "name": "Suspeito",
            "quantity": 100,
            "nutritionalInfo": {
                "carbs": 50, "proteins": 30, "totalFat": 25, "fiber": 5,
            },
        },
    ]
    result = validate_ingredients_full(ingredients)
    assert result.is_valid  # no errors (just warnings for macro sum)
    assert result.warnings  # macro sum warning for "Suspeito"
