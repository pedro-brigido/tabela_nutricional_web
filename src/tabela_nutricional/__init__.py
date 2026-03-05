"""
Tabela Nutricional — ANVISA-compliant nutritional table calculator.
RDC 429/2020, IN 75/2020.
"""

from __future__ import annotations

from tabela_nutricional.calculator import calculate, to_legacy_output
from tabela_nutricional.types import (
    CalculationResult,
    CalculationContext,
    NutrientBlock,
    NutrientResult,
    CalculationMeta,
)
from tabela_nutricional.allergens import (
    VALID_ALLERGEN_KEYS,
    ALLERGEN_LABELS,
    GLUTEN_LABELS,
    validate_allergens,
    format_allergen_declaration,
    validate_gluten_status,
)
from tabela_nutricional.validators import (
    validate_ingredients_full,
    validate_portion_size,
    validate_nutrient_ranges,
    validate_nutrient_relationships,
    ValidationResult,
)
from tabela_nutricional.portion_reference import (
    list_portion_groups,
    validate_portion_size as validate_portion_reference,
)

# Regulatory version identifier
REGULATORY_VERSION = "IN_75_2020_RDC_429_2020_v1"

__all__ = [
    "calculate",
    "to_legacy_output",
    "CalculationResult",
    "CalculationContext",
    "NutrientBlock",
    "NutrientResult",
    "CalculationMeta",
    "VALID_ALLERGEN_KEYS",
    "ALLERGEN_LABELS",
    "GLUTEN_LABELS",
    "validate_allergens",
    "format_allergen_declaration",
    "validate_gluten_status",
    "validate_ingredients_full",
    "validate_portion_size",
    "validate_nutrient_ranges",
    "validate_nutrient_relationships",
    "ValidationResult",
    "list_portion_groups",
    "validate_portion_reference",
    "REGULATORY_VERSION",
]


def calculate_legacy(ingredients: list, portion_size: float) -> dict | None:
    """
    Legacy API: same signature as before refactor. Returns { per100g, perPortion }
    for existing frontend. Uses new pipeline and converts output.
    """
    result = calculate(ingredients, portion_size)
    if result is None:
        return None
    return to_legacy_output(result)
