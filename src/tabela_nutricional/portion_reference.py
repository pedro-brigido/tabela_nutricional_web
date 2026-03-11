"""
Porções de referência — IN 75/2020, Anexo V.

Tabela de medidas caseiras e porções de referência por grupo de alimentos.
Utilizado para validação (warning) quando a porção informada difere da
porção de referência regulatória.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PortionReference:
    """Porção de referência para um grupo de alimentos (Anexo V)."""
    group_code: str
    group_name: str
    portion_g: Decimal
    household_measure: str
    food_form: str = "solid"  # "solid", "liquid", or "both"


# ---------------------------------------------------------------------------
# IN 75/2020, Anexo V — Porções de referência (valor em gramas ou ml)
# Grupos de alimentos conforme tabela oficial.
# ---------------------------------------------------------------------------
PORTION_REFERENCES: list[PortionReference] = [
    # I — Produtos de panificação, cereais, leguminosas, raízes, tubérculos e derivados
    PortionReference("I_A", "Pães", Decimal("50"), "1 unidade / 2 fatias", "solid"),
    PortionReference("I_B", "Bolos sem recheio", Decimal("60"), "1 fatia", "solid"),
    PortionReference("I_C", "Bolos com recheio", Decimal("60"), "1 fatia", "solid"),
    PortionReference("I_D", "Arroz, massas, farinhas, féculas", Decimal("80"), "4 colheres de sopa", "solid"),
    PortionReference("I_E", "Cereais matinais, aveia, granola", Decimal("30"), "1 xícara", "solid"),
    PortionReference("I_F", "Biscoitos doces e salgados", Decimal("30"), "6 unidades", "solid"),
    PortionReference("I_G", "Leguminosas (feijão, lentilha, grão de bico)", Decimal("55"), "1 concha", "solid"),
    PortionReference("I_H", "Batata, mandioca, inhame (cozidos)", Decimal("85"), "1 unidade", "solid"),

    # II — Verduras, hortaliças e conservas vegetais
    PortionReference("II_A", "Verduras e hortaliças frescas", Decimal("80"), "1 pires", "solid"),
    PortionReference("II_B", "Conservas vegetais", Decimal("25"), "1 ½ colher de sopa", "solid"),

    # III — Frutas, sucos, néctares e refrescos de frutas
    PortionReference("III_A", "Frutas frescas", Decimal("130"), "1 porção", "solid"),
    PortionReference("III_B", "Frutas secas / desidratadas", Decimal("25"), "½ xícara", "solid"),
    PortionReference("III_C", "Sucos e néctares", Decimal("200"), "1 copo", "liquid"),

    # IV — Leite e derivados
    PortionReference("IV_A", "Leite fluido", Decimal("200"), "1 copo", "liquid"),
    PortionReference("IV_B", "Leite em pó", Decimal("26"), "2 colheres de sopa", "solid"),
    PortionReference("IV_C", "Queijos (tipo minas, prato)", Decimal("30"), "1 ½ fatia", "solid"),
    PortionReference("IV_D", "Iogurtes e bebidas lácteas", Decimal("170"), "1 pote", "liquid"),
    PortionReference("IV_E", "Creme de leite, requeijão", Decimal("30"), "1 colher de sopa", "both"),

    # V — Carnes e ovos
    PortionReference("V_A", "Carnes bovinas, suínas, aves", Decimal("80"), "1 bife / filé", "solid"),
    PortionReference("V_B", "Peixes e frutos do mar", Decimal("80"), "1 filé", "solid"),
    PortionReference("V_C", "Ovos", Decimal("50"), "1 unidade", "solid"),
    PortionReference("V_D", "Embutidos (presunto, salsicha)", Decimal("40"), "2 fatias / 1 unidade", "solid"),

    # VI — Óleos, gorduras e sementes oleaginosas
    PortionReference("VI_A", "Óleos vegetais", Decimal("8"), "1 colher de sopa", "both"),
    PortionReference("VI_B", "Azeite de oliva", Decimal("8"), "1 colher de sopa", "both"),
    PortionReference("VI_C", "Manteiga, margarina", Decimal("10"), "1 colher de chá", "solid"),
    PortionReference("VI_D", "Oleaginosas (castanhas, nozes, amêndoas)", Decimal("15"), "1 colher de sopa", "solid"),

    # VII — Açúcares e produtos com energia proveniente de açúcares
    PortionReference("VII_A", "Açúcar, mel, geleia", Decimal("20"), "1 colher de sopa", "solid"),
    PortionReference("VII_B", "Chocolates", Decimal("25"), "½ tablete / 1 porção", "solid"),
    PortionReference("VII_C", "Balas, doces e sobremesas", Decimal("20"), "1 unidade", "solid"),
    PortionReference("VII_D", "Sorvetes", Decimal("60"), "1 bola", "solid"),

    # VIII — Molhos, temperos prontos, caldos, sopas, pratos prontos
    PortionReference("VIII_A", "Molho de tomate, maionese, mostarda", Decimal("12"), "1 colher de sopa", "both"),
    PortionReference("VIII_B", "Temperos prontos, caldos concentrados", Decimal("5"), "½ colher de chá", "both"),
    PortionReference("VIII_C", "Sopas e caldos (preparados)", Decimal("250"), "1 prato", "liquid"),
    PortionReference("VIII_D", "Pratos prontos congelados", Decimal("300"), "1 porção", "solid"),
]

# Dict for quick lookup by group_code
PORTION_BY_CODE: dict[str, PortionReference] = {
    ref.group_code: ref for ref in PORTION_REFERENCES
}


# Tolerância de ±30% para considerar a porção informada como compatível
PORTION_TOLERANCE = Decimal("0.30")


def validate_portion_size(
    portion_size: Decimal,
    group_code: str | None = None,
) -> dict:
    """
    Validate portion size against regulatory reference.
    Returns dict with:
      - is_valid: bool
      - reference: PortionReference | None
      - warning: str | None (if portion differs significantly from reference)
    """
    if group_code is None:
        return {"is_valid": True, "reference": None, "warning": None}

    ref = PORTION_BY_CODE.get(group_code)
    if ref is None:
        return {"is_valid": True, "reference": None, "warning": None}

    lower = ref.portion_g * (1 - PORTION_TOLERANCE)
    upper = ref.portion_g * (1 + PORTION_TOLERANCE)

    if lower <= portion_size <= upper:
        return {"is_valid": True, "reference": ref, "warning": None}

    return {
        "is_valid": False,
        "reference": ref,
        "warning": (
            f"Porção informada ({portion_size}g) difere da porção de referência "
            f"para '{ref.group_name}' ({ref.portion_g}g ± 30%). "
            f"Medida caseira de referência: {ref.household_measure}."
        ),
    }


def list_portion_groups(food_form: str | None = None) -> list[dict]:
    """Return list of portion reference groups for UI dropdown.

    Args:
        food_form: Optional filter — "solid" or "liquid". Groups classified
                   as "both" are always included. If *None*, all groups are
                   returned.
    """
    refs = PORTION_REFERENCES
    if food_form in ("solid", "liquid"):
        refs = [r for r in refs if r.food_form in (food_form, "both")]
    return [
        {
            "code": ref.group_code,
            "name": ref.group_name,
            "portion_g": str(ref.portion_g),
            "household_measure": ref.household_measure,
            "food_form": ref.food_form,
        }
        for ref in refs
    ]
