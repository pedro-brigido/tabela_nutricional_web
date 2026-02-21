"""Tests for tabela_nutricional.calculator (pipeline and legacy API)."""

import pytest
from decimal import Decimal

from tabela_nutricional import calculate, calculate_legacy, to_legacy_output
from tabela_nutricional.calculator import NUTRIENT_KEYS
from tabela_nutricional.vdr_values import VDR_BY_NUTRIENT, has_vdr


def test_calculate_returns_none_for_empty_ingredients():
    assert calculate([], 100) is None
    assert calculate_legacy([], 100) is None


def test_calculate_returns_none_for_zero_total_weight():
    assert (
        calculate(
            [{"quantity": 0, "nutritionalInfo": {"carbs": 10, "proteins": 5}}],
            50,
        )
        is None
    )


def test_calculate_single_ingredient_per_100g():
    ingredients = [
        {
            "quantity": 100,
            "nutritionalInfo": {
                "carbs": 20,
                "proteins": 5,
                "totalFat": 10,
                "fiber": 2,
                "sodium": 200,
            },
        }
    ]
    result = calculate(ingredients, 50)
    assert result is not None
    assert result.per100_base.nutrients
    assert result.perPortion.nutrients
    assert "carbs" in result.per100_base.nutrients
    assert "proteins" in result.per100_base.nutrients
    assert "energy" in result.per100_base.nutrients


def test_legacy_output_has_per100g_perPortion():
    ingredients = [
        {
            "quantity": 100,
            "nutritionalInfo": {
                "carbs": 20,
                "proteins": 5,
                "totalFat": 10,
                "fiber": 2,
                "sodium": 200,
            },
        }
    ]
    result = calculate_legacy(ingredients, 50)
    assert result is not None
    assert "per100g" in result
    assert "perPortion" in result
    assert "carbs" in result["per100g"]
    assert "energy" in result["perPortion"]


def test_calculate_proteins_vd_calculated():
    """%VD for proteins must be calculated (per portion)."""
    ingredients = [
        {
            "quantity": 100,
            "nutritionalInfo": {
                "carbs": 10,
                "proteins": 25,
                "totalFat": 5,
                "fiber": 1,
                "sodium": 100,
            },
        }
    ]
    result = calculate(ingredients, 100)
    assert result is not None
    proteins_portion = result.perPortion.nutrients["proteins"]
    assert proteins_portion.vd_display != ""
    assert proteins_portion.vd_display == "50"
    assert proteins_portion.vd_percent == 50


def test_legacy_proteins_vd():
    ingredients = [
        {
            "quantity": 100,
            "nutritionalInfo": {
                "carbs": 10,
                "proteins": 25,
                "totalFat": 5,
                "fiber": 1,
                "sodium": 100,
            },
        }
    ]
    result = calculate_legacy(ingredients, 100)
    assert result["perPortion"]["proteins"]["vd"] == "50"


def test_vdr_has_proteins():
    assert "proteins" in VDR_BY_NUTRIENT
    assert has_vdr("proteins")
    assert VDR_BY_NUTRIENT["proteins"].value == Decimal("50")


def test_total_sugars_and_added_sugars_in_result():
    ingredients = [
        {
            "quantity": 100,
            "nutritionalInfo": {
                "carbs": 15,
                "proteins": 5,
                "totalFat": 2,
                "fiber": 1,
                "sodium": 50,
                "totalSugars": 3,
                "addedSugars": 1,
            },
        }
    ]
    result = calculate(ingredients, 50)
    assert "totalSugars" in result.per100_base.nutrients
    assert "addedSugars" in result.per100_base.nutrients
    assert "totalSugars" in NUTRIENT_KEYS
    assert "addedSugars" in NUTRIENT_KEYS


def test_trans_fat_vd_display_is_asterisks():
    ingredients = [
        {
            "quantity": 100,
            "nutritionalInfo": {
                "carbs": 10,
                "proteins": 5,
                "totalFat": 2,
                "transFat": 0.1,
                "fiber": 1,
                "sodium": 50,
            },
        }
    ]
    result = calculate(ingredients, 50)
    assert result.perPortion.nutrients["transFat"].vd_display == "**"


def test_result_has_meta():
    ingredients = [
        {"quantity": 100, "nutritionalInfo": {"carbs": 10, "proteins": 5, "totalFat": 2, "fiber": 1, "sodium": 50}}
    ]
    result = calculate(ingredients, 50)
    assert result.meta.context_echo
    assert "portion_size" in result.meta.context_echo
