"""
TACO (Tabela Brasileira de Composição de Alimentos) — 4th edition.

Provides in-memory food composition lookup with accent-insensitive search.
Data source: NEPA/UNICAMP, structured from public TACO 4th edition dataset.
"""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from importlib.resources import files
from typing import TypedDict

_DATA_RESOURCE = files("tabela_nutricional").joinpath("data", "taco.json")


class TacoNutrients(TypedDict, total=False):
    energyKcal: float | None
    carbs: float | None
    proteins: float | None
    totalFat: float | None
    saturatedFat: float | None
    transFat: float | None
    fiber: float | None
    sodium: float | None
    totalSugars: float | None
    addedSugars: float | None


class TacoFood(TypedDict):
    id: int
    name: str
    category: str
    per100g: TacoNutrients


def _strip_accents(text: str) -> str:
    """Remove diacritics for accent-insensitive matching."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def _load_taco_data() -> list[TacoFood]:
    """Load TACO JSON once and cache in memory."""
    with _DATA_RESOURCE.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _build_search_index() -> list[tuple[str, int]]:
    """Build (normalized_name, index) pairs for fast searching."""
    data = _load_taco_data()
    return [
        (_strip_accents(food["name"]).lower(), idx)
        for idx, food in enumerate(data)
    ]


def search(query: str, *, limit: int = 10) -> list[TacoFood]:
    """
    Search TACO foods by name (accent-insensitive, case-insensitive).

    Ranking:
      1. Prefix matches (name starts with query)
      2. Substring matches (query appears anywhere in name)

    Returns up to `limit` results.
    """
    if not query or not query.strip():
        return []

    q = _strip_accents(query.strip()).lower()
    if len(q) < 2:
        return []

    data = _load_taco_data()
    index = _build_search_index()

    prefix_matches: list[TacoFood] = []
    substring_matches: list[TacoFood] = []

    for norm_name, idx in index:
        if norm_name.startswith(q):
            prefix_matches.append(data[idx])
        elif q in norm_name:
            substring_matches.append(data[idx])

        if len(prefix_matches) + len(substring_matches) >= limit * 3:
            break

    results = prefix_matches[:limit]
    remaining = limit - len(results)
    if remaining > 0:
        results.extend(substring_matches[:remaining])

    return results[:limit]


def get_by_id(food_id: int) -> TacoFood | None:
    """Look up a single TACO food by ID."""
    data = _load_taco_data()
    for food in data:
        if food["id"] == food_id:
            return food
    return None


def get_categories() -> list[str]:
    """Return sorted list of unique TACO food categories."""
    data = _load_taco_data()
    return sorted({food["category"] for food in data})
