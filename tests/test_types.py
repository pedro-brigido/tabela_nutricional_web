"""Tests for types — normalization and validation."""

import pytest
from decimal import Decimal

from tabela_nutricional.types import (
    CalculationContext,
    NutritionalInfo,
    IngredientInput,
    normalize_ingredients,
    _to_decimal,
)


def test_to_decimal():
    assert _to_decimal(None) == Decimal("0")
    assert _to_decimal(10) == Decimal("10")
    assert _to_decimal("3,5") == Decimal("3.5")
    assert _to_decimal(Decimal("1.5")) == Decimal("1.5")


def test_context_from_request():
    ctx = CalculationContext.from_request(50, portion_unit="g")
    assert ctx.portion_size == Decimal("50")
    assert ctx.portion_unit == "g"
    assert ctx.unit_base == "100g"


def test_context_invalid_portion_raises():
    with pytest.raises(ValueError):
        CalculationContext.from_request(0)
    with pytest.raises(ValueError):
        CalculationContext.from_request(-1)


def test_nutritional_info_from_dict():
    ni = NutritionalInfo.from_dict({
        "carbs": 20,
        "proteins": 5,
        "totalFat": 10,
        "saturatedFat": 2,
        "transFat": 0,
        "fiber": 1,
        "sodium": 100,
        "totalSugars": 5,
        "addedSugars": 2,
    })
    assert ni.carbs == Decimal("20")
    assert ni.solubleFiber == ni.fiber  # fallback


def test_ingredient_from_dict():
    ing = IngredientInput.from_dict({
        "quantity": 100,
        "nutritionalInfo": {"carbs": 15, "proteins": 5, "totalFat": 2, "fiber": 1, "sodium": 50, "totalSugars": 0, "addedSugars": 0},
    })
    assert ing.quantity == Decimal("100")
    assert ing.nutritionalInfo.carbs == Decimal("15")


def test_normalize_ingredients():
    raw = [
        {"quantity": 50, "nutritionalInfo": {"carbs": 10, "proteins": 5, "totalFat": 0, "fiber": 0, "sodium": 0, "totalSugars": 0, "addedSugars": 0}},
    ]
    out = normalize_ingredients(raw)
    assert len(out) == 1
    assert out[0].quantity == Decimal("50")
