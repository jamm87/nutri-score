"""Caché local (SQLite) de productos y registro de llamadas a Gemini."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import ProductData

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    key TEXT PRIMARY KEY,          -- 'barcode:<EAN>' o 'image:<sha256>'
    source TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gemini_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    key TEXT,
    model TEXT NOT NULL,
    images INTEGER NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    thinking_tokens INTEGER,
    total_tokens INTEGER,
    cost_usd_paid_tier REAL,       -- lo que costaría en la capa de pago
    cost_usd_billed REAL           -- 0 si se usa la capa gratuita
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Cache:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)

    def get(self, key: str) -> ProductData | None:
        row = self.conn.execute("SELECT data FROM products WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        product = ProductData.from_dict(json.loads(row[0]))
        product.from_cache = True
        return product

    def put(self, key: str, product: ProductData) -> None:
        data = product.to_dict()
        data["from_cache"] = False
        self.conn.execute(
            "INSERT OR REPLACE INTO products (key, source, data, created_at) VALUES (?, ?, ?, ?)",
            (key, product.source.value, json.dumps(data, ensure_ascii=False), _now()),
        )
        self.conn.commit()

    def log_gemini_call(self, *, key: str | None, model: str, images: int, input_tokens: int,
                        output_tokens: int, thinking_tokens: int, total_tokens: int,
                        cost_paid_tier: float, cost_billed: float) -> None:
        self.conn.execute(
            "INSERT INTO gemini_calls (ts, key, model, images, input_tokens, output_tokens, thinking_tokens,"
            " total_tokens, cost_usd_paid_tier, cost_usd_billed) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (_now(), key, model, images, input_tokens, output_tokens, thinking_tokens, total_tokens,
             cost_paid_tier, cost_billed),
        )
        self.conn.commit()

    def cost_summary(self) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0),"
            " COALESCE(SUM(thinking_tokens),0), COALESCE(SUM(cost_usd_paid_tier),0),"
            " COALESCE(SUM(cost_usd_billed),0) FROM gemini_calls"
        ).fetchone()
        products = self.conn.execute("SELECT source, COUNT(*) FROM products GROUP BY source").fetchall()
        return {
            "llamadas_gemini": row[0],
            "tokens_entrada": row[1],
            "tokens_salida": row[2],
            "tokens_razonamiento": row[3],
            "coste_estimado_capa_pago_usd": row[4],
            "coste_facturado_usd": row[5],
            "productos_en_cache": dict(products),
        }
