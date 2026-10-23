"""Lectura de imágenes: código de barras (local, gratis) y reducción antes de enviar a Gemini."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageOps

RETAIL_FORMATS = ("EAN13", "EAN8", "UPCA", "UPCE")


def load(path: Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)  # respeta la orientación de las fotos del móvil
    return img.convert("RGB")


def images_hash(paths: list[Path]) -> str:
    """Huella de un conjunto de fotos (independiente del orden) para la caché."""
    digests = sorted(hashlib.sha256(p.read_bytes()).hexdigest() for p in paths)
    return hashlib.sha256("".join(digests).encode()).hexdigest()


def read_barcode(img: Image.Image) -> str | None:
    """Lee un EAN/UPC con zxing-cpp sobre la imagen a resolución completa."""
    import zxingcpp

    for result in zxingcpp.read_barcodes(img):
        fmt = str(result.format).split(".")[-1].upper().replace("-", "").replace("_", "")
        if any(f in fmt for f in RETAIL_FORMATS) and valid_gtin(result.text):
            return result.text
    return None


def valid_gtin(code: str | None) -> bool:
    """Comprueba el dígito de control de un EAN-8/UPC-A/EAN-13/GTIN-14."""
    if not code or not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in code]
    check = digits.pop()
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return (10 - total % 10) % 10 == check


def to_jpeg_for_llm(img: Image.Image, max_side: int, quality: int) -> bytes:
    """Reduce la imagen para que el lado mayor no pase de max_side y la comprime en JPEG."""
    img = img.copy()
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()
