import zxingcpp
from PIL import Image, ImageOps

from nutriscore.imaging import read_barcode, to_jpeg_for_llm, valid_gtin


def _ean_image(digits12: str) -> Image.Image:
    b = zxingcpp.create_barcode(digits12, zxingcpp.BarcodeFormat.EAN13)
    mv = memoryview(b.to_image(scale=4))
    img = Image.frombytes("L", (mv.shape[1], mv.shape[0]), mv.tobytes())
    return ImageOps.expand(img, border=60, fill=255).convert("RGB")


def test_reads_ean13_locally():
    assert read_barcode(_ean_image("841000000000")) == "8410000000009"


def test_no_barcode_returns_none():
    assert read_barcode(Image.new("RGB", (300, 200), "white")) is None


def test_gtin_check_digit():
    assert valid_gtin("8410000000009")
    assert not valid_gtin("8410000000008")
    assert not valid_gtin("12345")
    assert not valid_gtin(None)


def test_image_is_downscaled_before_sending():
    big = Image.new("RGB", (4000, 3000), "white")
    data = to_jpeg_for_llm(big, max_side=1024, quality=85)
    import io
    small = Image.open(io.BytesIO(data))
    assert max(small.size) == 1024
    assert small.size == (1024, 768)
