"""
Expanded tests for significance — all nutrients + edge cases.
IN 75/2020 Anexo IV.
"""

import pytest
from decimal import Decimal

from tabela_nutricional.significance import (
    evaluate_insignificance,
    SIGNIFICANCE_BY_NUTRIENT,
    _get_threshold,
)


CONTEXT_CONV = {"food_category": "conventional"}
CONTEXT_SUPP = {"food_category": "supplement"}


class TestEachNutrientThreshold:
    """Verify that each nutrient triggers insignificance below its threshold."""

    @pytest.mark.parametrize("nutrient,threshold_conv", [
        ("energy", Decimal("4")),
        ("carbs", Decimal("0.5")),
        ("proteins", Decimal("0.5")),
        ("totalFat", Decimal("0.5")),
        ("saturatedFat", Decimal("0.2")),
        ("fiber", Decimal("0.5")),
        ("sodium", Decimal("5")),
        ("totalSugars", Decimal("0.5")),
        ("addedSugars", Decimal("0.5")),
    ])
    def test_below_threshold_is_insignificant(self, nutrient, threshold_conv):
        half = threshold_conv / 2
        d = evaluate_insignificance(nutrient, half, half, CONTEXT_CONV)
        assert d.is_insignificant is True
        assert d.was_forced_zero is True

    @pytest.mark.parametrize("nutrient,threshold_conv", [
        ("energy", Decimal("4")),
        ("carbs", Decimal("0.5")),
        ("proteins", Decimal("0.5")),
        ("totalFat", Decimal("0.5")),
        ("saturatedFat", Decimal("0.2")),
        ("fiber", Decimal("0.5")),
        ("sodium", Decimal("5")),
        ("totalSugars", Decimal("0.5")),
        ("addedSugars", Decimal("0.5")),
    ])
    def test_above_threshold_is_significant(self, nutrient, threshold_conv):
        above = threshold_conv + Decimal("1")
        d = evaluate_insignificance(nutrient, above, above, CONTEXT_CONV)
        assert d.is_insignificant is False

    @pytest.mark.parametrize("nutrient,threshold_conv", [
        ("energy", Decimal("4")),
        ("carbs", Decimal("0.5")),
        ("proteins", Decimal("0.5")),
        ("totalFat", Decimal("0.5")),
        ("saturatedFat", Decimal("0.2")),
        ("fiber", Decimal("0.5")),
        ("sodium", Decimal("5")),
        ("totalSugars", Decimal("0.5")),
        ("addedSugars", Decimal("0.5")),
    ])
    def test_at_threshold_is_insignificant(self, nutrient, threshold_conv):
        """At exactly the threshold, still insignificant (<=)."""
        d = evaluate_insignificance(nutrient, threshold_conv, threshold_conv, CONTEXT_CONV)
        assert d.is_insignificant is True


class TestAsymmetricColumns:
    """Conventional: BOTH per100 and per_portion must be <= threshold."""

    def test_per100_above_per_portion_below(self):
        d = evaluate_insignificance(
            "carbs",
            Decimal("0.6"),  # per100 above 0.5
            Decimal("0.3"),  # per_portion below 0.5
            CONTEXT_CONV,
        )
        assert d.is_insignificant is False

    def test_per100_below_per_portion_above(self):
        d = evaluate_insignificance(
            "proteins",
            Decimal("0.3"),
            Decimal("0.8"),
            CONTEXT_CONV,
        )
        assert d.is_insignificant is False


class TestTransFatSpecialRule:
    """Trans fat: requires (saturated + trans) <= 0.2 in BOTH columns."""

    def test_trans_and_sat_both_low_passes(self):
        d = evaluate_insignificance(
            "transFat",
            Decimal("0.05"),
            Decimal("0.05"),
            {
                "food_category": "conventional",
                "saturatedFat_per100_base": Decimal("0.05"),
                "saturatedFat_per_portion": Decimal("0.05"),
            },
        )
        assert d.is_insignificant is True

    def test_sat_plus_trans_exceeds_in_per100(self):
        d = evaluate_insignificance(
            "transFat",
            Decimal("0.1"),
            Decimal("0.1"),
            {
                "food_category": "conventional",
                "saturatedFat_per100_base": Decimal("0.15"),  # 0.15 + 0.1 = 0.25 > 0.2
                "saturatedFat_per_portion": Decimal("0.05"),
            },
        )
        assert d.is_insignificant is False

    def test_sat_plus_trans_exceeds_in_portion(self):
        d = evaluate_insignificance(
            "transFat",
            Decimal("0.1"),
            Decimal("0.1"),
            {
                "food_category": "conventional",
                "saturatedFat_per100_base": Decimal("0.05"),
                "saturatedFat_per_portion": Decimal("0.15"),
            },
        )
        assert d.is_insignificant is False

    def test_trans_above_threshold_alone(self):
        d = evaluate_insignificance(
            "transFat",
            Decimal("0.3"),
            Decimal("0.1"),
            {
                "food_category": "conventional",
                "saturatedFat_per100_base": Decimal("0"),
                "saturatedFat_per_portion": Decimal("0"),
            },
        )
        assert d.is_insignificant is False


class TestSaturatedFatThreshold:
    """Saturated fat threshold is 0.2g (not 0.5g like other macros)."""

    def test_saturated_at_0_2_is_insignificant(self):
        d = evaluate_insignificance(
            "saturatedFat",
            Decimal("0.2"),
            Decimal("0.2"),
            CONTEXT_CONV,
        )
        assert d.is_insignificant is True

    def test_saturated_at_0_3_is_significant(self):
        d = evaluate_insignificance(
            "saturatedFat",
            Decimal("0.3"),
            Decimal("0.3"),
            CONTEXT_CONV,
        )
        assert d.is_insignificant is False


class TestCategories:
    """All food categories should work."""

    @pytest.mark.parametrize("category", ["conventional", "supplement", "as_prepared"])
    def test_energy_below_4_insignificant_all_categories(self, category):
        d = evaluate_insignificance(
            "energy", Decimal("3"), Decimal("3"),
            {"food_category": category},
        )
        assert d.is_insignificant is True

    def test_get_threshold_returns_correct_for_each_category(self):
        t = _get_threshold("energy", "conventional")
        assert t == Decimal("4")
        t = _get_threshold("energy", "supplement")
        assert t == Decimal("4")
        t = _get_threshold("energy", "as_prepared")
        assert t == Decimal("4")
