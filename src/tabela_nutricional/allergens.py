"""
Declaração de alérgenos — RDC 429/2020 §3.3 e RDC 26/2015.

Lista oficial dos principais alimentos que causam alergias alimentares
conforme regulamentação ANVISA.
"""

from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# RDC 26/2015, Artigo 6 — 8 alérgenos alimentares obrigatórios
# Mais "derivados" conforme texto normativo. Cada entrada:
#   (chave_interna, rótulo_pt_br, grupo_regulatório)
# ---------------------------------------------------------------------------
ALLERGEN_REGISTRY: list[tuple[str, str, str]] = [
    ("wheat", "trigo", "cereais"),
    ("rye", "centeio", "cereais"),
    ("barley", "cevada", "cereais"),
    ("oat", "aveia", "cereais"),
    ("crustaceans", "crustáceos", "crustáceos"),
    ("eggs", "ovos", "ovos"),
    ("fish", "peixes", "peixes"),
    ("peanuts", "amendoim", "amendoim"),
    ("soy", "soja", "soja"),
    ("milk", "leite", "leite"),
    ("tree_nuts", "castanhas", "nozes e castanhas"),
    ("almonds", "amêndoas", "nozes e castanhas"),
    ("hazelnuts", "avelãs", "nozes e castanhas"),
    ("cashews", "castanha de caju", "nozes e castanhas"),
    ("brazil_nuts", "castanha-do-pará", "nozes e castanhas"),
    ("macadamias", "macadâmias", "nozes e castanhas"),
    ("walnuts", "nozes", "nozes e castanhas"),
    ("pecans", "pecãs", "nozes e castanhas"),
    ("pistachios", "pistaches", "nozes e castanhas"),
    ("latex_fruits", "látex (frutas)", "látex"),
    ("sulfites", "sulfitos", "sulfitos"),
]

# Chaves válidas para uso em checklist de alérgenos
VALID_ALLERGEN_KEYS: frozenset[str] = frozenset(
    entry[0] for entry in ALLERGEN_REGISTRY
)

# Mapeamento chave → rótulo pt-BR
ALLERGEN_LABELS: dict[str, str] = {
    entry[0]: entry[1] for entry in ALLERGEN_REGISTRY
}

# Grupos regulatórios (para display agrupado)
ALLERGEN_GROUPS: dict[str, list[str]] = {}
for key, label, group in ALLERGEN_REGISTRY:
    ALLERGEN_GROUPS.setdefault(group, []).append(key)


# RDC 26/2015, Art. 7 — Status de glúten
GlutenStatus = Literal["contains_gluten", "gluten_free"]

GLUTEN_LABELS: dict[str, str] = {
    "contains_gluten": "CONTÉM GLÚTEN",
    "gluten_free": "NÃO CONTÉM GLÚTEN",
}


def validate_allergens(allergen_keys: list[str]) -> tuple[list[str], list[str]]:
    """
    Validate a list of allergen keys.
    Returns (valid_keys, invalid_keys).
    """
    valid = []
    invalid = []
    seen = set()
    for key in allergen_keys:
        k = key.strip().lower() if isinstance(key, str) else ""
        if not k:
            continue
        if k in seen:
            continue
        seen.add(k)
        if k in VALID_ALLERGEN_KEYS:
            valid.append(k)
        else:
            invalid.append(key)
    return valid, invalid


def format_allergen_declaration(
    allergen_keys: list[str],
    gluten_status: GlutenStatus | None = None,
    custom_allergens: str | None = None,
) -> str:
    """
    Format allergen declaration per RDC 429/2020 §3.3.
    Output: "ALÉRGICOS: CONTÉM [lista]. [CONTÉM/NÃO CONTÉM GLÚTEN]."
    """
    parts = []

    # Named allergens
    labels = []
    for key in allergen_keys:
        label = ALLERGEN_LABELS.get(key)
        if label:
            labels.append(label.upper())

    if custom_allergens and custom_allergens.strip():
        labels.append(custom_allergens.strip().upper())

    if labels:
        unique = list(dict.fromkeys(labels))  # preserve order, remove dupes
        parts.append(f"ALÉRGICOS: CONTÉM {', '.join(unique)}.")

    # Gluten
    if gluten_status:
        gluten_text = GLUTEN_LABELS.get(gluten_status, "")
        if gluten_text:
            parts.append(gluten_text + ".")

    return " ".join(parts)


def validate_gluten_status(status: str | None) -> GlutenStatus | None:
    """Validate and normalize gluten status."""
    if status is None or status == "":
        return None
    s = status.strip().lower()
    s_under = s.replace(" ", "_")
    if s_under in ("contains_gluten", "contém_glúten", "contem_gluten"):
        return "contains_gluten"
    if s_under in ("gluten_free", "não_contém_glúten", "nao_contem_gluten"):
        return "gluten_free"
    return None
