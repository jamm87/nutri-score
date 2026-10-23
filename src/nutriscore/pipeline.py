"""Orquestación: código de barras → caché → Open Food Facts → Gemini."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import gemini_extractor, imaging, off_client
from .cache import Cache
from .config import Config
from .models import ProductData

FREE_TIER_NOTICE = (
    "Aviso de privacidad: estás usando la capa gratuita de Gemini. En el EEE, Suiza y Reino "
    "Unido Google aplica también a la capa gratuita los términos de pago (no usa tus datos para "
    "mejorar sus productos). Fuera de esas regiones sí puede usarlos y revisores humanos pueden "
    "leerlos (https://ai.google.dev/gemini-api/terms)."
)


@dataclass
class Obtained:
    product: ProductData
    notices: list[str] = field(default_factory=list)
    usage: gemini_extractor.GeminiUsage | None = None


class PipelineError(RuntimeError):
    pass


def obtain(images: list[Path], cfg: Config, cache: Cache | None, barcode: str | None = None) -> Obtained:
    notices: list[str] = []
    loaded = [imaging.load(p) for p in images]

    # 0. Código de barras: lectura local y gratuita.
    if barcode is None:
        for img in loaded:
            barcode = imaging.read_barcode(img)
            if barcode:
                notices.append(f"Código de barras leído en la foto: {barcode}")
                break
    elif not imaging.valid_gtin(barcode):
        raise PipelineError(f"El código {barcode} no es un EAN/UPC válido (dígito de control)")

    off_partial: ProductData | None = None
    if barcode:
        if cache and (hit := cache.get(f"barcode:{barcode}")):
            return Obtained(hit, notices + ["Resultado tomado de la caché local (sin coste)"])
        try:
            off = off_client.fetch(barcode, cfg.off)
        except off_client.OffError as e:
            off = None
            notices.append(str(e))
        if off is not None:
            missing = off_client.missing_required(off.nutrition)
            if not missing:
                if cache:
                    cache.put(f"barcode:{barcode}", off)
                return Obtained(off, notices)
            off_partial = off
            notices.append("Open Food Facts tiene el producto pero le faltan: " + ", ".join(missing))
        else:
            notices.append("El producto no está en Open Food Facts")

    if not images:
        if off_partial is not None:
            notices.append("Sin fotos: se calcula con los datos incompletos de Open Food Facts")
            return Obtained(off_partial, notices)
        raise PipelineError("No hay datos: el producto no está en Open Food Facts y no se dieron fotos")

    # Caché por huella de las fotos: no pagar dos veces por las mismas imágenes.
    img_key = f"image:{imaging.images_hash(images)}"
    if cache and (hit := cache.get(img_key)):
        return Obtained(hit, notices + ["Resultado tomado de la caché local (sin coste)"])

    # 1. Gemini: una sola llamada con todas las fotos reducidas.
    jpegs = [imaging.to_jpeg_for_llm(img, cfg.image["max_side_px"], cfg.image["jpeg_quality"])
             for img in loaded]
    if cfg.gemini.get("free_tier"):
        notices.append(FREE_TIER_NOTICE)
    try:
        product, usage = gemini_extractor.extract(jpegs, cfg.gemini)
    except gemini_extractor.GeminiError as e:
        if cache and e.usage:
            _log(cache, e.usage, img_key, len(jpegs))
        raise PipelineError(str(e)) from e
    if cache:
        _log(cache, usage, barcode and f"barcode:{barcode}" or img_key, len(jpegs))

    barcode = barcode or product.barcode
    product.barcode = barcode
    if cache:
        cache.put(img_key, product)
        if barcode:
            cache.put(f"barcode:{barcode}", product)
    return Obtained(product, notices, usage)


def _log(cache: Cache, u: gemini_extractor.GeminiUsage, key: str, n_images: int) -> None:
    cache.log_gemini_call(key=key, model=u.model, images=n_images, input_tokens=u.input_tokens,
                          output_tokens=u.output_tokens, thinking_tokens=u.thinking_tokens,
                          total_tokens=u.total_tokens, cost_paid_tier=u.cost_paid_tier_usd,
                          cost_billed=u.cost_billed_usd)
