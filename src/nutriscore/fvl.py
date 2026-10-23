"""ESTIMACIÓN del % de frutas, verduras y legumbres (FVL) a partir de los ingredientes.

La etiqueta casi nunca declara este porcentaje, así que el resultado es SIEMPRE una
estimación y se devuelve como intervalo [mínimo, máximo]:

- Solo cuenta el % que se declara de forma explícita junto a un ingrediente reconocido
  como fruta, verdura o legumbre (por ejemplo, "tomate 45 %").
- Si un ingrediente FVL no lleva %, se acota con la regla de orden del Reglamento (UE)
  1169/2011, art. 18: los ingredientes van en orden decreciente de peso. Su % es como
  mucho el del ingrediente con % declarado que le precede (o 100 si no hay ninguno), y
  como poco el del siguiente con % declarado (o 0). Además, el ingrediente en la
  posición k pesa como mucho 100/k %.
- Las patatas y otros tubérculos amiláceos no cuentan. Tampoco los aromas, extractos,
  harinas, almidones, fibras, proteínas aisladas ni aceites (salvo el de oliva, que OFF
  cuenta como fruta).

Es una heurística por palabras clave: puede fallar con nombres poco comunes. Por eso el
informe muestra siempre la etiqueta ESTIMACIÓN y, en la puntuación, el rango.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Raíces de palabras (sin tildes, minúsculas) en español, inglés y francés.
FVL_KEYWORDS = (
    # frutas
    "manzana", "apple", "pomme ", "pera", "pear", "poire", "naranja", "orange", "limon", "lemon",
    "lima", "mandarina", "pomelo", "grapefruit", "platano", "banana", "banane", "fresa", "strawberr",
    "fraise", "frambuesa", "raspberr", "framboise", "mora", "blackberr", "arandano", "blueberr",
    "cranberr", "myrtille", "cereza", "cherr", "cerise", "melocoton", "peach", "peche", "albaricoque",
    "apricot", "abricot", "ciruela", "plum", "prune", "uva", "grape", "raisin", "pina", "pineapple",
    "ananas", "mango", "mangue", "papaya", "kiwi", "higo", "fig", "datil", "date", "granada",
    "pomegranate", "grenade", "melon", "sandia", "watermelon", "pasteque", "coco", "aceituna", "olive",
    "aguacate", "avocado", "avocat", "fruta", "fruit",
    # verduras y hortalizas
    "tomate", "tomato", "pimiento", "pepper", "poivron", "cebolla", "onion", "oignon", "ajo", "garlic",
    "ail ", "zanahoria", "carrot", "carotte", "calabacin", "zucchini", "courgette", "calabaza",
    "pumpkin", "potiron", "berenjena", "eggplant", "aubergine", "pepino", "cucumber", "concombre",
    "espinaca", "spinach", "epinard", "lechuga", "lettuce", "laitue", "col ", "cabbage", "chou",
    "brocoli", "broccoli", "coliflor", "cauliflower", "puerro", "leek", "poireau", "apio", "celery",
    "celeri", "remolacha", "beetroot", "betterave", "alcachofa", "artichoke", "artichaut",
    "esparrago", "asparagus", "asperge", "champinon", "seta", "mushroom", "champignon", "verdura",
    "hortaliza", "vegetable", "legume ", "maiz dulce", "sweet corn", "gazpacho",
    # legumbres
    "garbanzo", "chickpea", "pois chiche", "lenteja", "lentil", "lentille", "alubia", "judia", "bean",
    "haricot", "guisante", "pea ", "petit pois", "soja", "soy", "haba", "broad bean", "feve",
    "legumbre", "pulse",
)

# Si el ingrediente contiene alguna de estas, no cuenta como FVL.
EXCLUDE = (
    "patata", "potato", "pomme de terre", "boniato", "yuca", "mandioca", "cassava", "aroma",
    "flavour", "flavor", "arome", "sabor", "extracto", "extract", "harina", "flour", "farine",
    "almidon", "starch", "amidon", "fibra", "fibre", "fiber", "proteina", "protein", "lecitina",
    "lecithin", "aceite", "oil", "huile", "pectina", "pectin", "vinagre", "vinegar", "azucar",
    "sugar", "sucre", "jarabe", "syrup", "sirop", "salsa de soja", "soy sauce", "sauce soja",
    "pimienta", "black pepper", "poivre",
)
# Excepción a la exclusión de aceites: el aceite de oliva cuenta como fruta.
OLIVE_OIL = ("aceite de oliva", "olive oil", "huile d'olive", "huile d olive")

_PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


@dataclass
class FvlEstimate:
    low: float
    high: float
    note: str


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _split_top_level(text: str) -> list[str]:
    """Separa por comas o punto y coma que no estén entre paréntesis o corchetes."""
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]" and depth:
            depth -= 1
        if ch in ",;" and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return [p for p in parts if p]


def _pattern(words: tuple[str, ...]) -> re.Pattern:
    """Palabra que empieza por la raíz dada; un espacio final en la raíz exige palabra completa."""
    alts = [re.escape(w.strip()) + (r"\b" if w.endswith(" ") else "") for w in words]
    return re.compile(r"\b(?:" + "|".join(alts) + ")")


_FVL_RE = _pattern(FVL_KEYWORDS)
_EXCLUDE_RE = _pattern(EXCLUDE)
_OLIVE_RE = _pattern(OLIVE_OIL)


def _is_fvl(ingredient: str) -> bool:
    if _OLIVE_RE.search(ingredient):
        return True
    if _EXCLUDE_RE.search(ingredient):
        return False
    return bool(_FVL_RE.search(ingredient))


def _own_percent(ingredient: str) -> float | None:
    """% declarado del propio ingrediente (fuera de sus sub-ingredientes entre paréntesis)."""
    outside = re.sub(r"\([^)]*\)", " ", ingredient)
    m = _PERCENT.search(outside) or _PERCENT.search(ingredient)
    return float(m.group(1).replace(",", ".")) if m else None


def estimate_fvl(ingredients: str | None) -> FvlEstimate | None:
    if not ingredients or not ingredients.strip():
        return None
    text = _normalize(ingredients)
    text = re.sub(r"^\s*ingr[eé]?dientes?\s*:?", "", text)
    items = _split_top_level(text)
    pcts = [_own_percent(i) for i in items]
    fvl_flags = [_is_fvl(i) for i in items]

    if not any(fvl_flags):
        return FvlEstimate(0.0, 0.0, "ESTIMACIÓN: no se detectaron frutas, verduras ni legumbres")

    low = high = 0.0
    names = []
    for idx, (item, pct, is_fvl) in enumerate(zip(items, pcts, fvl_flags)):
        if not is_fvl:
            continue
        names.append(item[:40])
        if pct is not None:
            low += pct
            high += pct
            continue
        before = [p for p in pcts[:idx] if p is not None]
        after = [p for p in pcts[idx + 1 :] if p is not None]
        # En la posición k (desde 1) un ingrediente pesa como mucho 100/k %, porque los
        # anteriores pesan al menos lo mismo que él.
        high += min([*before, 100.0 / (idx + 1)])
        low += max(after) if after else 0.0

    low, high = min(low, 100.0), min(high, 100.0)
    return FvlEstimate(
        round(low, 1), round(high, 1),
        "ESTIMACIÓN desde ingredientes (" + "; ".join(names) + ")",
    )
