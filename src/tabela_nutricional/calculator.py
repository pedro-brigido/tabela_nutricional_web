"""
ANVISA Nutritional Calculator — pipeline: aggregate, round, energy, significance, express, %VD.
RDC 429/2020, IN 75/2020. Uses: vdr_values (II), rounding (III), significance (IV), energy (XXII).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from tabela_nutricional.energy import (
    EnergyComponents,
    compute_energy,
    rounded_components_from_raw,
)
from tabela_nutricional.rounding import (
    NUTRIENT_ROUNDING_RULE,
    round_quantity,
    format_pt_br,
    RULE_ENERGY,
    RULE_MACRONUTRIENTS_G,
)
from tabela_nutricional.significance import evaluate_insignificance
from tabela_nutricional.types import (
    CalculationContext,
    CalculationResult,
    NutrientBlock,
    NutrientResult,
    NutrientFlags,
    CalculationMeta,
    IngredientInput,
    NutritionalInfo,
    normalize_ingredients,
    _to_decimal,
)
from tabela_nutricional.validators import (
    validate_ingredients_full,
    validate_portion_size as validate_portion_range,
)
from tabela_nutricional.vdr_values import get_vdr, has_vdr

# Order of nutrients in output (RDC 429)
NUTRIENT_KEYS = (
    "energy",
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


def _aggregate_raw(ingredients: list[IngredientInput]) -> dict[str, Decimal]:
    """Sum weighted nutrients over batch. Returns totals (not yet per 100)."""
    total_weight = sum(ing.quantity for ing in ingredients)
    if total_weight <= 0:
        return {}
    out: dict[str, Decimal] = {
        "carbs": Decimal("0"),
        "proteins": Decimal("0"),
        "totalFat": Decimal("0"),
        "saturatedFat": Decimal("0"),
        "transFat": Decimal("0"),
        "fiber": Decimal("0"),
        "solubleFiber": Decimal("0"),
        "sodium": Decimal("0"),
        "totalSugars": Decimal("0"),
        "addedSugars": Decimal("0"),
        "polyols": Decimal("0"),
        "erythritol": Decimal("0"),
        "ethanol": Decimal("0"),
        "organic_acids": Decimal("0"),
        "polydextrose": Decimal("0"),
    }
    for ing in ingredients:
        f = ing.quantity / Decimal("100")
        n = ing.nutritionalInfo
        out["carbs"] += n.carbs * f
        out["proteins"] += n.proteins * f
        out["totalFat"] += n.totalFat * f
        out["saturatedFat"] += n.saturatedFat * f
        out["transFat"] += n.transFat * f
        out["fiber"] += n.fiber * f
        out["solubleFiber"] += (n.solubleFiber or n.fiber) * f
        out["sodium"] += n.sodium * f
        out["totalSugars"] += n.totalSugars * f
        out["addedSugars"] += n.addedSugars * f
        out["polyols"] += n.polyols * f
        out["erythritol"] += n.erythritol * f
        out["ethanol"] += n.ethanol * f
        out["organic_acids"] += n.organic_acids * f
        out["polydextrose"] += n.polydextrose * f
    return out


def _per100_and_per_portion(
    raw_totals: dict[str, Decimal],
    total_weight: Decimal,
    portion_size: Decimal,
) -> tuple[dict[str, Decimal], dict[str, Decimal]]:
    """per100_base and per_portion (raw)."""
    if total_weight <= 0:
        return {}, {}
    factor_100 = Decimal("100") / total_weight
    per100: dict[str, Decimal] = {k: v * factor_100 for k, v in raw_totals.items()}
    portion_factor = portion_size / Decimal("100")
    per_portion: dict[str, Decimal] = {k: v * portion_factor for k, v in per100.items()}
    return per100, per_portion


def _compute_energy_for_block(block: dict[str, Decimal]) -> Decimal:
    """Set block['energy'] from rounded components (Anexo XXII)."""
    comps = rounded_components_from_raw(
        block["carbs"],
        block["proteins"],
        block["totalFat"],
        block["solubleFiber"],
        block.get("polyols", Decimal("0")),
        block.get("erythritol", Decimal("0")),
        block.get("organic_acids", Decimal("0")),
        block.get("ethanol", Decimal("0")),
        block.get("polydextrose", Decimal("0")),
    )
    return compute_energy(comps)


def _build_block_results(
    per100: dict[str, Decimal],
    per_portion: dict[str, Decimal],
    context: CalculationContext,
    for_portion: bool,
) -> NutrientBlock:
    """Build NutrientBlock (per100_base or perPortion) with significance, rounding, %VD."""
    block = per_portion if for_portion else per100
    other = per100 if for_portion else per_portion
    ctx_dict = {
        "food_category": context.food_category,
        "saturatedFat_per100_base": per100.get("saturatedFat", Decimal("0")),
        "saturatedFat_per_portion": per_portion.get("saturatedFat", Decimal("0")),
    }
    results: dict[str, NutrientResult] = {}
    for key in NUTRIENT_KEYS:
        raw = block.get(key, Decimal("0"))
        raw_other = other.get(key, Decimal("0"))
        rule = NUTRIENT_ROUNDING_RULE.get(key)
        if not rule:
            continue
        dec = evaluate_insignificance(key, raw, raw_other, ctx_dict)
        if dec.was_forced_zero:
            display = "0"
            rounded_val = Decimal("0")
            flags = NutrientFlags(
                is_insignificant=True,
                insignificance_basis="annex_iv",
                was_forced_zero=True,
            )
            notes = [dec.note] if dec.note else []
        else:
            rounded = round_quantity(raw, rule)
            rounded_val = rounded.value
            display = format_pt_br(rounded)
            flags = NutrientFlags(is_insignificant=False, was_forced_zero=False)
            notes = []
        if key == "transFat" and dec.note:
            notes.append(dec.note)
        vdr = get_vdr(key)
        unit = rule.unit
        vd_percent: int | None = None
        vd_display = ""
        if for_portion and vdr and vdr.value is not None and vdr.value > 0:
            pct = (rounded_val / vdr.value) * Decimal("100")
            vd_percent = int(pct.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if vd_percent < 1:
                vd_display = "0"
            else:
                vd_display = str(vd_percent)
        if key == "transFat" or (vdr and vdr.value is None):
            vd_display = "**"
            if "VD not established" not in notes:
                notes.append("VD not established")
        results[key] = NutrientResult(
            raw=raw,
            rounded=rounded_val,
            display=display,
            unit=unit,
            vd_percent=vd_percent,
            vd_display=vd_display,
            flags=flags,
            notes=notes,
        )
    return NutrientBlock(nutrients=results)


def calculate(
    ingredients: list[dict],
    portion_size: float | Decimal,
    *,
    food_form: str = "solid",
    unit_base: str = "100g",
    recipe_mode: str = "as_sold",
    portion_unit: str = "g",
    food_category: str = "conventional",
) -> CalculationResult | None:
    """
    Full pipeline: aggregate -> per100/perPortion -> round components -> energy ->
    significance -> express -> %VD. Returns new contract (per100_base, perPortion, meta).
    """
    warnings: list[str] = []

    try:
        ctx = CalculationContext.from_request(
            portion_size,
            food_form=food_form,
            unit_base=unit_base,
            recipe_mode=recipe_mode,
            portion_unit=portion_unit,
            food_category=food_category,
        )
    except ValueError:
        return None

    # Validate portion size range
    portion_val = validate_portion_range(ctx.portion_size)
    warnings.extend(portion_val.warnings)
    if not portion_val.is_valid:
        return None

    # Validate ingredient data
    ing_validation = validate_ingredients_full(ingredients)
    warnings.extend(ing_validation.warnings)
    if not ing_validation.is_valid:
        return None

    try:
        ing_list = normalize_ingredients(ingredients)
    except ValueError:
        return None
    if not ing_list:
        return None
    raw_totals = _aggregate_raw(ing_list)
    if not raw_totals:
        return None
    total_weight = sum(ing.quantity for ing in ing_list)
    per100, per_portion = _per100_and_per_portion(
        raw_totals, total_weight, ctx.portion_size
    )
    # Energy from rounded components (Anexo XXII)
    per100["energy"] = _compute_energy_for_block(per100)
    per_portion["energy"] = _compute_energy_for_block(per_portion)
    per100_block = _build_block_results(per100, per_portion, ctx, for_portion=False)
    per_portion_block = _build_block_results(per100, per_portion, ctx, for_portion=True)
    meta = CalculationMeta(
        context_echo={
            "food_form": ctx.food_form,
            "unit_base": ctx.unit_base,
            "portion_size": str(ctx.portion_size),
            "portion_unit": ctx.portion_unit,
            "food_category": ctx.food_category,
            "regulatory_version": "IN_75_2020_RDC_429_2020_v1",
        },
        warnings=warnings,
    )
    return CalculationResult(
        per100_base=per100_block,
        perPortion=per_portion_block,
        meta=meta,
    )


def to_legacy_output(result: CalculationResult) -> dict:
    """
    Convert new contract to legacy shape for existing frontend.
    Legacy: { per100g: { nutrient: { raw, display, vd } }, perPortion: { ... } }
    """
    def block_to_legacy(block: NutrientBlock) -> dict:
        out = {}
        for k, nr in block.nutrients.items():
            out[k] = {
                "raw": float(nr.raw),
                "display": nr.display,
                "vd": nr.vd_display if nr.vd_display != "**" else "",
            }
        return out
    return {
        "per100g": block_to_legacy(result.per100_base),
        "perPortion": block_to_legacy(result.perPortion),
        "meta": {
            "context_echo": result.meta.context_echo,
            "warnings": result.meta.warnings,
        },
    }
