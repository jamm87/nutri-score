# nutriscore-cli

Calcula el **Nutri-Score (algoritmo revisado 2022/2023 de Santé publique France)** a partir
de fotos de la etiqueta. Está pensado para gastar lo mínimo:

1. **Código de barras (gratis).** Se lee en local con `zxing-cpp` y se consulta Open Food
   Facts. Si OFF tiene energía, azúcares, saturadas, sal y proteínas, no se llama a ninguna
   API de pago.
2. **Gemini (de pago, una sola llamada).** Solo si no hay datos completos en OFF. Se envían
   todas las fotos reducidas (1024 px por defecto) en una única llamada, con salida JSON
   estructurada y sin razonamiento (*thinking*).
3. **Caché SQLite.** Guarda los resultados por código de barras y por huella de las fotos,
   así no se paga dos veces por el mismo producto.
4. **Cálculo determinista en Python.** El LLM solo transcribe valores; nunca calcula puntos.

## Instalación

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
export GEMINI_API_KEY=...   # clave de Google AI Studio (solo hace falta si se usa Gemini)
```

## Uso

```bash
# Una o varias fotos del mismo producto (tabla, ingredientes, código de barras)
nutriscore analizar tabla.jpg ingredientes.jpg
nutriscore analizar tabla.jpg --codigo 8410000000009   # si el código no sale en la foto
nutriscore analizar --codigo 8410000000009             # solo OFF, sin fotos
nutriscore analizar foto.jpg --categoria queso --json

# Valores tecleados a mano (sin coste)
nutriscore manual --categoria general --energia-kj 1762 --azucares 13.9 --saturadas 0 \
  --sal 6.81 --proteinas 7.2 --fvl 0

# Tokens y coste acumulado de Gemini
nutriscore costes
```

Categorías: `general`, `bebida`, `agua`, `grasas` (grasas, aceites, frutos secos y
semillas), `queso`, `carne_roja`. Si la categoría es dudosa, el programa pregunta. Sin
terminal interactiva, pide `--categoria`.

## Qué muestra

- La letra y la puntuación, con el desglose de cada componente (valor, puntos y máximo).
- La fuente de los datos: Open Food Facts, Gemini o caché.
- **Datos que faltan.** Nunca se rellenan con valores "típicos". Se calcula el mejor y el
  peor caso dentro de los límites físicos (0–100 g, 3700 kJ). Si la letra puede cambiar,
  se muestra el rango de letras y cuánto pesa cada dato que falta.
- **% de frutas, verduras y legumbres: siempre marcado como ESTIMACIÓN.** Se calcula desde
  la lista de ingredientes con los porcentajes declarados y la regla de orden decreciente
  de peso, y se usa como intervalo.
- Las conversiones aplicadas (sodio → sal ×2,5; kcal → kJ ×4,184) y los campos no legibles.
- Con Gemini: tokens de entrada y salida, y el coste estimado.
- Con OFF: el Nutri-Score 2023 que publica OFF, para comparar.

## Configuración (`config.toml`)

| Clave | Para qué |
|---|---|
| `gemini.model` | Modelo; por defecto `gemini-2.5-flash-lite` (el de visión más barato, 0,10 $/1M tokens de entrada) |
| `gemini.price_*` | Precios para estimar el coste. **El de salida está sin verificar**: compruébalo en la [página de precios](https://ai.google.dev/gemini-api/docs/pricing) |
| `gemini.free_tier` | `true` = el coste facturado se registra como 0 |
| `image.max_side_px` | Resolución enviada a Gemini; súbela solo si aparecen campos ilegibles |

Para cambiar de modelo basta con editar una línea, por ejemplo `gemini-3.1-flash-lite`
(0,25 $/1M de entrada). `gemini-2.5-flash-lite` no tiene fecha de retirada en la API de
Gemini, pero Google recomienda modelos 3.x para proyectos nuevos.

## ⚠️ Privacidad en la capa gratuita de Gemini

Según los [términos de la API de Gemini](https://ai.google.dev/gemini-api/terms), Google puede
usar lo que se envía en la capa gratuita para mejorar sus productos, y revisores humanos
pueden leerlo. **Excepción:** en el EEE, Suiza y Reino Unido se aplican también al uso
gratuito los términos de pago, y Google no usa esos datos para mejorar sus productos. Aun así,
no envíes fotos con datos personales.

## Fuentes del algoritmo

- Santé publique France — [Nutri-Score 2023 update](https://www.santepubliquefrance.fr/import/nutri-score-2023-update):
  informe de alimentos 2022 e informe de bebidas votado el 31/01/2023 y adoptado el 30/03/2023.
- Las tablas de umbrales están transcritas de la implementación de referencia de Open Food Facts,
  [`Nutriscore.pm`](https://github.com/openfoodfacts/openfoodfacts-server/blob/main/lib/ProductOpener/Nutriscore.pm),
  que aplica esos informes. Las citas están en `src/nutriscore/algorithm/tables_2023.py`.
- La lista de edulcorantes no nutritivos sale de la taxonomía de aditivos de OFF
  (`non_nutritive_sweetener:en: yes`).

## Tests

```bash
.venv/bin/python -m pytest
```

- `test_score_off_cases.py`: 51 productos de los tests oficiales de Open Food Facts, con su
  Nutri-Score 2023 esperado (puntos por componente, puntuación y letra).
- `test_score_rules.py`: el caso real (1762 kJ, azúcares 13,9 g, sal 6,81 g, proteínas 7,2 g,
  fibra sin declarar, FVL 0 %), que da **E** en todo el rango posible (23–28). También
  cubre las reglas de quesos, carne roja, agua y edulcorantes.
- `test_pipeline.py`: el flujo OFF → Gemini → caché, con dobles de prueba y sin red.

## Estructura

```
src/nutriscore/
  algorithm/tables_2023.py  umbrales oficiales con su fuente
  algorithm/score.py        cálculo puro (sin LLM)
  algorithm/ranges.py       rango de puntuación con datos que faltan
  imaging.py                código de barras (zxing-cpp) y reducción de imagen
  off_client.py             Open Food Facts
  gemini_extractor.py       una llamada con JSON schema y registro de tokens
  fvl.py, sweeteners.py     ESTIMACIÓN de FVL y detección de edulcorantes
  classify.py               categoría (reglas de OFF y sugerencia de Gemini)
  cache.py                  SQLite: productos y coste de cada llamada
  pipeline.py, report.py, cli.py
```
