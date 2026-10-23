"""Detección de edulcorantes no nutritivos en la lista de ingredientes (solo afecta a bebidas).

Lista de edulcorantes no nutritivos del informe de bebidas del Comité Científico del
Nutri-Score (votado el 31/01/2023), tal como la recoge Open Food Facts con la propiedad
`non_nutritive_sweetener:en: yes` de su taxonomía de aditivos:
  https://github.com/openfoodfacts/openfoodfacts-server/blob/main/taxonomies/additives.txt
  (consultado el 2026-10-23)
Los polioles (sorbitol E420, eritritol E968, etc.) NO están en la lista.
"""

from __future__ import annotations

import re
import unicodedata

# E-número → nombres en español, inglés y francés (sin tildes, en minúsculas; raíces).
NON_NUTRITIVE_SWEETENERS: dict[str, tuple[str, ...]] = {
    "950": ("acesulfam",),  # acesulfamo K / acesulfame K
    "951": ("aspartam",),
    "952": ("ciclamat", "cyclamat", "acido ciclamico", "cyclamic acid", "acide cyclamique"),
    "954": ("sacarina", "saccharin"),
    "955": ("sucralos",),
    "957": ("taumatina", "thaumatin"),
    "959": ("neohesperidin", "neohespiridina", "nhdc"),
    "960": ("esteviol", "steviol", "stevia", "estevia", "rebaudiosid", "steviosid"),
    "961": ("neotam",),
    "962": ("aspartamo-acesulfamo", "aspartame-acesulfame"),
    "969": ("advantam",),
}

_E_NUMBER = re.compile(r"\be\s*-?\s*(9[56]\d)\s*[a-d]?(?:\s*\(?[ivx]+\)?)?\b")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def find_non_nutritive_sweeteners(ingredients: str | None) -> list[str] | None:
    """Devuelve los E-números detectados, [] si no hay ninguno o None si no hay ingredientes."""
    if not ingredients or not ingredients.strip():
        return None
    text = _normalize(ingredients)
    found: set[str] = set()
    for m in _E_NUMBER.finditer(text):
        if m.group(1) in NON_NUTRITIVE_SWEETENERS:
            found.add("E" + m.group(1))
    for number, names in NON_NUTRITIVE_SWEETENERS.items():
        if any(name in text for name in names):
            found.add("E" + number)
    return sorted(found)
