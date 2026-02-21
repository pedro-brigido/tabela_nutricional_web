"""
Valor energético — IN 75/2020 Art. 12 + Anexo XXII.
Energy calculated AFTER rounding macronutrients. Factors from official table.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from tabela_nutricional.rounding import round_quantity_to_decimal, RULE_ENERGY, RULE_MACRONUTRIENTS_G

# Anexo XXII — Fatores de conversão (kcal/g)
FACTOR_CARBS = Decimal("4")
FACTOR_PROTEIN = Decimal("4")
FACTOR_FAT = Decimal("9")
FACTOR_SOLUBLE_FIBER = Decimal("2")  # fibras solúveis, exceto polidextrose
FACTOR_POLYOLS = Decimal("2.4")
FACTOR_ERYTHRITOL = Decimal("0")
FACTOR_ORGANIC_ACIDS = Decimal("3")
FACTOR_ETHANOL = Decimal("7")
FACTOR_POLYDEXTROSE = Decimal("1")  # polidextrose often 1 kcal/g in regulations


@dataclass
class EnergyComponents:
    """Rounded components (per Anexo III) used to compute energy (Anexo XXII)."""

    carbs: Decimal
    proteins: Decimal
    total_fat: Decimal
    soluble_fiber: Decimal
    polyols: Decimal = Decimal("0")
    erythritol: Decimal = Decimal("0")
    organic_acids: Decimal = Decimal("0")
    ethanol: Decimal = Decimal("0")
    polydextrose: Decimal = Decimal("0")


def compute_energy(components: EnergyComponents) -> Decimal:
    """
    IN 75/2020 Art. 12 + Anexo XXII: energy from rounded components.
    Result in kcal, rounded to integer (half-up).
    """
    total = (
        components.carbs * FACTOR_CARBS
        + components.proteins * FACTOR_PROTEIN
        + components.total_fat * FACTOR_FAT
        + components.soluble_fiber * FACTOR_SOLUBLE_FIBER
        + (components.polyols - components.erythritol) * FACTOR_POLYOLS
        + components.erythritol * FACTOR_ERYTHRITOL
        + components.organic_acids * FACTOR_ORGANIC_ACIDS
        + components.ethanol * FACTOR_ETHANOL
        + components.polydextrose * FACTOR_POLYDEXTROSE
    )
    # Energy always integer (kcal), half-up
    return total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def rounded_components_from_raw(
    carbs: Decimal,
    proteins: Decimal,
    total_fat: Decimal,
    soluble_fiber: Decimal,
    polyols: Decimal = Decimal("0"),
    erythritol: Decimal = Decimal("0"),
    organic_acids: Decimal = Decimal("0"),
    ethanol: Decimal = Decimal("0"),
    polydextrose: Decimal = Decimal("0"),
) -> EnergyComponents:
    """Apply Anexo III rounding to each component before energy calculation."""
    return EnergyComponents(
        carbs=round_quantity_to_decimal(carbs, RULE_MACRONUTRIENTS_G),
        proteins=round_quantity_to_decimal(proteins, RULE_MACRONUTRIENTS_G),
        total_fat=round_quantity_to_decimal(total_fat, RULE_MACRONUTRIENTS_G),
        soluble_fiber=round_quantity_to_decimal(soluble_fiber, RULE_MACRONUTRIENTS_G),
        polyols=round_quantity_to_decimal(polyols, RULE_MACRONUTRIENTS_G),
        erythritol=round_quantity_to_decimal(erythritol, RULE_MACRONUTRIENTS_G),
        organic_acids=round_quantity_to_decimal(organic_acids, RULE_MACRONUTRIENTS_G),
        ethanol=round_quantity_to_decimal(ethanol, RULE_MACRONUTRIENTS_G),
        polydextrose=round_quantity_to_decimal(polydextrose, RULE_MACRONUTRIENTS_G),
    )
