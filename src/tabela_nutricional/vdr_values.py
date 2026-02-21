"""
Valores Diários de Referência (VDR/VD) — IN 75/2020, Anexo II.
Single source of truth; do not invent values.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

# VDR in same units as declaration (kcal, g, mg)
# None = VD not established (declare "**" in label)


class VDR(NamedTuple):
    value: Decimal | None
    unit: str


# Anexo II — Valores diários de referência para adultos
VDR_ENERGY = VDR(Decimal("2000"), "kcal")
VDR_CARBS = VDR(Decimal("300"), "g")
VDR_ADDED_SUGARS = VDR(Decimal("50"), "g")
VDR_TOTAL_SUGARS = VDR(None, "g")
VDR_PROTEINS = VDR(Decimal("50"), "g")
VDR_TOTAL_FAT = VDR(Decimal("55"), "g")
VDR_SATURATED_FAT = VDR(Decimal("20"), "g")
VDR_TRANS_FAT = VDR(None, "g")
VDR_FIBER = VDR(Decimal("25"), "g")
VDR_SODIUM = VDR(Decimal("2000"), "mg")

VDR_BY_NUTRIENT: dict[str, VDR] = {
    "energy": VDR_ENERGY,
    "carbs": VDR_CARBS,
    "addedSugars": VDR_ADDED_SUGARS,
    "totalSugars": VDR_TOTAL_SUGARS,
    "proteins": VDR_PROTEINS,
    "totalFat": VDR_TOTAL_FAT,
    "saturatedFat": VDR_SATURATED_FAT,
    "transFat": VDR_TRANS_FAT,
    "fiber": VDR_FIBER,
    "sodium": VDR_SODIUM,
}


def get_vdr(nutrient_key: str) -> VDR | None:
    return VDR_BY_NUTRIENT.get(nutrient_key)


def has_vdr(nutrient_key: str) -> bool:
    v = get_vdr(nutrient_key)
    return v is not None and v.value is not None
