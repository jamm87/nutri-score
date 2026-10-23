"""Caso real del usuario y reglas específicas sin caso en los fixtures de OFF."""

from nutriscore.algorithm.ranges import evaluate
from nutriscore.algorithm.score import ScoreInputs, compute, grade_for, points_for
from nutriscore.models import Category, NutritionData


def test_user_real_case_is_E_even_without_fiber():
    # energía 1762 kJ, azúcares 13,9 g, saturadas 0 g, sal 6,81 g, proteínas 7,2 g,
    # fibra no declarada, FVL 0 % → esperado E
    n = NutritionData(energy_kj=1762, sugars_g=13.9, saturated_fat_g=0, salt_g=6.81,
                      proteins_g=7.2, fiber_g=None, fvl_percent_range=(0, 0))
    r = evaluate(n, Category.GENERAL)
    assert r.best.grade == r.worst.grade == "E"
    assert r.grade_is_certain
    # energía 5 + azúcares 3 + saturadas 0 + sal 20 = 28 → proteínas no cuentan (>= 11)
    assert r.worst.negative_points == 28
    assert not r.worst.proteins_counted
    # la fibra puede aportar 0..5 puntos: puntuación entre 23 y 28
    assert (r.best.score, r.worst.score) == (23, 28)
    assert [m.field for m in r.missing] == ["fiber_g"]


def test_thresholds_are_strictly_greater():
    assert points_for(3.4, (3.4, 6.8)) == 0
    assert points_for(3.41, (3.4, 6.8)) == 1


def test_saturated_fat_ratio_uses_greater_or_equal():
    # 10 % exacto ya da 1 punto en la proporción saturadas/grasa
    i = ScoreInputs(energy_kj=3700, sugars_g=0, saturated_fat_g=10, salt_g=0, fiber_g=0,
                    proteins_g=0, fvl_percent=0, fat_g=100)
    r = compute(i, Category.FATS)
    ratio = next(c for c in r.negative if c.id == "proporcion_saturadas_pct")
    assert ratio.points == 1


def test_cheese_counts_proteins_even_with_many_negative_points():
    # Valores ilustrativos (no de un producto concreto) para comprobar la regla.
    i = ScoreInputs(energy_kj=1600, sugars_g=0.5, saturated_fat_g=18, salt_g=1.6,
                    fiber_g=0, proteins_g=25, fvl_percent=0)
    general = compute(i, Category.GENERAL)
    cheese = compute(i, Category.CHEESE)
    assert general.negative_points >= 11
    assert not general.proteins_counted
    assert cheese.proteins_counted
    assert cheese.score == general.score - 7


def test_red_meat_protein_capped_at_2():
    i = ScoreInputs(energy_kj=800, sugars_g=0, saturated_fat_g=3, salt_g=0.2,
                    fiber_g=0, proteins_g=20, fvl_percent=0)
    r = compute(i, Category.RED_MEAT)
    prot = next(c for c in r.positive if c.id == "proteinas_g")
    assert prot.points == 2


def test_water_is_always_A_and_other_beverages_never_A():
    assert grade_for(-10, Category.WATER) == "A"
    assert grade_for(-10, Category.BEVERAGE) == "B"


def test_beverage_sweeteners_add_4_points():
    base = dict(energy_kj=5, sugars_g=0, saturated_fat_g=0, salt_g=0, fiber_g=0,
                proteins_g=0, fvl_percent=0)
    without = compute(ScoreInputs(**base), Category.BEVERAGE)
    with_nns = compute(ScoreInputs(**base, non_nutritive_sweeteners=True), Category.BEVERAGE)
    assert with_nns.score - without.score == 4
    assert (without.grade, with_nns.grade) == ("B", "C")


def test_grade_boundaries_general_and_fats():
    assert [grade_for(s, Category.GENERAL) for s in (0, 1, 2, 3, 10, 11, 18, 19)] == list("ABBCCDDE")
    assert [grade_for(s, Category.FATS) for s in (-6, -5, 2, 3, 10, 11, 18, 19)] == list("ABBCCDDE")
    assert [grade_for(s, Category.BEVERAGE) for s in (2, 3, 6, 7, 9, 10)] == list("BCCDDE")
