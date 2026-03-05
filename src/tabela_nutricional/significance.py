"""
Quantidades não significativas — IN 75/2020, Anexo IV.
Separate from rounding (Anexo III). Conditional rules (e.g. trans depends on saturated+trans).

Thresholds per food category (conventional, supplement, as_prepared) as specified
in IN 75/2020, Anexo IV, Tabela 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

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


# ---------------------------------------------------------------------------
# Anexo IV — Tabela 1: Limites para declaração de quantidades não significativas
# IN 75/2020.
#
# Conventional (alimentos em geral): per 100g/100ml
# Supplement (suplementos alimentares): per dose diária declarada
# As_prepared (alimentos preparados conforme instruções): per porção preparada
#
# Nota: Para suplementos, a avaliação é por dose (não per 100g).
# Os valores abaixo são conforme a tabela oficial do Anexo IV.
# ---------------------------------------------------------------------------

# Energia (kcal): ≤ 4 kcal para todos
THRESHOLD_ENERGY = SignificanceThresholds(
    conventional=Decimal("4"),
    supplement=Decimal("4"),
    as_prepared=Decimal("4"),
)

# Carboidratos (g)
THRESHOLD_CARBS = SignificanceThresholds(
    conventional=Decimal("0.5"),
    supplement=Decimal("0.5"),
    as_prepared=Decimal("0.5"),
)

# Proteínas (g)
THRESHOLD_PROTEINS = SignificanceThresholds(
    conventional=Decimal("0.5"),
    supplement=Decimal("0.5"),
    as_prepared=Decimal("0.5"),
)

# Gorduras totais (g)
THRESHOLD_TOTAL_FAT = SignificanceThresholds(
    conventional=Decimal("0.5"),
    supplement=Decimal("0.5"),
    as_prepared=Decimal("0.5"),
)

# Gorduras saturadas (g)
THRESHOLD_SATURATED = SignificanceThresholds(
    conventional=Decimal("0.2"),
    supplement=Decimal("0.2"),
    as_prepared=Decimal("0.2"),
)

# Gorduras trans (g): ≤ 0.2 g AND (saturada + trans) ≤ 0.2 g in BOTH columns
THRESHOLD_TRANS = SignificanceThresholds(
    conventional=Decimal("0.2"),
    supplement=Decimal("0.2"),
    as_prepared=Decimal("0.2"),
)

# Fibra alimentar (g)
THRESHOLD_FIBER = SignificanceThresholds(
    conventional=Decimal("0.5"),
    supplement=Decimal("0.5"),
    as_prepared=Decimal("0.5"),
)

# Sódio (mg)
THRESHOLD_SODIUM = SignificanceThresholds(
    conventional=Decimal("5"),
    supplement=Decimal("5"),
    as_prepared=Decimal("5"),
)

# Açúcares totais (g)
THRESHOLD_TOTAL_SUGARS = SignificanceThresholds(
    conventional=Decimal("0.5"),
    supplement=Decimal("0.5"),
    as_prepared=Decimal("0.5"),
)

# Açúcares adicionados (g)
THRESHOLD_ADDED_SUGARS = SignificanceThresholds(
    conventional=Decimal("0.5"),
    supplement=Decimal("0.5"),
    as_prepared=Decimal("0.5"),
)


SIGNIFICANCE_BY_NUTRIENT: dict[str, SignificanceThresholds] = {
    "energy": THRESHOLD_ENERGY,
    "carbs": THRESHOLD_CARBS,
    "proteins": THRESHOLD_PROTEINS,
    "totalFat": THRESHOLD_TOTAL_FAT,
    "saturatedFat": THRESHOLD_SATURATED,
    "transFat": THRESHOLD_TRANS,
    "fiber": THRESHOLD_FIBER,
    "sodium": THRESHOLD_SODIUM,
    "totalSugars": THRESHOLD_TOTAL_SUGARS,
    "addedSugars": THRESHOLD_ADDED_SUGARS,
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
