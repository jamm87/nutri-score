"""Cálculo determinista del Nutri-Score 2023 (ver fuentes en tables_2023.py).

Este módulo exige valores completos. El tratamiento de datos que faltan (rangos) está
en ranges.py: aquí nunca se rellena nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Category
from . import tables_2023 as T


@dataclass(frozen=True)
class ScoreInputs:
    """Valores por 100 g/100 ml, todos conocidos."""

    energy_kj: float
    sugars_g: float
    saturated_fat_g: float
    salt_g: float
    fiber_g: float
    proteins_g: float
    fvl_percent: float
    # Solo se usa en la categoría grasas (proporción saturadas/grasa total).
    fat_g: float | None = None
    # Solo se usa en bebidas.
    non_nutritive_sweeteners: bool = False


@dataclass
class Component:
    id: str
    value: float
    points: int
    points_max: int
    note: str = ""


@dataclass
class ScoreResult:
    score: int
    grade: str
    negative: list[Component] = field(default_factory=list)
    positive: list[Component] = field(default_factory=list)
    negative_points: int = 0
    positive_points: int = 0
    proteins_counted: bool = False
    proteins_reason: str = ""


def points_for(value: float, thresholds: tuple[float, ...], inclusive: bool = False) -> int:
    """Número de umbrales superados (> o, si inclusive, >=)."""
    if inclusive:
        return sum(1 for t in thresholds if value >= t)
    return sum(1 for t in thresholds if value > t)


def saturated_fat_ratio(saturated_fat_g: float, fat_g: float | None) -> float:
    """% saturadas / grasa total. Si la grasa total es 0 o falta pero hay saturadas, se
    toma grasa = saturadas (100 %), como en la implementación de referencia de OFF."""
    if saturated_fat_g <= 0:
        return 0.0
    if fat_g is None or fat_g <= 0 or fat_g < saturated_fat_g:
        fat_g = saturated_fat_g
    # Redondeo a 9 decimales solo para eliminar errores de coma flotante
    # (p. ej. 1.6 / 10 * 100 = 16.000000000000004), no es un redondeo del algoritmo.
    return round(saturated_fat_g / fat_g * 100, 9)


def grade_for(score: int, category: Category) -> str:
    if category == Category.WATER:
        return "A"
    if category.is_beverage:
        table = T.GRADES_BEVERAGES
    elif category == Category.FATS:
        table = T.GRADES_FATS
    else:
        table = T.GRADES_GENERAL
    for letter, max_score in table:
        if score <= max_score:
            return letter
    return "E"


def compute(inputs: ScoreInputs, category: Category) -> ScoreResult:
    bev = category.is_beverage
    fats = category == Category.FATS

    # --- Negativos ---
    negative: list[Component] = []
    if fats:
        efs = inputs.saturated_fat_g * T.KJ_PER_G_SATURATED_FAT
        negative.append(
            Component("energia_de_saturadas_kj", efs,
                      points_for(efs, T.ENERGY_FROM_SATURATED_FAT), len(T.ENERGY_FROM_SATURATED_FAT))
        )
    else:
        table = T.ENERGY_BEVERAGES if bev else T.ENERGY
        negative.append(Component("energia_kj", inputs.energy_kj,
                                  points_for(inputs.energy_kj, table), len(table)))

    table = T.SUGARS_BEVERAGES if bev else T.SUGARS
    negative.append(Component("azucares_g", inputs.sugars_g, points_for(inputs.sugars_g, table), len(table)))

    if fats:
        ratio = saturated_fat_ratio(inputs.saturated_fat_g, inputs.fat_g)
        negative.append(
            Component("proporcion_saturadas_pct", ratio,
                      points_for(ratio, T.SATURATED_FAT_RATIO, inclusive=True), len(T.SATURATED_FAT_RATIO))
        )
    else:
        negative.append(Component("grasas_saturadas_g", inputs.saturated_fat_g,
                                  points_for(inputs.saturated_fat_g, T.SATURATED_FAT), len(T.SATURATED_FAT)))

    negative.append(Component("sal_g", inputs.salt_g, points_for(inputs.salt_g, T.SALT), len(T.SALT)))

    if bev:
        nns = T.NON_NUTRITIVE_SWEETENERS_POINTS if inputs.non_nutritive_sweeteners else 0
        negative.append(Component("edulcorantes", 1.0 if inputs.non_nutritive_sweeteners else 0.0,
                                  nns, T.NON_NUTRITIVE_SWEETENERS_POINTS))

    negative_points = sum(c.points for c in negative)

    # --- ¿Cuentan las proteínas? ---
    if bev:
        proteins_counted, reason = True, "bebida: las proteínas cuentan siempre"
    elif category == Category.CHEESE:
        proteins_counted, reason = True, "queso: las proteínas cuentan siempre"
    elif fats:
        proteins_counted = negative_points < T.PROTEIN_NEGATIVE_LIMIT_FATS
        reason = (f"puntos negativos {'<' if proteins_counted else '>='} "
                  f"{T.PROTEIN_NEGATIVE_LIMIT_FATS} (categoría grasas)")
    else:
        proteins_counted = negative_points < T.PROTEIN_NEGATIVE_LIMIT_GENERAL
        reason = f"puntos negativos {'<' if proteins_counted else '>='} {T.PROTEIN_NEGATIVE_LIMIT_GENERAL}"

    # --- Positivos ---
    positive: list[Component] = []
    table = T.PROTEINS_BEVERAGES if bev else T.PROTEINS
    p_points = points_for(inputs.proteins_g, table)
    p_note = ""
    if category == Category.RED_MEAT and p_points > T.RED_MEAT_MAX_PROTEIN_POINTS:
        p_points = T.RED_MEAT_MAX_PROTEIN_POINTS
        p_note = f"limitado a {T.RED_MEAT_MAX_PROTEIN_POINTS} puntos (carne roja)"
    if not proteins_counted:
        p_points = 0
        p_note = "no cuenta: " + reason
    positive.append(Component("proteinas_g", inputs.proteins_g, p_points, len(table), p_note))

    positive.append(Component("fibra_g", inputs.fiber_g, points_for(inputs.fiber_g, T.FIBER), len(T.FIBER)))

    table = T.FRUITS_VEGETABLES_LEGUMES_BEVERAGES if bev else T.FRUITS_VEGETABLES_LEGUMES
    positive.append(Component("frutas_verduras_legumbres_pct", inputs.fvl_percent,
                              points_for(inputs.fvl_percent, table), len(table)))

    positive_points = sum(c.points for c in positive)
    score = negative_points - positive_points
    return ScoreResult(
        score=score,
        grade=grade_for(score, category),
        negative=negative,
        positive=positive,
        negative_points=negative_points,
        positive_points=positive_points,
        proteins_counted=proteins_counted,
        proteins_reason=reason,
    )
