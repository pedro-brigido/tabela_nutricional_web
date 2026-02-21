"""
Input/output models and validation for ANVISA nutritional calculator.
RDC 429/2020, IN 75/2020. Normalizes to Decimal for rounding consistency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

# --- Literal types (contract) ---
FoodForm = Literal["solid", "liquid"]
UnitBase = Literal["100g", "100ml"]
RecipeMode = Literal["as_sold", "as_prepared"]
PortionUnit = Literal["g", "ml"]
FoodCategory = Literal["conventional", "supplement", "as_prepared"]

# Required keys per 100g/100ml (RDC 429)
NUTRITIONAL_INFO_REQUIRED = (
    "carbs",
    "proteins",
    "totalFat",
    "saturatedFat",
    "transFat",
    "fiber",
    "sodium",
    "totalSugars",
    "addedSugars",
)

# Optional keys for energy (Anexo XXII)
NUTRITIONAL_INFO_OPTIONAL_ENERGY = (
    "polyols",
    "erythritol",
    "ethanol",
    "organic_acids",
    "polydextrose",
    "solubleFiber",
)


def _to_decimal(value: Any) -> Decimal:
    """Normalize to Decimal; 0 on invalid/None."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    s = str(value).strip().replace(",", ".")
    try:
        return Decimal(s) if s else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


@dataclass
class CalculationContext:
    """Global context for a calculation (IN 75/2020, RDC 429)."""

    food_form: FoodForm = "solid"
    unit_base: UnitBase = "100g"
    recipe_mode: RecipeMode = "as_sold"
    portion_size: Decimal = field(default_factory=lambda: Decimal("100"))
    portion_unit: PortionUnit = "g"
    food_category: FoodCategory = "conventional"
    density_g_per_ml: Decimal | None = None
    serving_validation: bool = False

    def __post_init__(self) -> None:
        if self.portion_size <= 0:
            raise ValueError("portion_size must be > 0")
        if self.portion_unit not in ("g", "ml"):
            raise ValueError("portion_unit must be 'g' or 'ml'")
        if self.unit_base not in ("100g", "100ml"):
            raise ValueError("unit_base must be '100g' or '100ml'")

    @classmethod
    def from_request(
        cls,
        portion_size: float | Decimal | str,
        *,
        food_form: str = "solid",
        unit_base: str = "100g",
        recipe_mode: str = "as_sold",
        portion_unit: str = "g",
        food_category: str = "conventional",
        density_g_per_ml: float | Decimal | None = None,
        serving_validation: bool = False,
    ) -> "CalculationContext":
        return cls(
            food_form=food_form if food_form in ("solid", "liquid") else "solid",
            unit_base=unit_base if unit_base in ("100g", "100ml") else "100g",
            recipe_mode=recipe_mode if recipe_mode in ("as_sold", "as_prepared") else "as_sold",
            portion_size=_to_decimal(portion_size),
            portion_unit=portion_unit if portion_unit in ("g", "ml") else "g",
            food_category=(
                food_category
                if food_category in ("conventional", "supplement", "as_prepared")
                else "conventional"
            ),
            density_g_per_ml=_to_decimal(density_g_per_ml) if density_g_per_ml is not None else None,
            serving_validation=bool(serving_validation),
        )


@dataclass
class NutritionalInfo:
    """Per 100g or 100ml (conforme unit_base). All values as Decimal."""

    carbs: Decimal
    proteins: Decimal
    totalFat: Decimal
    saturatedFat: Decimal
    transFat: Decimal
    fiber: Decimal
    sodium: Decimal
    totalSugars: Decimal
    addedSugars: Decimal
    # Optional for energy (Anexo XXII)
    polyols: Decimal = Decimal("0")
    erythritol: Decimal = Decimal("0")
    ethanol: Decimal = Decimal("0")
    organic_acids: Decimal = Decimal("0")
    polydextrose: Decimal = Decimal("0")
    solubleFiber: Decimal = Decimal("0")
    energyKcal: Decimal | None = None  # if provided, may be overridden by calculated

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NutritionalInfo":
        if not data:
            return cls(
                carbs=Decimal("0"),
                proteins=Decimal("0"),
                totalFat=Decimal("0"),
                saturatedFat=Decimal("0"),
                transFat=Decimal("0"),
                fiber=Decimal("0"),
                sodium=Decimal("0"),
                totalSugars=Decimal("0"),
                addedSugars=Decimal("0"),
            )
        def get(k: str, default: Any = 0) -> Decimal:
            return _to_decimal(data.get(k, default))

        return cls(
            carbs=get("carbs"),
            proteins=get("proteins"),
            totalFat=get("totalFat"),
            saturatedFat=get("saturatedFat"),
            transFat=get("transFat"),
            fiber=get("fiber"),
            sodium=get("sodium"),
            totalSugars=get("totalSugars"),
            addedSugars=get("addedSugars"),
            polyols=get("polyols"),
            erythritol=get("erythritol"),
            ethanol=get("ethanol"),
            organic_acids=get("organic_acids"),
            polydextrose=get("polydextrose"),
            solubleFiber=get("solubleFiber") or get("fiber"),
            energyKcal=_to_decimal(data["energyKcal"]) if data.get("energyKcal") is not None else None,
        )


@dataclass
class IngredientInput:
    """One ingredient: quantity (g or ml) + nutritionalInfo per 100g/100ml."""

    quantity: Decimal
    nutritionalInfo: NutritionalInfo

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IngredientInput":
        qty = _to_decimal(data.get("quantity", 0))
        nutri = NutritionalInfo.from_dict(data.get("nutritionalInfo"))
        return cls(quantity=qty, nutritionalInfo=nutri)


# --- Output types ---


@dataclass
class NutrientFlags:
    is_insignificant: bool = False
    insignificance_basis: Literal["annex_iv"] | None = None
    was_forced_zero: bool = False


@dataclass
class NutrientResult:
    """One nutrient in per100_base or perPortion (new contract)."""

    raw: Decimal
    rounded: Decimal
    display: str
    unit: str
    vd_percent: int | None
    vd_display: str
    flags: NutrientFlags
    notes: list[str] = field(default_factory=list)


@dataclass
class NutrientBlock:
    """Set of nutrient results (per100_base or perPortion)."""

    nutrients: dict[str, NutrientResult] = field(default_factory=dict)


@dataclass
class CalculationMeta:
    context_echo: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CalculationResult:
    """Full result (new contract)."""

    per100_base: NutrientBlock
    perPortion: NutrientBlock
    meta: CalculationMeta


def normalize_ingredients(raw_ingredients: list[dict[str, Any]]) -> list[IngredientInput]:
    """Validate and normalize list of ingredients from API/Excel."""
    out: list[IngredientInput] = []
    for i, raw in enumerate(raw_ingredients):
        try:
            out.append(IngredientInput.from_dict(raw))
        except (TypeError, ValueError) as e:
            raise ValueError(f"Ingredient index {i}: {e}") from e
    return out
