"""
Arredondamento e expressão das quantidades — IN 75/2020, Anexo III.
Half-up only (0–4 down, 5–9 up). Do NOT use Python round() or :.Nf for rounding.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

# Half-up: quantize using ROUND_HALF_UP so 0.5 -> 1, 0.4 -> 0
ONE_PLACE = Decimal("0.1")
ONE_UNIT = Decimal("1")


@dataclass(frozen=True)
class RoundingRule:
    """Rule for one nutrient type (Anexo III). Unit and bands (limit_exclusive, decimals)."""

    unit: Literal["kcal", "g", "mg"]
    # List of (upper_limit_exclusive, decimal_places). None = no upper limit.
    bands: tuple[tuple[Decimal | None, int], ...]


def _half_up(value: Decimal, decimal_places: int) -> Decimal:
    """Round value using half-up (0–4 down, 5–9 up). No Python round() or string format."""
    if decimal_places == 0:
        q = ONE_UNIT
    else:
        q = Decimal("0.1") ** decimal_places
    return value.quantize(q, rounding=ROUND_HALF_UP)


def _choose_band(value: Decimal, rule: RoundingRule) -> int:
    """Return number of decimal places for value under this rule."""
    for limit, decimals in rule.bands:
        if limit is None or value < limit:
            return decimals
    return 0


# Anexo III — rules by nutrient kind (unit + bands). Energy always integer (kcal).
RULE_ENERGY = RoundingRule("kcal", ((None, 0),))
RULE_MACRONUTRIENTS_G = RoundingRule("g", ((Decimal("10"), 1), (None, 0)))  # <10g: 1 dec; >=10: integer
RULE_SODIUM = RoundingRule("mg", ((None, 0),))  # integer
RULE_TRANS_FAT = RoundingRule("g", ((Decimal("10"), 1), (None, 0)))

# Map nutrient key -> rule (rounding only; significance is Annex IV)
NUTRIENT_ROUNDING_RULE: dict[str, RoundingRule] = {
    "energy": RULE_ENERGY,
    "carbs": RULE_MACRONUTRIENTS_G,
    "proteins": RULE_MACRONUTRIENTS_G,
    "totalFat": RULE_MACRONUTRIENTS_G,
    "saturatedFat": RULE_MACRONUTRIENTS_G,
    "transFat": RULE_TRANS_FAT,
    "fiber": RULE_MACRONUTRIENTS_G,
    "sodium": RULE_SODIUM,
    "totalSugars": RULE_MACRONUTRIENTS_G,
    "addedSugars": RULE_MACRONUTRIENTS_G,
}


@dataclass(frozen=True)
class RoundedQuantity:
    """Value after Anexo III rounding (before significance forcing to 0)."""

    value: Decimal
    decimal_places: int
    unit: str


def round_quantity(value: Decimal, rule: RoundingRule) -> RoundedQuantity:
    """
    Round value according to Anexo III, half-up.
    Value must already be > significance threshold if caller uses it post-significance.
    """
    decimal_places = _choose_band(value, rule)
    rounded = _half_up(value, decimal_places)
    return RoundedQuantity(value=rounded, decimal_places=decimal_places, unit=rule.unit)


def format_pt_br(rounded: RoundedQuantity) -> str:
    """
    Expressão em pt-BR: vírgula como separador decimal; suprimir ",0" quando inteiro.
    Anexo III: quando a primeira casa decimal for 0, declarar em números inteiros.
    """
    v = rounded.value
    if rounded.decimal_places == 0:
        return str(int(v))
    # Format with correct number of decimals, then trim trailing zeros
    s = f"{v:.{rounded.decimal_places}f}".replace(".", ",")
    # Remove trailing zeros after comma (e.g. 1,50 -> 1,5 if we had 2 decimals; 2,0 -> 2)
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return s


def round_quantity_to_decimal(value: Decimal, rule: RoundingRule) -> Decimal:
    """Convenience: return only the rounded Decimal (e.g. for energy calculation)."""
    return round_quantity(value, rule).value
