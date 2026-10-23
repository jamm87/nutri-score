from nutriscore import off_client
from nutriscore.models import Source

from conftest import load_json


def test_parse_off_product():
    raw = load_json("off_product_sample.json")["product"]
    p = off_client.parse_product(raw, "8410000000009")
    n = p.nutrition
    assert p.source == Source.OFF
    assert (n.energy_kj, n.sugars_g, n.saturated_fat_g, n.salt_g, n.proteins_g, n.fiber_g) == (
        1980, 28, 2.1, 0.6, 6.5, 3.2)
    assert p.off_grade_2023 == "D"
    assert n.fvl_percent_range == (0, 0)  # ESTIMACIÓN propia: no hay FVL en la lista
    assert off_client.missing_required(n) == []


def test_salt_from_sodium_and_kj_from_kcal_when_missing():
    raw = load_json("off_product_sample.json")["product"]
    nm = raw["nutriments"]
    del nm["salt_100g"], nm["energy-kj_100g"]
    p = off_client.parse_product(raw, "x")
    assert p.nutrition.salt_g == 0.6  # 240 mg × 2,5
    assert p.nutrition.energy_kj == round(473 * 4.184, 1)
    assert len(p.nutrition.conversions) == 2


def test_missing_values_stay_none():
    raw = load_json("off_product_sample.json")["product"]
    del raw["nutriments"]["fiber_100g"], raw["nutriments"]["sugars_100g"]
    p = off_client.parse_product(raw, "x")
    assert p.nutrition.fiber_g is None
    assert off_client.missing_required(p.nutrition) == ["sugars_g"]


def test_off_fvl_estimate_is_used_when_available():
    raw = load_json("off_product_sample.json")["product"]
    raw["nutriments"]["fruits-vegetables-legumes-estimate-from-ingredients_100g"] = 42.5
    p = off_client.parse_product(raw, "x")
    assert p.nutrition.fvl_percent_range == (42.5, 42.5)
    assert "ESTIMACIÓN" in p.nutrition.fvl_note
