"""Compara nuestro cálculo con los resultados esperados de Open Food Facts.

Los casos salen de los tests de la implementación de referencia de OFF
(openfoodfacts-server: tests/unit/nutriscore.t y
tests/unit/expected_test_results/nutriscore/*.json, rama main, 2026-10-23).
Se extrajeron con los valores que OFF usó realmente para puntuar (campo "value" de
cada componente). Cuando OFF no tenía un dato lo contó como 0, así que aquí también se
pone 0 para reproducir su resultado. La herramienta real no hace esto: calcula un rango.
"""

import pytest

from nutriscore.algorithm.score import ScoreInputs, compute
from nutriscore.models import Category

from conftest import load_json

CASES = load_json("off_nutriscore_2023_cases.json")

OFF_TO_OURS = {
    "energy": "energia_kj",
    "energy_from_saturated_fat": "energia_de_saturadas_kj",
    "sugars": "azucares_g",
    "saturated_fat": "grasas_saturadas_g",
    "saturated_fat_ratio": "proporcion_saturadas_pct",
    "salt": "sal_g",
    "non_nutritive_sweeteners": "edulcorantes",
    "proteins": "proteinas_g",
    "fiber": "fibra_g",
    "fruits_vegetables_legumes": "frutas_verduras_legumbres_pct",
}


def category_from_flags(f: dict) -> Category:
    if f["is_water"]:
        return Category.WATER
    if f["is_beverage"]:
        return Category.BEVERAGE
    if f["is_fat_oil_nuts_seeds"]:
        return Category.FATS
    if f["is_cheese"]:
        return Category.CHEESE
    if f["is_red_meat_product"]:
        return Category.RED_MEAT
    return Category.GENERAL


def inputs_from_case(c: dict) -> ScoreInputs:
    raw, used = c["raw"], c["expected"]["values"]

    def pick(off_id: str, raw_key: str) -> float:
        v = used.get(off_id, raw.get(raw_key))
        return 0.0 if v is None else float(v)  # convención de OFF: dato ausente = 0

    return ScoreInputs(
        energy_kj=pick("energy", "energy_kj"),
        sugars_g=pick("sugars", "sugars_g"),
        saturated_fat_g=pick("saturated_fat", "saturated_fat_g"),
        salt_g=pick("salt", "salt_g"),
        fiber_g=pick("fiber", "fiber_g"),
        proteins_g=pick("proteins", "proteins_g"),
        fvl_percent=0.0 if c["fvl_percent"] is None else float(c["fvl_percent"]),
        fat_g=raw["fat_g"],
        non_nutritive_sweeteners=(c["non_nutritive_sweeteners"] or 0) > 0,
    )


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_matches_open_food_facts(case):
    result = compute(inputs_from_case(case), category_from_flags(case["flags"]))
    exp = case["expected"]

    ours = {c.id: c.points for c in result.negative + result.positive}
    for off_id, points in exp["points"].items():
        assert ours[OFF_TO_OURS[off_id]] == points, off_id
    assert result.proteins_counted == exp["count_proteins"]
    assert result.score == exp["score"]
    assert result.grade == exp["grade"].upper()


def test_there_are_cases_for_every_category():
    cats = {category_from_flags(c["flags"]) for c in CASES}
    assert {Category.GENERAL, Category.BEVERAGE, Category.FATS, Category.RED_MEAT} <= cats
