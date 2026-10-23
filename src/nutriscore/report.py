"""Presentación del resultado (texto o JSON)."""

from __future__ import annotations

import json

from .algorithm.ranges import RangeResult
from .algorithm.score import Component
from .classify import Classification
from .gemini_extractor import GeminiUsage
from .models import ProductData

LABELS = {
    "energia_kj": "Energía (kJ)",
    "energia_de_saturadas_kj": "Energía de saturadas (kJ)",
    "azucares_g": "Azúcares (g)",
    "grasas_saturadas_g": "Grasas saturadas (g)",
    "proporcion_saturadas_pct": "Saturadas / grasa total (%)",
    "sal_g": "Sal (g)",
    "edulcorantes": "Edulcorantes no nutritivos",
    "proteinas_g": "Proteínas (g)",
    "fibra_g": "Fibra (g)",
    "frutas_verduras_legumbres_pct": "Frutas/verduras/legumbres (%) [ESTIMACIÓN]",
}


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _span(a, b, fmt=str) -> str:
    lo, hi = min(a, b), max(a, b)
    return fmt(lo) if lo == hi else f"{fmt(lo)}–{fmt(hi)}"


def _rows(best: list[Component], worst: list[Component]) -> list[dict]:
    rows = []
    for b, w in zip(best, worst):
        rows.append({
            "componente": b.id,
            "valor": b.value if b.value == w.value else [b.value, w.value],
            "puntos": b.points if b.points == w.points else [b.points, w.points],
            "puntos_max": b.points_max,
            "nota": w.note or b.note,
        })
    return rows


def to_dict(product: ProductData, cls: Classification, r: RangeResult, notices: list[str],
            usage: GeminiUsage | None) -> dict:
    n = product.nutrition
    return {
        "producto": product.name,
        "codigo_barras": product.barcode,
        "fuente": product.source.value,
        "desde_cache": product.from_cache,
        "categoria": r.category.value,
        "categoria_motivo": cls.reason,
        "letra": r.best.grade if r.grade_is_certain else None,
        "letras_posibles": r.grades,
        "puntuacion": r.best.score if r.is_exact else None,
        "puntuacion_rango": [r.best.score, r.worst.score],
        "negativos": _rows(r.best.negative, r.worst.negative),
        "positivos": _rows(r.best.positive, r.worst.positive),
        "datos_faltantes": [
            {"campo": m.label, "rango_supuesto": [m.best_value, m.worst_value],
             "puntuacion_si_solo_faltara_este": list(m.score_range_alone)}
            for m in r.missing
        ],
        "fvl_estimacion": {"rango_pct": n.fvl_percent_range, "nota": n.fvl_note},
        "conversiones": n.conversions,
        "campos_no_legibles": n.unreadable_fields,
        "nutriscore_2023_publicado_por_off": product.off_grade_2023,
        "gemini": None if usage is None else {
            "modelo": usage.model, "tokens_entrada": usage.input_tokens,
            "tokens_salida": usage.output_tokens, "tokens_razonamiento": usage.thinking_tokens,
            "coste_estimado_capa_pago_usd": usage.cost_paid_tier_usd,
            "coste_facturado_usd": usage.cost_billed_usd,
        },
        "avisos": notices,
    }


def render_json(*args) -> str:
    return json.dumps(to_dict(*args), ensure_ascii=False, indent=2)


def render_text(product: ProductData, cls: Classification, r: RangeResult, notices: list[str],
                usage: GeminiUsage | None) -> str:
    n = product.nutrition
    out: list[str] = []
    title = product.name or "Producto sin nombre"
    out.append(f"{title}" + (f"  [{product.barcode}]" if product.barcode else ""))
    src = product.source.value + (" (desde caché local)" if product.from_cache else "")
    out.append(f"Datos obtenidos de: {src}")
    out.append(f"Categoría: {r.category.value} — {cls.reason}")
    out.append("")

    if r.grade_is_certain:
        out.append(f"NUTRI-SCORE: {r.best.grade}   (puntuación {_span(r.best.score, r.worst.score)})")
    else:
        out.append(f"NUTRI-SCORE: entre {r.grades[0]} y {r.grades[-1]}   "
                   f"(puntuación {r.best.score} a {r.worst.score}; faltan datos que pueden cambiar la letra)")
    if product.off_grade_2023:
        same = "coincide" if product.off_grade_2023 in r.grades else "NO coincide"
        out.append(f"Nutri-Score 2023 publicado por OFF: {product.off_grade_2023} ({same})")
    out.append("")

    def table(title: str, best: list[Component], worst: list[Component]) -> None:
        out.append(title)
        for b, w in zip(best, worst):
            val = "sí" if b.id == "edulcorantes" and b.value else ("no" if b.id == "edulcorantes" else None)
            if b.id == "edulcorantes" and b.value != w.value:
                val = "desconocido"
            val = val or _span(b.value, w.value, _fmt)
            pts = _span(b.points, w.points)
            note = w.note or b.note
            out.append(f"  {LABELS.get(b.id, b.id):<45} {val:>12}   {pts:>5} / {b.points_max}"
                       + (f"   ({note})" if note else ""))

    table("Puntos negativos", r.best.negative, r.worst.negative)
    out.append(f"  {'Total negativos':<45} {'':>12}   {_span(r.best.negative_points, r.worst.negative_points):>5}")
    table("Puntos positivos", r.best.positive, r.worst.positive)
    out.append(f"  {'Total positivos':<45} {'':>12}   {_span(r.best.positive_points, r.worst.positive_points):>5}")
    out.append("")

    if r.missing:
        out.append("Datos que faltan y su impacto (no se rellenan con valores típicos):")
        for m in r.missing:
            lo, hi = m.score_range_alone
            vals = sorted((m.best_value, m.worst_value))
            shown = "sí o no" if m.field == "non_nutritive_sweeteners" else f"de {_fmt(vals[0])} a {_fmt(vals[1])}"
            out.append(f"  - {m.label}: puede valer {shown}; por sí solo movería la puntuación "
                       f"de {lo} a {hi}")
    out.append(f"ESTIMACIÓN de frutas/verduras/legumbres: {n.fvl_note}")
    for c in n.conversions:
        out.append(f"Conversión: {c}")
    if n.unreadable_fields:
        out.append("No legible en la foto: " + ", ".join(n.unreadable_fields))

    if usage:
        out.append("")
        out.append(f"Gemini ({usage.model}): {usage.input_tokens} tokens de entrada, "
                   f"{usage.output_tokens} de salida, {usage.thinking_tokens} de razonamiento. "
                   f"Coste estimado en capa de pago: {usage.cost_paid_tier_usd:.6f} $; "
                   f"facturado: {usage.cost_billed_usd:.6f} $")
    if notices:
        out.append("")
        out.extend(f"· {x}" for x in notices)
    return "\n".join(out)
