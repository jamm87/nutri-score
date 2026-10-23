"""Interfaz de línea de comandos.

  nutriscore analizar FOTO [FOTO...] [--codigo EAN] [--categoria X] [--json]
  nutriscore manual --categoria X [--energia-kj N ...]   (sin coste: valores tecleados)
  nutriscore costes                                      (tokens y coste acumulado)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import report
from .algorithm.ranges import evaluate
from .cache import Cache
from .classify import Classification, classify_from_off, classify_from_suggestion
from .config import load_config
from .models import Category, NutritionData, ProductData, Source
from .normalize import derive_from_ingredients, fill_conversions
from .pipeline import PipelineError, obtain

CATEGORY_HELP = ", ".join(c.value for c in Category)


def _category_arg(value: str) -> Category:
    try:
        return Category(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"categoría no válida; opciones: {CATEGORY_HELP}")


def resolve_category(product: ProductData, forced: Category | None) -> Classification:
    if forced is not None:
        return Classification(forced, True, "indicada por el usuario")
    cls = classify_from_off(product.off_categories)
    if cls is None:
        cls = classify_from_suggestion(product.suggested_category, product.suggested_confidence)
    if cls.exempt:
        return cls
    if not cls.certain:
        cls = ask_category(cls)
    return cls


def ask_category(cls: Classification) -> Classification:
    options = cls.candidates or list(Category)
    if not sys.stdin.isatty():
        raise SystemExit(
            f"Categoría dudosa ({cls.reason}). Indícala con --categoria ({CATEGORY_HELP})."
        )
    print(f"La categoría es dudosa: {cls.reason}", file=sys.stderr)
    for i, c in enumerate(options, 1):
        print(f"  {i}. {c.value}" + ("  (sugerida)" if c == cls.category else ""), file=sys.stderr)
    while True:
        ans = input(f"Elige categoría [1-{len(options)}, Intro = {cls.category.value}]: ").strip()
        if not ans:
            return Classification(cls.category, True, cls.reason + "; confirmada por el usuario")
        if ans.isdigit() and 1 <= int(ans) <= len(options):
            return Classification(options[int(ans) - 1], True, "elegida por el usuario")


def show(product: ProductData, cls: Classification, notices: list[str], usage, as_json: bool) -> int:
    if cls.exempt:
        msg = f"El Nutri-Score no se aplica a este producto: {cls.reason}"
        print(json.dumps({"aplicable": False, "motivo": msg}, ensure_ascii=False) if as_json else msg)
        return 0
    result = evaluate(product.nutrition, cls.category)
    render = report.render_json if as_json else report.render_text
    print(render(product, cls, result, notices, usage))
    return 0


def cmd_analizar(args) -> int:
    cfg = load_config(args.config)
    cache = None if args.sin_cache else Cache(cfg.db_path)
    for p in args.fotos:
        if not p.is_file():
            raise SystemExit(f"No existe la imagen: {p}")
    try:
        got = obtain(args.fotos, cfg, cache, barcode=args.codigo)
    except PipelineError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    cls = resolve_category(got.product, args.categoria)
    return show(got.product, cls, got.notices, got.usage, args.json)


def cmd_manual(args) -> int:
    n = NutritionData(
        energy_kj=args.energia_kj, sugars_g=args.azucares, fat_g=args.grasas,
        saturated_fat_g=args.saturadas, salt_g=args.sal, proteins_g=args.proteinas,
        fiber_g=args.fibra, ingredients=args.ingredientes,
    )
    fill_conversions(n, sodium_mg=args.sodio_mg, energy_kcal=args.energia_kcal)
    derive_from_ingredients(n, fvl_override=args.fvl,
                            fvl_override_note="ESTIMACIÓN indicada por el usuario" if args.fvl is not None else "")
    if args.edulcorantes is not None:
        n.non_nutritive_sweeteners = args.edulcorantes == "si"
    product = ProductData(source=Source.MANUAL, nutrition=n, name=args.nombre)
    cls = Classification(args.categoria, True, "indicada por el usuario")
    return show(product, cls, [], None, args.json)


def cmd_costes(args) -> int:
    cfg = load_config(args.config)
    print(json.dumps(Cache(cfg.db_path).cost_summary(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nutriscore", description="Nutri-Score 2023 desde fotos de la etiqueta")
    p.add_argument("--config", help="ruta a config.toml")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analizar", help="analiza una o varias fotos del mismo producto")
    a.add_argument("fotos", nargs="*", type=Path, help="fotos de la etiqueta (tabla, ingredientes, código)")
    a.add_argument("--codigo", help="código de barras, si no se ve en la foto")
    a.add_argument("--categoria", type=_category_arg, help=f"fuerza la categoría ({CATEGORY_HELP})")
    a.add_argument("--json", action="store_true", help="salida en JSON")
    a.add_argument("--sin-cache", action="store_true", help="no leer ni escribir la caché local")
    a.set_defaults(func=cmd_analizar)

    m = sub.add_parser("manual", help="calcula con valores introducidos a mano (sin coste)")
    m.add_argument("--categoria", type=_category_arg, required=True, help=CATEGORY_HELP)
    m.add_argument("--nombre")
    for flag in ("energia-kj", "energia-kcal", "azucares", "grasas", "saturadas", "sal",
                 "sodio-mg", "proteinas", "fibra"):
        m.add_argument(f"--{flag}", type=float)
    m.add_argument("--fvl", type=float, help="%% de frutas/verduras/legumbres (se marca como ESTIMACIÓN)")
    m.add_argument("--ingredientes", help="lista de ingredientes (para estimar FVL y edulcorantes)")
    m.add_argument("--edulcorantes", choices=("si", "no"), help="solo bebidas")
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_manual)

    c = sub.add_parser("costes", help="resumen de tokens y coste de Gemini")
    c.set_defaults(func=cmd_costes)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "analizar" and not args.fotos and not args.codigo:
        raise SystemExit("Indica al menos una foto o --codigo")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
