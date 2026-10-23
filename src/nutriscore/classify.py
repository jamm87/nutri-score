"""Clasificación del producto en una categoría del algoritmo 2023.

Reglas deterministas a partir de las categorías de Open Food Facts, como hace la
implementación de referencia (lib/ProductOpener/Food.pm y Config_off.pm de
openfoodfacts-server, consultado el 2026-10-23). Si no hay categorías de OFF se usa la
sugerencia de Gemini, que solo se acepta sin preguntar si su confianza es alta. Si la
categoría es dudosa, el CLI pregunta al usuario.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Category

# Categorías de OFF a las que no se aplica el Nutri-Score.
EXEMPT = (
    "en:alcoholic-beverages", "en:baby-foods", "en:baby-milks", "en:chewing-gum",
    "en:food-additives", "en:dietary-supplements", "en:meal-replacements", "en:salts",
    "en:spices", "en:sugar-substitutes", "en:vinegars", "en:non-food-products",
)
BEVERAGE_ROOTS = ("en:beverages", "en:beverage-preparations")
NOT_BEVERAGES = ("en:meal-replacement", "en:soups")
# 2023: leche, bebidas lácteas y bebidas vegetales pasan a ser bebidas.
ALWAYS_BEVERAGES = (
    "en:milks", "en:plant-based-milk-alternatives", "en:dairy-drinks", "en:plant-based-beverages",
    "en:tea-based-beverages", "en:iced-teas", "en:herbal-tea-beverages", "en:coffee-beverages",
    "en:coffee-drinks", "en:coffees", "en:herbal-teas", "en:teas",
)
WATER = ("en:spring-waters",)
FLAVOURED_WATER = ("en:flavored-waters", "en:flavoured-waters")
CHEESE = ("en:cheeses",)
NOT_CHEESE = ("fr:fromages-blancs",)
# OFF usa además códigos del Sistema Armonizado para frutos secos y semillas;
# aquí usamos las categorías equivalentes más comunes.
FATS = ("en:fats", "en:creams", "en:seeds", "en:nuts", "en:peanuts", "en:nut-butters")
NOT_FATS = ("en:chestnuts",)
# Indicios de carne roja (vacuno, cerdo, cordero, caballo, caza). Por sí solos no bastan:
# "embutidos" puede ser de ave, así que se pregunta.
RED_MEAT_HINTS = ("beef", "veal", "pork", "lamb", "mutton", "horse", "venison", "game-meat", "boar")
MEAT_HINTS = ("en:meats", "en:prepared-meats", "en:sausages", "en:hams", "en:charcuteries")

GEMINI_TO_CATEGORY = {c.value: c for c in Category}


@dataclass
class Classification:
    category: Category
    certain: bool
    reason: str
    candidates: list[Category] = field(default_factory=list)
    exempt: str | None = None


def _has(tags: list[str], wanted: tuple[str, ...]) -> bool:
    return any(t in tags for t in wanted)


def classify_from_off(tags: list[str]) -> Classification | None:
    if not tags:
        return None
    for t in EXEMPT:
        if t in tags:
            return Classification(Category.GENERAL, True, f"categoría exenta de Nutri-Score ({t})", exempt=t)
    if _has(tags, WATER) and not _has(tags, FLAVOURED_WATER):
        return Classification(Category.WATER, True, "OFF: agua de manantial/mineral")
    is_bev = (_has(tags, BEVERAGE_ROOTS) and not _has(tags, NOT_BEVERAGES)) or _has(tags, ALWAYS_BEVERAGES)
    if is_bev:
        return Classification(Category.BEVERAGE, True, "OFF: bebida (incluye leche y bebidas vegetales en 2023)")
    if _has(tags, CHEESE) and not _has(tags, NOT_CHEESE):
        return Classification(Category.CHEESE, True, "OFF: queso")
    if _has(tags, FATS) and not _has(tags, NOT_FATS):
        return Classification(Category.FATS, True, "OFF: grasas, aceites, frutos secos o semillas")
    red = [t for t in tags if any(h in t for h in RED_MEAT_HINTS)]
    if red:
        return Classification(Category.RED_MEAT, False, f"OFF: posible carne roja ({red[0]})",
                              [Category.RED_MEAT, Category.GENERAL])
    if _has(tags, MEAT_HINTS):
        return Classification(Category.GENERAL, False, "OFF: producto cárnico sin especie clara",
                              [Category.GENERAL, Category.RED_MEAT])
    return Classification(Category.GENERAL, True, "OFF: no pertenece a ninguna categoría especial")


def classify_from_suggestion(suggested: str | None, confidence: str | None) -> Classification:
    cat = GEMINI_TO_CATEGORY.get(suggested or "")
    if cat is None:
        return Classification(Category.GENERAL, False, "sin categoría sugerida", list(Category))
    certain = confidence == "alta" and cat in (Category.GENERAL, Category.BEVERAGE, Category.WATER)
    # Queso, grasas y carne roja cambian mucho la puntuación: siempre se confirman.
    return Classification(cat, certain, f"sugerida por Gemini (confianza {confidence or '?'})",
                          [] if certain else [cat] + [c for c in Category if c != cat])
