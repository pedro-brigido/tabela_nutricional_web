"""
ANVISA-conformance integration tests — multi-ingredient, categories, edge cases.
Validates calculator pipeline end-to-end against expected outputs.
"""

import pytest
from decimal import Decimal

from tabela_nutricional import calculate, to_legacy_output, REGULATORY_VERSION
from tabela_nutricional.calculator import NUTRIENT_KEYS


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_ingredient(name="Ingredient", qty=100, **nutri_overrides):
    base = {
        "carbs": 0, "proteins": 0, "totalFat": 0, "saturatedFat": 0,
        "transFat": 0, "fiber": 0, "sodium": 0, "totalSugars": 0,
        "addedSugars": 0,
    }
    base.update(nutri_overrides)
    return {"name": name, "quantity": qty, "nutritionalInfo": base}


# ---------------------------------------------------------------------------
# Multi-ingredient aggregation
# ---------------------------------------------------------------------------


class TestMultiIngredient:
    def test_two_ingredients_weighted_average(self):
        """Two ingredients at 50g each: nutrients should average."""
        ing = [
            _make_ingredient("A", 50, carbs=20, proteins=10, totalFat=5, fiber=2, sodium=100),
            _make_ingredient("B", 50, carbs=40, proteins=20, totalFat=10, fiber=4, sodium=200),
        ]
        result = calculate(ing, 100)
        assert result is not None
        # per100g: weighted average = (20*50/100 + 40*50/100) / (100/100) = 30
        carbs_100 = result.per100_base.nutrients["carbs"].raw
        assert carbs_100 == Decimal("30")

    def test_three_ingredients_different_weights(self):
        """3 ingredients with different quantities."""
        ing = [
            _make_ingredient("Flour", 200, carbs=76, proteins=10, totalFat=1, fiber=2, sodium=1),
            _make_ingredient("Sugar", 100, carbs=100, totalSugars=100, addedSugars=100),
            _make_ingredient("Butter", 50, totalFat=81, saturatedFat=51, carbs=0.1, sodium=11),
        ]
        result = calculate(ing, 60)
        assert result is not None
        # Total weight = 350g
        # per100g carbs: (76*200/100 + 100*100/100 + 0.1*50/100) * 100/350 = (152+100+0.05)*100/350
        expected_carbs = (Decimal("76") * 2 + Decimal("100") + Decimal("0.1") * Decimal("0.5")) * Decimal("100") / Decimal("350")
        carbs_raw = result.per100_base.nutrients["carbs"].raw
        assert abs(carbs_raw - expected_carbs) < Decimal("0.01")

    def test_five_ingredients(self):
        """Pipeline handles 5+ ingredients without error."""
        ing = [_make_ingredient(f"Ing{i}", 20, carbs=10+i, proteins=5) for i in range(5)]
        result = calculate(ing, 50)
        assert result is not None
        assert all(k in result.per100_base.nutrients for k in NUTRIENT_KEYS)


# ---------------------------------------------------------------------------
# Portion scaling
# ---------------------------------------------------------------------------


class TestPortionScaling:
    def test_portion_50g_is_half_of_100(self):
        ing = [_make_ingredient("A", 100, carbs=20, proteins=10, totalFat=5, fiber=2, sodium=200)]
        result = calculate(ing, 50)
        carbs_100 = result.per100_base.nutrients["carbs"].raw
        carbs_portion = result.perPortion.nutrients["carbs"].raw
        # per_portion = per100 * 50/100 = per100 * 0.5
        assert carbs_portion == carbs_100 * Decimal("0.5")

    def test_portion_200g_is_double(self):
        ing = [_make_ingredient("A", 100, carbs=20, proteins=10, totalFat=5, fiber=2, sodium=200)]
        result = calculate(ing, 200)
        carbs_100 = result.per100_base.nutrients["carbs"].raw
        carbs_portion = result.perPortion.nutrients["carbs"].raw
        assert carbs_portion == carbs_100 * Decimal("2")


# ---------------------------------------------------------------------------
# Food categories
# ---------------------------------------------------------------------------


class TestFoodCategories:
    def test_supplement_category(self):
        ing = [_make_ingredient("Vitamin C", 100, carbs=1, proteins=0.5)]
        result = calculate(ing, 30, food_category="supplement")
        assert result is not None
        assert result.meta.context_echo["food_category"] == "supplement"

    def test_as_prepared_category(self):
        ing = [_make_ingredient("Gelatin", 100, carbs=15, proteins=8)]
        result = calculate(ing, 120, food_category="as_prepared")
        assert result is not None

    def test_liquid_form(self):
        ing = [_make_ingredient("Juice", 100, carbs=10, totalSugars=9, fiber=0.5, sodium=5)]
        result = calculate(ing, 200, food_form="liquid", unit_base="100ml", portion_unit="ml")
        assert result is not None
        assert result.meta.context_echo["food_form"] == "liquid"
        assert result.meta.context_echo["unit_base"] == "100ml"


