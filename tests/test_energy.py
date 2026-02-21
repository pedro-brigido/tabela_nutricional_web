"""Tests for energy module — IN 75/2020 Anexo XXII."""

import pytest
from decimal import Decimal

from tabela_nutricional.energy import (
    compute_energy,
    EnergyComponents,
    rounded_components_from_raw,
    FACTOR_CARBS,
    FACTOR_PROTEIN,
    FACTOR_FAT,
    FACTOR_SOLUBLE_FIBER,
)


def test_energy_from_basic_components():
    comp = EnergyComponents(
        carbs=Decimal("10"),
        proteins=Decimal("5"),
        total_fat=Decimal("2"),
        soluble_fiber=Decimal("1"),
    )
    e = compute_energy(comp)
    # 10*4 + 5*4 + 2*9 + 1*2 = 40 + 20 + 18 + 2 = 80
    assert e == Decimal("80")


def test_energy_always_integer():
    comp = EnergyComponents(
        carbs=Decimal("1.5"),
        proteins=Decimal("0.5"),
        total_fat=Decimal("0.5"),
        soluble_fiber=Decimal("0"),
    )
    e = compute_energy(comp)
    assert e == int(e)
    # 1.5*4 + 0.5*4 + 0.5*9 = 6 + 2 + 4.5 = 12.5 -> half-up 13
    assert e == Decimal("13")


def test_rounded_components_from_raw():
    comp = rounded_components_from_raw(
        Decimal("10.35"),
        Decimal("5.25"),
        Decimal("2.15"),
        Decimal("1.05"),
    )
    assert comp.carbs == Decimal("10.4")  # half-up 1 dec
    assert comp.proteins == Decimal("5.2")
    assert comp.total_fat == Decimal("2.2")
    assert comp.soluble_fiber == Decimal("1.1")


def test_energy_with_polyols_erythritol():
    comp = EnergyComponents(
        carbs=Decimal("0"),
        proteins=Decimal("0"),
        total_fat=Decimal("0"),
        soluble_fiber=Decimal("0"),
        polyols=Decimal("10"),
        erythritol=Decimal("2"),
    )
    e = compute_energy(comp)
    # (10-2)*2.4 + 2*0 = 19.2 -> 19
    assert e == Decimal("19")


def test_energy_with_ethanol():
    comp = EnergyComponents(
        carbs=Decimal("0"),
        proteins=Decimal("0"),
        total_fat=Decimal("0"),
        soluble_fiber=Decimal("0"),
        ethanol=Decimal("1"),
    )
    e = compute_energy(comp)
    assert e == Decimal("7")
