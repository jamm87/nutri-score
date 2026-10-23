"""Conversiones explícitas (sin estimar valores) y datos derivados de los ingredientes."""

from __future__ import annotations

from .fvl import estimate_fvl
from .models import NutritionData
from .sweeteners import find_non_nutritive_sweeteners

# Reglamento (UE) 1169/2011, anexo I: sal = sodio × 2,5
SALT_PER_SODIUM = 2.5
# Reglamento (UE) 1169/2011, anexo XIV: 1 kcal = 4,184 kJ
KJ_PER_KCAL = 4.184


def fill_conversions(n: NutritionData, *, sodium_mg: float | None, energy_kcal: float | None) -> None:
    """Completa sal y energía SOLO con conversiones legales exactas, dejando nota."""
    if n.salt_g is None and sodium_mg is not None:
        n.salt_g = round(sodium_mg / 1000 * SALT_PER_SODIUM, 4)
        n.conversions.append(f"sal calculada desde sodio: {sodium_mg} mg × 2,5 / 1000 = {n.salt_g} g")
    if n.energy_kj is None and energy_kcal is not None:
        n.energy_kj = round(energy_kcal * KJ_PER_KCAL, 1)
        n.conversions.append(f"energía calculada desde kcal: {energy_kcal} × 4,184 = {n.energy_kj} kJ")


def derive_from_ingredients(n: NutritionData, *, fvl_override: float | None = None,
                            fvl_override_note: str = "", sweeteners_n: int | None = None) -> None:
    """% FVL (ESTIMACIÓN) y presencia de edulcorantes no nutritivos."""
    if fvl_override is not None:
        n.fvl_percent_range = (fvl_override, fvl_override)
        n.fvl_note = fvl_override_note
    else:
        est = estimate_fvl(n.ingredients)
        if est is not None:
            n.fvl_percent_range = (est.low, est.high)
            n.fvl_note = est.note
        else:
            n.fvl_note = "sin lista de ingredientes: % FVL desconocido"

    if sweeteners_n is not None:
        n.non_nutritive_sweeteners = sweeteners_n > 0
    else:
        found = find_non_nutritive_sweeteners(n.ingredients)
        n.non_nutritive_sweeteners = None if found is None else bool(found)
