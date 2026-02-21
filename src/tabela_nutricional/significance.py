"""
Quantidades não significativas — IN 75/2020, Anexo IV.
Separate from rounding (Anexo III). Conditional rules (e.g. trans depends on saturated+trans).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Literal

from tabela_nutricional.types import FoodCategory

# Thresholds: declare as "0" when value <= threshold (and any extra condition holds).
# By food category (conventional, supplement, as_prepared). IN 75/2020 Anexo IV.
# All thresholds in same unit as declaration (kcal, g, mg).


@dataclass(frozen=True)
class SignificanceThresholds:
    """Per-nutrient, per-category max value to be considered non-significant."""

    conventional: Decimal
    supplement: Decimal
    as_prepared: Decimal


# Anexo IV — table of thresholds (conventional; supplement and as_prepared may differ in full table)
THRESHOLD_ENERGY = SignificanceThresholds(Decimal("4"), Decimal("4"), Decimal("4"))
THRESHOLD_MACRO_G = SignificanceThresholds(Decimal("0.5"), Decimal("0.5"), Decimal("0.5"))
THRESHOLD_SODIUM = SignificanceThresholds(Decimal("5"), Decimal("5"), Decimal("5"))
# Trans: 0.2 g and (saturated + trans) <= 0.2 g in BOTH columns
THRESHOLD_TRANS = SignificanceThresholds(Decimal("0.2"), Decimal("0.2"), Decimal("0.2"))
THRESHOLD_SATURATED = SignificanceThresholds(Decimal("0.5"), Decimal("0.5"), Decimal("0.5"))

SIGNIFICANCE_BY_NUTRIENT: dict[str, SignificanceThresholds] = {
    "energy": THRESHOLD_ENERGY,
    "carbs": THRESHOLD_MACRO_G,
    "proteins": THRESHOLD_MACRO_G,
    "totalFat": THRESHOLD_MACRO_G,
    "saturatedFat": THRESHOLD_SATURATED,
    "transFat": THRESHOLD_TRANS,
    "fiber": THRESHOLD_MACRO_G,
    "sodium": THRESHOLD_SODIUM,
    "totalSugars": THRESHOLD_MACRO_G,
    "addedSugars": THRESHOLD_MACRO_G,
}


@dataclass
class InsignificanceDecision:
    """Result of Anexo IV evaluation for one nutrient."""

    is_insignificant: bool
    was_forced_zero: bool  # True if we declare "0" for display
    note: str | None = None  # e.g. "requires_sat_plus_trans_condition"


def _get_threshold(nutrient: str, category: FoodCategory) -> Decimal:
    t = SIGNIFICANCE_BY_NUTRIENT.get(nutrient)
    if not t:
        return Decimal("0")
    if category == "conventional":
        return t.conventional
    if category == "supplement":
        return t.supplement
    return t.as_prepared


def evaluate_insignificance(
    nutrient: str,
    per100_base_raw: Decimal,
    per_portion_raw: Decimal,
    context: dict,
) -> InsignificanceDecision:
    """
    Anexo IV: decide if quantity is non-significant (declare "0").
    For conventional foods, criteria must be met in BOTH per 100g/100ml AND per portion.
    Trans fat: also requires (saturated + trans) <= 0.2 in both columns.
    """
    category: FoodCategory = context.get("food_category", "conventional")
    threshold = _get_threshold(nutrient, category)

    # Both columns must be <= threshold for conventional (and typically for others)
    if per100_base_raw > threshold or per_portion_raw > threshold:
        return InsignificanceDecision(is_insignificant=False, was_forced_zero=False)

    # Trans fat: condition (saturated + trans) <= 0.2 in BOTH columns
    if nutrient == "transFat":
        sat_100 = context.get("saturatedFat_per100_base", Decimal("0"))
        trans_100 = per100_base_raw
        sat_portion = context.get("saturatedFat_per_portion", Decimal("0"))
        trans_portion = per_portion_raw
        if (sat_100 + trans_100) > Decimal("0.2") or (sat_portion + trans_portion) > Decimal("0.2"):
            return InsignificanceDecision(
                is_insignificant=False,
                was_forced_zero=False,
                note="requires_sat_plus_trans_condition",
            )
        return InsignificanceDecision(
            is_insignificant=True,
            was_forced_zero=True,
            note="annex_iv",
        )

    return InsignificanceDecision(
        is_insignificant=True,
        was_forced_zero=True,
        note="annex_iv",
    )
