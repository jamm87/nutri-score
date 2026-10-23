from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATHS = (Path("config.toml"), Path(__file__).resolve().parents[2] / "config.toml")


@dataclass
class Config:
    raw: dict
    base_dir: Path

    @property
    def gemini(self) -> dict:
        return self.raw["gemini"]

    @property
    def image(self) -> dict:
        return self.raw["image"]

    @property
    def off(self) -> dict:
        return self.raw["off"]

    @property
    def db_path(self) -> Path:
        p = Path(self.raw["cache"]["db_path"])
        return p if p.is_absolute() else self.base_dir / p


def load_config(path: str | Path | None = None) -> Config:
    candidates = (Path(path),) if path else DEFAULT_PATHS
    for p in candidates:
        if p.is_file():
            with p.open("rb") as f:
                return Config(tomllib.load(f), p.resolve().parent)
    raise FileNotFoundError(f"No se encontró config.toml (buscado en: {', '.join(map(str, candidates))})")
