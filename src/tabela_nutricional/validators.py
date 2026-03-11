"""
Validação de dados de entrada — RDC 429/2020, IN 75/2020.

Validates nutritional plausibility, nutrient relationships, and portion ranges.
Returns warnings (non-blocking) for implausible data and errors for impossible data.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from tabela_nutricional.types import NutritionalInfo, _to_decimal

# ---------------------------------------------------------------------------
# Nutrient range limits per 100g/100ml (plausibility checks)
# ---------------------------------------------------------------------------
NUTRIENT_RANGES: dict[str, tuple[Decimal, Decimal]] = {
    "carbs": (Decimal("0"), Decimal("100")),
    "proteins": (Decimal("0"), Decimal("100")),
    "totalFat": (Decimal("0"), Decimal("100")),
    "saturatedFat": (Decimal("0"), Decimal("100")),
    "transFat": (Decimal("0"), Decimal("100")),
    "fiber": (Decimal("0"), Decimal("100")),
    "sodium": (Decimal("0"), Decimal("100000")),  # mg
    "totalSugars": (Decimal("0"), Decimal("100")),
    "addedSugars": (Decimal("0"), Decimal("100")),
    "energyKcal": (Decimal("0"), Decimal("900")),
}

# Max plausible portion size in g or ml
PORTION_SIZE_MIN = Decimal("0.1")
PORTION_SIZE_MAX = Decimal("10000")

# Max plausible ingredient quantity in g
INGREDIENT_QTY_MIN = Decimal("0.001")
INGREDIENT_QTY_MAX = Decimal("100000")


class ValidationResult:
    """Container for validation errors and warnings."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def validate_nutrient_ranges(data: dict[str, Any], label: str = "") -> ValidationResult:
    """
    Validate that nutrient values are within plausible ranges per 100g/100ml.
    Returns errors for negative values, warnings for extreme values.
    """
    result = ValidationResult()
    prefix = f"{label}: " if label else ""

    for field, (min_val, max_val) in NUTRIENT_RANGES.items():
        raw = data.get(field)
        if raw is None:
            continue
        val = _to_decimal(raw)
        if val < min_val:
            result.add_error(
                f"{prefix}{field} não pode ser negativo ({val})."
            )
        elif val > max_val:
            result.add_warning(
                f"{prefix}{field} muito elevado ({val}). "
                f"Faixa esperada: {min_val}–{max_val}."
            )

    return result


def validate_nutrient_relationships(ni: NutritionalInfo, label: str = "") -> ValidationResult:
    """
    Validate logical relationships between nutrients.
    e.g., saturatedFat ≤ totalFat, addedSugars ≤ totalSugars ≤ carbs.
    """
    result = ValidationResult()
    prefix = f"{label}: " if label else ""

    if ni.saturatedFat > ni.totalFat:
        result.add_warning(
            f"{prefix}Gordura saturada ({ni.saturatedFat}g) > Gordura total ({ni.totalFat}g)."
        )

    if ni.transFat > ni.totalFat:
        result.add_warning(
            f"{prefix}Gordura trans ({ni.transFat}g) > Gordura total ({ni.totalFat}g)."
        )

    if ni.addedSugars > ni.totalSugars:
        result.add_warning(
            f"{prefix}Açúcares adicionados ({ni.addedSugars}g) > Açúcares totais ({ni.totalSugars}g)."
        )

    if ni.totalSugars > ni.carbs:
        result.add_warning(
            f"{prefix}Açúcares totais ({ni.totalSugars}g) > Carboidratos ({ni.carbs}g)."
        )

    # Macro sum plausibility: carbs + proteins + totalFat + fiber should be ≤ 100g per 100g
    macro_sum = ni.carbs + ni.proteins + ni.totalFat + ni.fiber
    if macro_sum > Decimal("105"):  # small tolerance
        result.add_warning(
            f"{prefix}Soma dos macronutrientes ({macro_sum}g/100g) excede 100g. "
            "Verifique os valores informados."
        )

    return result


def validate_portion_size(portion_size: Decimal) -> ValidationResult:
    """Validate portion size range."""
    result = ValidationResult()
    if portion_size < PORTION_SIZE_MIN:
        result.add_error(
            f"Porção ({portion_size}g) abaixo do mínimo permitido ({PORTION_SIZE_MIN}g)."
        )
    elif portion_size > PORTION_SIZE_MAX:
        result.add_warning(
            f"Porção ({portion_size}g) acima do limite esperado ({PORTION_SIZE_MAX}g)."
        )
    return result


def validate_ingredient_quantity(qty: Decimal, label: str = "") -> ValidationResult:
    """Validate ingredient quantity range."""
    result = ValidationResult()
    prefix = f"{label}: " if label else ""
    if qty < INGREDIENT_QTY_MIN:
        result.add_error(
            f"{prefix}Quantidade ({qty}g) abaixo do mínimo permitido ({INGREDIENT_QTY_MIN}g)."
        )
    elif qty > INGREDIENT_QTY_MAX:
        result.add_warning(
            f"{prefix}Quantidade ({qty}g) muito elevada."
        )
    return result


def validate_ingredients_full(
    ingredients: list[dict[str, Any]],
) -> ValidationResult:
    """
    Full validation of an ingredient list.
    Returns combined errors and warnings.
    """
    result = ValidationResult()

    for i, ing in enumerate(ingredients):
        label = ing.get("name", f"Ingrediente #{i + 1}")
        ni_data = ing.get("nutritionalInfo", {})

        # Validate quantity
        qty = _to_decimal(ing.get("quantity", 0))
        qty_result = validate_ingredient_quantity(qty, label)
        result.errors.extend(qty_result.errors)
        result.warnings.extend(qty_result.warnings)

        # Validate ranges
        range_result = validate_nutrient_ranges(ni_data, label)
        result.errors.extend(range_result.errors)
        result.warnings.extend(range_result.warnings)

        # Validate relationships
        ni = NutritionalInfo.from_dict(ni_data)
        rel_result = validate_nutrient_relationships(ni, label)
        result.warnings.extend(rel_result.warnings)

    return result
