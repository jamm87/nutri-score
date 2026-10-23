from nutriscore.gemini_extractor import RESPONSE_SCHEMA, estimate_cost, parse_response
from nutriscore.models import Source

BASE = {
    "unidad_base": "100g", "energia_kj": 1762, "energia_kcal": 420, "grasas_g": 12,
    "grasas_saturadas_g": 0, "azucares_g": 13.9, "sal_g": 6.81, "sodio_mg": None,
    "proteinas_g": 7.2, "fibra_g": None, "ingredientes": "Harina de trigo, sal, azúcar",
    "campos_no_legibles": [], "nombre_producto": "Snack", "codigo_barras": "8410000000009",
    "categoria_sugerida": "general", "categoria_confianza": "alta",
}


def test_parse_basic():
    p = parse_response(dict(BASE))
    n = p.nutrition
    assert p.source == Source.GEMINI
    assert (n.energy_kj, n.salt_g, n.fiber_g) == (1762, 6.81, None)
    assert p.barcode == "8410000000009"
    assert p.suggested_category == "general" and p.suggested_confidence == "alta"
    assert n.non_nutritive_sweeteners is False


def test_per_portion_only_values_are_discarded():
    p = parse_response({**BASE, "unidad_base": "otra"})
    n = p.nutrition
    assert n.energy_kj is None and n.sugars_g is None and n.salt_g is None
    assert any("porción" in f for f in n.unreadable_fields)


def test_sodium_converted_only_when_salt_missing():
    p = parse_response({**BASE, "sal_g": None, "sodio_mg": 400})
    assert p.nutrition.salt_g == 1.0


def test_invalid_barcode_digits_are_dropped():
    assert parse_response({**BASE, "codigo_barras": "8410000000008"}).barcode is None


def test_negative_values_rejected():
    p = parse_response({**BASE, "azucares_g": -3})
    assert p.nutrition.sugars_g is None and "azucares_g" in p.nutrition.unreadable_fields


def test_schema_requires_all_fields():
    assert set(RESPONSE_SCHEMA["required"]) == set(RESPONSE_SCHEMA["properties"])


def test_cost_estimate():
    cfg = {"price_input_per_mtok_usd": 0.10, "price_output_per_mtok_usd": 0.40}
    assert abs(estimate_cost(1_000_000, 0, 0, cfg) - 0.10) < 1e-12
    assert abs(estimate_cost(500, 200, 0, cfg) - (500 * 0.10 + 200 * 0.40) / 1e6) < 1e-15