# ---------------------------------------------------------------------------
# %VD calculation
# ---------------------------------------------------------------------------


class TestVDPercent:
    def test_proteins_vd_50g(self):
        """VDR for proteins = 50g. 25g per portion = 50%."""
        ing = [_make_ingredient("A", 100, proteins=25, carbs=10, totalFat=5, fiber=1, sodium=100)]
        result = calculate(ing, 100)
        assert result.perPortion.nutrients["proteins"].vd_percent == 50

    def test_trans_fat_vd_is_double_asterisk(self):
        """Trans fat has no established VDR → display '**'."""
        ing = [_make_ingredient("A", 100, totalFat=10, transFat=1, carbs=10, proteins=5, fiber=1, sodium=100)]
        result = calculate(ing, 100)
        assert result.perPortion.nutrients["transFat"].vd_display == "**"

    def test_total_sugars_vd_is_double_asterisk(self):
        """Total sugars has no established VDR → display '**'."""
        ing = [_make_ingredient("A", 100, carbs=20, totalSugars=10, proteins=5, totalFat=5, fiber=1, sodium=100)]
        result = calculate(ing, 100)
        assert result.perPortion.nutrients["totalSugars"].vd_display == "**"


# ---------------------------------------------------------------------------
# Insignificant quantities in full pipeline
# ---------------------------------------------------------------------------


class TestInsignificanceInPipeline:
    def test_zero_nutrient_declared_as_zero(self):
        """All zero nutrients → displayed as '0'."""
        ing = [_make_ingredient("Water", 100)]
        result = calculate(ing, 100)
        for key in NUTRIENT_KEYS:
            nr = result.per100_base.nutrients[key]
            assert nr.display == "0", f"{key} should display '0' but got '{nr.display}'"

    def test_insignificant_carbs(self):
        """Carbs ≤ 0.5g → declared as 0."""
        ing = [_make_ingredient("A", 100, carbs=Decimal("0.3"), proteins=10, totalFat=5, fiber=1, sodium=100)]
        result = calculate(ing, 100)
        assert result.per100_base.nutrients["carbs"].flags.is_insignificant is True


# ---------------------------------------------------------------------------
# Regulatory version
# ---------------------------------------------------------------------------


class TestRegulatoryVersion:
    def test_meta_has_regulatory_version(self):
        ing = [_make_ingredient("A", 100, carbs=10, proteins=5, totalFat=2, fiber=1, sodium=50)]
        result = calculate(ing, 50)
        assert result.meta.context_echo["regulatory_version"] == REGULATORY_VERSION

    def test_warnings_in_meta(self):
        """Meta should have warnings list."""
        ing = [_make_ingredient("A", 100, carbs=10, proteins=5, totalFat=2, fiber=1, sodium=50)]
        result = calculate(ing, 50)
        assert isinstance(result.meta.warnings, list)


# ---------------------------------------------------------------------------
# Legacy output conversion
# ---------------------------------------------------------------------------


class TestLegacyOutput:
    def test_legacy_has_all_nutrients(self):
        ing = [_make_ingredient("A", 100, carbs=20, proteins=10, totalFat=5, fiber=2, sodium=200)]
        result = calculate(ing, 50)
        legacy = to_legacy_output(result)
        for key in NUTRIENT_KEYS:
            assert key in legacy["per100g"], f"{key} missing from per100g"
            assert key in legacy["perPortion"], f"{key} missing from perPortion"

    def test_legacy_meta_has_warnings(self):
        ing = [_make_ingredient("A", 100, carbs=10, proteins=5, totalFat=2, fiber=1, sodium=50)]
        result = calculate(ing, 50)
        legacy = to_legacy_output(result)
        assert "warnings" in legacy["meta"]
        assert "context_echo" in legacy["meta"]

    def test_legacy_per100g_values_are_float(self):
        ing = [_make_ingredient("A", 100, carbs=20, proteins=10, totalFat=5, fiber=2, sodium=200)]
        result = calculate(ing, 50)
        legacy = to_legacy_output(result)
        for key in NUTRIENT_KEYS:
            assert isinstance(legacy["per100g"][key]["raw"], float)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_zero_portion_returns_none(self):
        ing = [_make_ingredient("A", 100, carbs=10)]
        assert calculate(ing, 0) is None

    def test_negative_portion_returns_none(self):
        ing = [_make_ingredient("A", 100, carbs=10)]
        assert calculate(ing, -50) is None

    def test_empty_ingredients_returns_none(self):
        assert calculate([], 100) is None

    def test_single_ingredient_zero_quantity_returns_none(self):
        assert calculate([_make_ingredient("A", 0)], 100) is None
