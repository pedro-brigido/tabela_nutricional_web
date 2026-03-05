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


# ---------------------------------------------------------------------------
# IN 75/2020, Anexo V — Porções de referência (valor em gramas ou ml)
# Grupos de alimentos conforme tabela oficial.
# ---------------------------------------------------------------------------
PORTION_REFERENCES: list[PortionReference] = [
    # I — Produtos de panificação, cereais, leguminosas, raízes, tubérculos e derivados
    PortionReference("I_A", "Pães", Decimal("50"), "1 unidade / 2 fatias"),
    PortionReference("I_B", "Bolos sem recheio", Decimal("60"), "1 fatia"),
    PortionReference("I_C", "Bolos com recheio", Decimal("60"), "1 fatia"),
    PortionReference("I_D", "Arroz, massas, farinhas, féculas", Decimal("80"), "4 colheres de sopa"),
    PortionReference("I_E", "Cereais matinais, aveia, granola", Decimal("30"), "1 xícara"),
    PortionReference("I_F", "Biscoitos doces e salgados", Decimal("30"), "6 unidades"),
    PortionReference("I_G", "Leguminosas (feijão, lentilha, grão de bico)", Decimal("55"), "1 concha"),
    PortionReference("I_H", "Batata, mandioca, inhame (cozidos)", Decimal("85"), "1 unidade"),

    # II — Verduras, hortaliças e conservas vegetais
    PortionReference("II_A", "Verduras e hortaliças frescas", Decimal("80"), "1 pires"),
    PortionReference("II_B", "Conservas vegetais", Decimal("25"), "1 ½ colher de sopa"),

    # III — Frutas, sucos, néctares e refrescos de frutas
    PortionReference("III_A", "Frutas frescas", Decimal("130"), "1 porção"),
    PortionReference("III_B", "Frutas secas / desidratadas", Decimal("25"), "½ xícara"),
    PortionReference("III_C", "Sucos e néctares (ml)", Decimal("200"), "1 copo"),

    # IV — Leite e derivados
    PortionReference("IV_A", "Leite fluido (ml)", Decimal("200"), "1 copo"),
    PortionReference("IV_B", "Leite em pó", Decimal("26"), "2 colheres de sopa"),
    PortionReference("IV_C", "Queijos (tipo minas, prato)", Decimal("30"), "1 ½ fatia"),
    PortionReference("IV_D", "Iogurtes e bebidas lácteas", Decimal("170"), "1 pote"),
    PortionReference("IV_E", "Creme de leite, requeijão", Decimal("30"), "1 colher de sopa"),

    # V — Carnes e ovos
    PortionReference("V_A", "Carnes bovinas, suínas, aves", Decimal("80"), "1 bife / filé"),
    PortionReference("V_B", "Peixes e frutos do mar", Decimal("80"), "1 filé"),
    PortionReference("V_C", "Ovos", Decimal("50"), "1 unidade"),
    PortionReference("V_D", "Embutidos (presunto, salsicha)", Decimal("40"), "2 fatias / 1 unidade"),

    # VI — Óleos, gorduras e sementes oleaginosas
    PortionReference("VI_A", "Óleos vegetais", Decimal("8"), "1 colher de sopa"),
    PortionReference("VI_B", "Azeite de oliva", Decimal("8"), "1 colher de sopa"),
    PortionReference("VI_C", "Manteiga, margarina", Decimal("10"), "1 colher de chá"),
    PortionReference("VI_D", "Oleaginosas (castanhas, nozes, amêndoas)", Decimal("15"), "1 colher de sopa"),

    # VII — Açúcares e produtos com energia proveniente de açúcares
    PortionReference("VII_A", "Açúcar, mel, geleia", Decimal("20"), "1 colher de sopa"),
    PortionReference("VII_B", "Chocolates", Decimal("25"), "½ tablete / 1 porção"),
    PortionReference("VII_C", "Balas, doces e sobremesas", Decimal("20"), "1 unidade"),
    PortionReference("VII_D", "Sorvetes", Decimal("60"), "1 bola"),

    # VIII — Molhos, temperos prontos, caldos, sopas, pratos prontos
    PortionReference("VIII_A", "Molho de tomate, maionese, mostarda", Decimal("12"), "1 colher de sopa"),
    PortionReference("VIII_B", "Temperos prontos, caldos concentrados", Decimal("5"), "½ colher de chá"),
    PortionReference("VIII_C", "Sopas e caldos (preparados)", Decimal("250"), "1 prato"),
    PortionReference("VIII_D", "Pratos prontos congelados", Decimal("300"), "1 porção"),
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


def list_portion_groups() -> list[dict]:
    """Return list of portion reference groups for UI dropdown."""
    return [
        {
            "code": ref.group_code,
            "name": ref.group_name,
            "portion_g": str(ref.portion_g),
            "household_measure": ref.household_measure,
        }
        for ref in PORTION_REFERENCES
    ]
