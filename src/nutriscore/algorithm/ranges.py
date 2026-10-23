"""Nutri-Score con datos incompletos: rango de puntuaciones posibles, sin inventar valores.

La puntuación es monótona en cada componente: sube (o se queda igual) al subir un
componente negativo y baja al subir uno positivo. Si un componente negativo sube, las
proteínas pueden dejar de contar, y eso también sube la puntuación. En la categoría
grasas, subir la grasa total baja la proporción de saturadas. Por eso basta con evaluar
dos escenarios extremos:
  - mejor caso: negativos desconocidos al mínimo y positivos al máximo físico;
  - peor caso: al revés.
La letra también es monótona en la puntuación, así que el rango de letras sale de esos
dos extremos.

Los límites son físicos (0–100 g por 100 g, 3700 kJ = 100 g de grasa), no valores
"típicos". El rango resultante es conservador.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Category, NutritionData
from .score import ScoreInputs, ScoreResult, compute

MAX_ENERGY_KJ = 3700.0  # 100 g de grasa × 37 kJ/g: máximo físico por 100 g
MAX_G = 100.0

FIELD_LABELS = {
    "energy_kj": "energía (kJ)",
    "sugars_g": "azúcares",
    "saturated_fat_g": "grasas saturadas",
    "fat_g": "grasas totales",
    "salt_g": "sal",
    "proteins_g": "proteínas",
    "fiber_g": "fibra",
    "fvl_percent": "% frutas/verduras/legumbres",
    "non_nutritive_sweeteners": "edulcorantes",
}


@dataclass
class MissingImpact:
    field: str
    label: str
    best_value: float
    worst_value: float
    # Rango de puntuación si SOLO este dato fuera desconocido (los demás desconocidos en
    # su caso más favorable). Indica cuánto pesa este dato por sí solo.
    score_range_alone: tuple[int, int]


@dataclass
class RangeResult:
    category: Category
    best: ScoreResult
    worst: ScoreResult
    missing: list[MissingImpact] = field(default_factory=list)
    fvl_is_estimate: bool = False

    @property
    def is_exact(self) -> bool:
        return self.best.score == self.worst.score

    @property
    def grade_is_certain(self) -> bool:
        return self.best.grade == self.worst.grade

    @property
    def grades(self) -> list[str]:
        letters = "ABCDE"
        lo, hi = letters.index(self.best.grade), letters.index(self.worst.grade)
        return list(letters[lo : hi + 1])


def required_fields(category: Category) -> list[str]:
    fields = ["energy_kj", "sugars_g", "saturated_fat_g", "salt_g", "proteins_g", "fiber_g", "fvl_percent"]
    if category == Category.FATS:
        fields.remove("energy_kj")  # se sustituye por la energía de las saturadas
        fields.append("fat_g")
    if category.is_beverage:
        fields.append("non_nutritive_sweeteners")
    return fields


def _bounds(n: NutritionData, category: Category) -> dict[str, tuple[float, float, bool]]:
    """Para cada campo: (valor en el mejor caso, valor en el peor caso, ¿falta?)."""
    b: dict[str, tuple[float, float, bool]] = {}

    def neg(name: str, value: float | None, upper: float) -> None:
        b[name] = (value, value, False) if value is not None else (0.0, upper, True)

    def pos(name: str, value: float | None, upper: float) -> None:
        b[name] = (value, value, False) if value is not None else (upper, 0.0, True)

    neg("energy_kj", n.energy_kj, MAX_ENERGY_KJ)
    neg("sugars_g", n.sugars_g, MAX_G)
    neg("salt_g", n.salt_g, MAX_G)
    # Las saturadas no pueden superar la grasa total cuando esta se conoce.
    neg("saturated_fat_g", n.saturated_fat_g, n.fat_g if n.fat_g is not None else MAX_G)
    # Grasa total: más grasa = menor proporción de saturadas = mejor. Peor caso: grasa = saturadas.
    if n.fat_g is not None:
        b["fat_g"] = (n.fat_g, n.fat_g, False)
    else:
        b["fat_g"] = (MAX_G, b["saturated_fat_g"][1], True)
    pos("proteins_g", n.proteins_g, MAX_G)
    pos("fiber_g", n.fiber_g, MAX_G)
    if n.fvl_percent_range is not None:
        lo, hi = n.fvl_percent_range
        b["fvl_percent"] = (hi, lo, lo != hi)
    else:
        b["fvl_percent"] = (100.0, 0.0, True)
    if n.non_nutritive_sweeteners is not None:
        v = 1.0 if n.non_nutritive_sweeteners else 0.0
        b["non_nutritive_sweeteners"] = (v, v, False)
    else:
        b["non_nutritive_sweeteners"] = (0.0, 1.0, True)
    return b


def _inputs(values: dict[str, float]) -> ScoreInputs:
    return ScoreInputs(
        energy_kj=values["energy_kj"],
        sugars_g=values["sugars_g"],
        saturated_fat_g=values["saturated_fat_g"],
        salt_g=values["salt_g"],
        fiber_g=values["fiber_g"],
        proteins_g=values["proteins_g"],
        fvl_percent=values["fvl_percent"],
        fat_g=values["fat_g"],
        non_nutritive_sweeteners=values["non_nutritive_sweeteners"] >= 1,
    )


def evaluate(n: NutritionData, category: Category) -> RangeResult:
    b = _bounds(n, category)
    relevant = required_fields(category)
    best_vals = {k: v[0] for k, v in b.items()}
    worst_vals = {k: v[1] for k, v in b.items()}
    # Los campos que no usa esta categoría no deben variar entre escenarios.
    for k in b:
        if k not in relevant:
            worst_vals[k] = best_vals[k]

    best = compute(_inputs(best_vals), category)
    worst = compute(_inputs(worst_vals), category)

    missing: list[MissingImpact] = []
    for k in relevant:
        lo, hi, is_missing = b[k]
        if not is_missing:
            continue
        alone = dict(best_vals)
        alone[k] = hi
        s_alone = compute(_inputs(alone), category).score
        missing.append(MissingImpact(k, FIELD_LABELS[k], lo, hi, (best.score, s_alone)))

    return RangeResult(
        category=category,
        best=best,
        worst=worst,
        missing=missing,
        fvl_is_estimate=True,  # el % FVL nunca viene declarado en la etiqueta: siempre se estima
    )
