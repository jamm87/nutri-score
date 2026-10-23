from nutriscore.algorithm.ranges import evaluate
from nutriscore.models import Category, NutritionData

COMPLETE = dict(energy_kj=1200, sugars_g=12, saturated_fat_g=2, fat_g=8, salt_g=0.5,
                proteins_g=6, fiber_g=3.5, fvl_percent_range=(0, 0))


def test_complete_data_gives_exact_score():
    r = evaluate(NutritionData(**COMPLETE), Category.GENERAL)
    assert r.is_exact and r.grade_is_certain and r.missing == []


def test_missing_value_never_filled_with_typical_value():
    n = NutritionData(**{**COMPLETE, "salt_g": None})
    r = evaluate(n, Category.GENERAL)
    # Peor caso: sal al máximo físico (20 puntos). Mejor caso: 0 g.
    salt_best = next(c for c in r.best.negative if c.id == "sal_g")
    salt_worst = next(c for c in r.worst.negative if c.id == "sal_g")
    assert (salt_best.value, salt_worst.value) == (0, 100)
    assert not r.grade_is_certain
    assert r.grades[0] == r.best.grade and r.grades[-1] == r.worst.grade


def test_unknown_fvl_is_range_0_100():
    n = NutritionData(**{**COMPLETE, "fvl_percent_range": None})
    r = evaluate(n, Category.GENERAL)
    fvl_best = next(c for c in r.best.positive if c.id == "frutas_verduras_legumbres_pct")
    assert fvl_best.points == 5
    assert [m.field for m in r.missing] == ["fvl_percent"]


def test_fat_missing_in_fats_category_worst_case_ratio_100():
    n = NutritionData(energy_kj=3400, sugars_g=0, saturated_fat_g=7, fat_g=None, salt_g=0,
                      proteins_g=0, fiber_g=0, fvl_percent_range=(0, 0))
    r = evaluate(n, Category.FATS)
    worst_ratio = next(c for c in r.worst.negative if c.id == "proporcion_saturadas_pct")
    best_ratio = next(c for c in r.best.negative if c.id == "proporcion_saturadas_pct")
    assert worst_ratio.value == 100 and best_ratio.value == 7


def test_saturated_cannot_exceed_known_fat():
    n = NutritionData(**{**COMPLETE, "saturated_fat_g": None, "fat_g": 3})
    r = evaluate(n, Category.GENERAL)
    sat_worst = next(c for c in r.worst.negative if c.id == "grasas_saturadas_g")
    assert sat_worst.value == 3


def test_beverage_unknown_sweeteners_is_a_range():
    n = NutritionData(energy_kj=10, sugars_g=0, saturated_fat_g=0, salt_g=0, proteins_g=0,
                      fiber_g=0, fvl_percent_range=(0, 0), non_nutritive_sweeteners=None)
    r = evaluate(n, Category.BEVERAGE)
    assert r.worst.score - r.best.score == 4
    assert [m.field for m in r.missing] == ["non_nutritive_sweeteners"]


def test_fields_not_used_by_category_are_not_reported_missing():
    # La grasa total solo importa en la categoría grasas.
    n = NutritionData(**{**COMPLETE, "fat_g": None})
    assert evaluate(n, Category.GENERAL).missing == []
