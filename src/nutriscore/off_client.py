"""Cliente de Open Food Facts (API v2, gratuita)."""

from __future__ import annotations

import requests

from .models import NutritionData, ProductData, Source
from .normalize import derive_from_ingredients, fill_conversions

FIELDS = ",".join([
    "code", "product_name", "product_name_es", "nutriments", "categories_tags",
    "ingredients_text", "ingredients_text_es", "ingredients_non_nutritive_sweeteners_n",
    "nutriscore", "nutrition_data_per",
])

# Sin estos datos no consideramos "completa" la información de OFF. La fibra no se exige
# porque en la UE es opcional en la etiqueta: si falta, se calcula el rango.
REQUIRED = ("energy_kj", "sugars_g", "saturated_fat_g", "salt_g", "proteins_g")


class OffError(RuntimeError):
    pass


def fetch_raw(barcode: str, cfg: dict) -> dict | None:
    """Devuelve el producto de OFF o None si no existe."""
    url = f"{cfg['base_url'].rstrip('/')}/api/v2/product/{barcode}.json"
    try:
        r = requests.get(url, params={"fields": FIELDS},
                         headers={"User-Agent": cfg["user_agent"]}, timeout=cfg.get("timeout_s", 10))
    except requests.RequestException as e:
        raise OffError(f"No se pudo consultar Open Food Facts: {e}") from e
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise OffError(f"Open Food Facts respondió {r.status_code}")
    data = r.json()
    if data.get("status") != 1 or "product" not in data:
        return None
    return data["product"]


def _num(nutriments: dict, key: str) -> float | None:
    v = nutriments.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_product(p: dict, barcode: str) -> ProductData:
    nm = p.get("nutriments") or {}
    n = NutritionData(
        energy_kj=_num(nm, "energy-kj_100g"),
        sugars_g=_num(nm, "sugars_100g"),
        fat_g=_num(nm, "fat_100g"),
        saturated_fat_g=_num(nm, "saturated-fat_100g"),
        salt_g=_num(nm, "salt_100g"),
        proteins_g=_num(nm, "proteins_100g"),
        fiber_g=_num(nm, "fiber_100g"),
        ingredients=p.get("ingredients_text_es") or p.get("ingredients_text") or None,
    )
    if n.energy_kj is None and _num(nm, "energy_100g") is not None:
        # En OFF, energy_100g siempre está en kJ.
        n.energy_kj = _num(nm, "energy_100g")
    sodium_g = _num(nm, "sodium_100g")
    fill_conversions(n, sodium_mg=None if sodium_g is None else sodium_g * 1000,
                     energy_kcal=_num(nm, "energy-kcal_100g"))

    fvl_off = _num(nm, "fruits-vegetables-legumes-estimate-from-ingredients_100g")
    derive_from_ingredients(
        n,
        fvl_override=fvl_off,
        fvl_override_note="ESTIMACIÓN de Open Food Facts desde ingredientes" if fvl_off is not None else "",
        sweeteners_n=p.get("ingredients_non_nutritive_sweeteners_n"),
    )

    grade = None
    ns = p.get("nutriscore") or {}
    if isinstance(ns, dict):
        grade = (ns.get("2023") or {}).get("grade")
    return ProductData(
        source=Source.OFF,
        nutrition=n,
        barcode=barcode,
        name=p.get("product_name_es") or p.get("product_name"),
        off_categories=list(p.get("categories_tags") or []),
        off_grade_2023=grade.upper() if isinstance(grade, str) and len(grade) == 1 else None,
    )


def missing_required(n: NutritionData) -> list[str]:
    return [f for f in REQUIRED if getattr(n, f) is None]


def fetch(barcode: str, cfg: dict) -> ProductData | None:
    raw = fetch_raw(barcode, cfg)
    return None if raw is None else parse_product(raw, barcode)
