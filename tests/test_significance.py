"""Tests for significance module — IN 75/2020 Anexo IV."""

import pytest
from decimal import Decimal

from tabela_nutricional.significance import (
    evaluate_insignificance,
    SIGNIFICANCE_BY_NUTRIENT,
    THRESHOLD_ENERGY,
    THRESHOLD_TRANS,
)


def test_energy_below_4_insignificant():
    d = evaluate_insignificance(
        "energy",
        Decimal("3"),
        Decimal("2"),
        {"food_category": "conventional"},
    )
    assert d.is_insignificant is True
    assert d.was_forced_zero is True


def test_energy_above_4_significant():
    d = evaluate_insignificance(
        "energy",
        Decimal("5"),
        Decimal("3"),
        {"food_category": "conventional"},
    )
    assert d.is_insignificant is False
    assert d.was_forced_zero is False


def test_both_columns_must_be_below_threshold():
    """Conventional: both per100 and per_portion must be <= threshold."""
    d = evaluate_insignificance(
        "sodium",
        Decimal("3"),   # per100 below 5
        Decimal("6"),   # per portion above 5
        {"food_category": "conventional"},
    )
    assert d.is_insignificant is False


def test_trans_fat_requires_sat_plus_trans_condition():
    """Trans: (saturated + trans) <= 0.2 in BOTH columns."""
    # Both 0.1 trans, but sat 0.2 in one column -> sum 0.3 > 0.2
    d = evaluate_insignificance(
        "transFat",
        Decimal("0.1"),
        Decimal("0.1"),
        {
            "food_category": "conventional",
            "saturatedFat_per100_base": Decimal("0.2"),
            "saturatedFat_per_portion": Decimal("0.05"),
        },
    )
    assert d.is_insignificant is False


def test_trans_fat_insignificant_when_both_under():
    d = evaluate_insignificance(
        "transFat",
        Decimal("0.1"),
        Decimal("0.1"),
        {
            "food_category": "conventional",
            "saturatedFat_per100_base": Decimal("0.05"),
            "saturatedFat_per_portion": Decimal("0.05"),
        },
    )
    assert d.is_insignificant is True
    assert d.was_forced_zero is True


def test_supplement_category_uses_supplement_threshold():
    d = evaluate_insignificance(
        "energy",
        Decimal("3"),
        Decimal("3"),
        {"food_category": "supplement"},
    )
    assert d.is_insignificant is True
