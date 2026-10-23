"""Flujo completo sin red: OFF y Gemini se sustituyen por dobles de prueba."""

from pathlib import Path

import pytest
from PIL import Image

from nutriscore import gemini_extractor, off_client, pipeline
from nutriscore.cache import Cache
from nutriscore.config import Config
from nutriscore.gemini_extractor import GeminiUsage, parse_response
from nutriscore.models import NutritionData, ProductData, Source

from test_gemini_parse import BASE
from test_imaging import _ean_image

CFG = Config({
    "gemini": {"model": "gemini-2.5-flash-lite", "price_input_per_mtok_usd": 0.1,
               "price_output_per_mtok_usd": 0.4, "free_tier": True},
    "image": {"max_side_px": 1024, "jpeg_quality": 85},
    "off": {"base_url": "http://off.invalid", "user_agent": "test"},
    "cache": {"db_path": ":memory:"},
}, Path("."))


@pytest.fixture
def photo(tmp_path):
    p = tmp_path / "tabla.jpg"
    Image.new("RGB", (2000, 1500), "white").save(p)
    return p


@pytest.fixture
def barcode_photo(tmp_path):
    p = tmp_path / "codigo.png"
    _ean_image("841000000000").save(p)
    return p


@pytest.fixture
def gemini_calls(monkeypatch):
    calls = []

    def fake_extract(jpegs, cfg):
        calls.append(jpegs)
        return parse_response(dict(BASE)), GeminiUsage(cfg["model"], 600, 150, 0, 750, 0.00012, 0.0)

    monkeypatch.setattr(gemini_extractor, "extract", fake_extract)
    return calls


def complete_off_product(code):
    return ProductData(Source.OFF, NutritionData(energy_kj=1000, sugars_g=5, saturated_fat_g=1,
                                                 salt_g=0.3, proteins_g=4), barcode=code)


def test_off_complete_avoids_gemini(monkeypatch, barcode_photo, gemini_calls):
    monkeypatch.setattr(off_client, "fetch", lambda code, cfg: complete_off_product(code))
    got = pipeline.obtain([barcode_photo], CFG, Cache(":memory:"))
    assert got.product.source == Source.OFF
    assert gemini_calls == []


def test_off_incomplete_falls_back_to_gemini_once(monkeypatch, barcode_photo, gemini_calls):
    def partial(code, cfg):
        p = complete_off_product(code)
        p.nutrition.salt_g = None
        return p

    monkeypatch.setattr(off_client, "fetch", partial)
    cache = Cache(":memory:")
    got = pipeline.obtain([barcode_photo], CFG, cache)
    assert got.product.source == Source.GEMINI and len(gemini_calls) == 1
    assert any("faltan" in n for n in got.notices)
    # Segunda vez: caché por código de barras, sin pagar de nuevo.
    again = pipeline.obtain([barcode_photo], CFG, cache)
    assert again.product.from_cache and len(gemini_calls) == 1
    summary = cache.cost_summary()
    assert summary["llamadas_gemini"] == 1 and summary["tokens_entrada"] == 600


def test_no_barcode_uses_gemini_with_downscaled_image_and_image_cache(monkeypatch, photo, gemini_calls):
    monkeypatch.setattr(off_client, "fetch", lambda *a: pytest.fail("no debe consultar OFF"))
    cache = Cache(":memory:")
    got = pipeline.obtain([photo], CFG, cache)
    assert got.usage.input_tokens == 600
    sent = Image.open(__import__("io").BytesIO(gemini_calls[0][0]))
    assert max(sent.size) <= 1024
    assert any("privacidad" in n for n in got.notices)
    pipeline.obtain([photo], CFG, cache)
    assert len(gemini_calls) == 1


def test_all_photos_go_in_a_single_call(monkeypatch, tmp_path, gemini_calls):
    monkeypatch.setattr(off_client, "fetch", lambda *a: None)
    paths = []
    for i, color in enumerate(("white", "gray")):
        p = tmp_path / f"f{i}.jpg"
        Image.new("RGB", (800, 600), color).save(p)
        paths.append(p)
    pipeline.obtain(paths, CFG, Cache(":memory:"))
    assert len(gemini_calls) == 1 and len(gemini_calls[0]) == 2
