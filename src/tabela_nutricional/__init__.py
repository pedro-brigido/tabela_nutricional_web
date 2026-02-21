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

__all__ = [
    "calculate",
    "to_legacy_output",
    "CalculationResult",
    "CalculationContext",
    "NutrientBlock",
    "NutrientResult",
    "CalculationMeta",
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
