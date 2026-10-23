"""Extracción de la tabla nutricional con Gemini: UNA sola llamada por producto.

El LLM solo transcribe valores. Nunca calcula puntos ni rellena datos que no ve.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .imaging import valid_gtin
from .models import Category, NutritionData, ProductData, Source
from .normalize import derive_from_ingredients, fill_conversions

NUMBER_OR_NULL = {"type": ["number", "null"], "minimum": 0}

# Salida estructurada: Gemini devuelve directamente JSON que cumple este esquema, así no
# hay que reintentar por errores de formato.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "unidad_base": {"type": "string", "enum": ["100g", "100ml", "otra"],
                        "description": "Base de los valores de la tabla. 'otra' si solo hay valores por porción."},
        "energia_kj": NUMBER_OR_NULL,
        "energia_kcal": NUMBER_OR_NULL,
        "grasas_g": NUMBER_OR_NULL,
        "grasas_saturadas_g": NUMBER_OR_NULL,
        "azucares_g": NUMBER_OR_NULL,
        "sal_g": NUMBER_OR_NULL,
        "sodio_mg": NUMBER_OR_NULL,
        "proteinas_g": NUMBER_OR_NULL,
        "fibra_g": NUMBER_OR_NULL,
        "ingredientes": {"type": ["string", "null"]},
        "campos_no_legibles": {"type": "array", "items": {"type": "string"}},
        "nombre_producto": {"type": ["string", "null"]},
        "codigo_barras": {"type": ["string", "null"],
                          "description": "Dígitos impresos bajo el código de barras, si se leen."},
        "categoria_sugerida": {"type": "string", "enum": [c.value for c in Category]},
        "categoria_confianza": {"type": "string", "enum": ["alta", "baja"]},
    },
    "required": [
        "unidad_base", "energia_kj", "energia_kcal", "grasas_g", "grasas_saturadas_g", "azucares_g",
        "sal_g", "sodio_mg", "proteinas_g", "fibra_g", "ingredientes", "campos_no_legibles",
        "nombre_producto", "codigo_barras", "categoria_sugerida", "categoria_confianza",
    ],
}

PROMPT = """Eres un transcriptor de etiquetas alimentarias. Lee la(s) foto(s) del MISMO producto.

Reglas estrictas:
- Copia los valores de la columna "por 100 g" o "por 100 ml" tal como aparecen impresos.
  NO uses la columna por porción. Si solo hay valores por porción, pon unidad_base "otra"
  y deja los valores nutricionales en null.
- Si un valor no aparece o no se lee con seguridad, pon null y añade el nombre del campo a
  campos_no_legibles. NUNCA estimes, deduzcas ni pongas valores típicos.
- Un "0" o "<0,1" impreso se transcribe como el número (0 o 0.1); no lo conviertas en null.
- Usa punto decimal. Sal en gramos; sodio en miligramos (convierte g→mg solo si el sodio está
  impreso en gramos).
- ingredientes: el texto completo de la lista de ingredientes, literal, incluidos los
  porcentajes. null si no se ve.
- categoria_sugerida: general, bebida, agua (solo agua sin aromatizar), grasas (grasas,
  aceites, mantequilla, nata, frutos secos, semillas), queso, carne_roja (vacuno, cerdo,
  cordero, caballo, caza y sus derivados). La leche y las bebidas vegetales son "bebida".
  categoria_confianza "baja" si dudas.
"""


@dataclass
class GeminiUsage:
    model: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    total_tokens: int
    cost_paid_tier_usd: float
    cost_billed_usd: float


class GeminiError(RuntimeError):
    def __init__(self, msg: str, usage: GeminiUsage | None = None):
        super().__init__(msg)
        self.usage = usage  # si la llamada llegó a consumir tokens, para registrar el coste


def estimate_cost(input_tokens: int, output_tokens: int, thinking_tokens: int, cfg: dict) -> float:
    # Los tokens de razonamiento se facturan como salida.
    return (input_tokens * cfg["price_input_per_mtok_usd"]
            + (output_tokens + thinking_tokens) * cfg["price_output_per_mtok_usd"]) / 1_000_000


def parse_response(data: dict) -> ProductData:
    """Convierte el JSON de Gemini en ProductData."""
    unit = data.get("unidad_base")
    unreadable = list(data.get("campos_no_legibles") or [])
    values = {k: data.get(k) for k in ("energia_kj", "energia_kcal", "grasas_g", "grasas_saturadas_g",
                                        "azucares_g", "sal_g", "sodio_mg", "proteinas_g", "fibra_g")}
    if unit not in ("100g", "100ml"):
        # No convertimos porciones a 100 g: el tamaño de porción podría estar mal leído.
        values = dict.fromkeys(values)
        unreadable.append("tabla por 100 g/100 ml (solo hay valores por porción)")
    for k, v in values.items():
        if v is not None and (not isinstance(v, (int, float)) or v < 0):
            values[k] = None
            unreadable.append(k)

    n = NutritionData(
        energy_kj=values["energia_kj"],
        sugars_g=values["azucares_g"],
        fat_g=values["grasas_g"],
        saturated_fat_g=values["grasas_saturadas_g"],
        salt_g=values["sal_g"],
        proteins_g=values["proteinas_g"],
        fiber_g=values["fibra_g"],
        ingredients=data.get("ingredientes") or None,
        base_unit=unit if unit in ("100g", "100ml") else "100g",
        unreadable_fields=unreadable,
    )
    fill_conversions(n, sodium_mg=values["sodio_mg"], energy_kcal=values["energia_kcal"])
    derive_from_ingredients(n)

    code = data.get("codigo_barras")
    code = "".join(ch for ch in code if ch.isdigit()) if code else None
    product = ProductData(
        source=Source.GEMINI,
        nutrition=n,
        barcode=code if valid_gtin(code) else None,
        name=data.get("nombre_producto"),
        suggested_category=data.get("categoria_sugerida"),
        suggested_confidence=data.get("categoria_confianza"),
    )
    return product


def extract(jpeg_images: list[bytes], cfg: dict) -> tuple[ProductData, GeminiUsage]:
    from google import genai
    from google.genai import types

    api_key = os.environ.get(cfg.get("api_key_env", "GEMINI_API_KEY"))
    if not api_key:
        raise GeminiError(f"Falta la clave de API en la variable de entorno {cfg.get('api_key_env')}")
    client = genai.Client(api_key=api_key)

    parts = [types.Part.from_bytes(data=img, mime_type="image/jpeg") for img in jpeg_images]
    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
        response_json_schema=RESPONSE_SCHEMA,
        # Sin razonamiento: es transcripción y así no se pagan tokens de "thinking".
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    try:
        resp = client.models.generate_content(model=cfg["model"], contents=[*parts, PROMPT], config=config)
    except Exception as e:  # el SDK lanza varios tipos de error
        raise GeminiError(f"Error llamando a Gemini ({cfg['model']}): {e}") from e

    um = resp.usage_metadata
    inp = (um.prompt_token_count or 0) if um else 0
    out = (um.candidates_token_count or 0) if um else 0
    think = (um.thoughts_token_count or 0) if um else 0
    total = (um.total_token_count or inp + out + think) if um else 0
    cost = estimate_cost(inp, out, think, cfg)
    usage = GeminiUsage(cfg["model"], inp, out, think, total, cost, 0.0 if cfg.get("free_tier") else cost)

    try:
        data = json.loads(resp.text)
    except (TypeError, json.JSONDecodeError) as e:
        raise GeminiError(f"Gemini no devolvió JSON válido: {resp.text!r:.200}", usage) from e
    return parse_response(data), usage
