"""Estructuras de datos compartidas."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class Category(str, Enum):
    """Categorías del algoritmo Nutri-Score 2023."""

    GENERAL = "general"
    BEVERAGE = "bebida"
    WATER = "agua"  # bebida; el agua es siempre A
    FATS = "grasas"  # grasas, aceites, frutos secos y semillas
    CHEESE = "queso"
    RED_MEAT = "carne_roja"

    @property
    def is_beverage(self) -> bool:
        return self in (Category.BEVERAGE, Category.WATER)


class Source(str, Enum):
    OFF = "Open Food Facts"
    GEMINI = "Gemini"
    MANUAL = "manual"


@dataclass
class NutritionData:
    """Valores por 100 g / 100 ml tal como aparecen en la etiqueta. None = no disponible."""

    energy_kj: float | None = None
    sugars_g: float | None = None
    fat_g: float | None = None
    saturated_fat_g: float | None = None
    salt_g: float | None = None
    proteins_g: float | None = None
    fiber_g: float | None = None
    # % de frutas, verduras y legumbres. Siempre es una ESTIMACIÓN desde ingredientes,
    # expresada como intervalo [min, max]. None = no se pudo estimar.
    fvl_percent_range: tuple[float, float] | None = None
    fvl_note: str = ""
    # Solo relevante en bebidas: True/False si se pudo determinar, None si no hay ingredientes.
    non_nutritive_sweeteners: bool | None = None
    ingredients: str | None = None
    base_unit: str = "100g"  # "100g" | "100ml"
    # Notas sobre conversiones aplicadas (p. ej. sodio → sal, kcal → kJ).
    conversions: list[str] = field(default_factory=list)
    unreadable_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> NutritionData:
        d = dict(d)
        if d.get("fvl_percent_range") is not None:
            d["fvl_percent_range"] = tuple(d["fvl_percent_range"])
        return cls(**d)


@dataclass
class ProductData:
    """Resultado de la fase de obtención de datos (OFF o Gemini)."""

    source: Source
    nutrition: NutritionData
    barcode: str | None = None
    name: str | None = None
    off_categories: list[str] = field(default_factory=list)
    suggested_category: str | None = None
    suggested_confidence: str | None = None
    # Nutri-Score 2023 publicado por OFF, solo para comparar con el nuestro.
    off_grade_2023: str | None = None
    from_cache: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source"] = self.source.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ProductData:
        d = dict(d)
        d["source"] = Source(d["source"])
        d["nutrition"] = NutritionData.from_dict(d["nutrition"])
        return cls(**d)
