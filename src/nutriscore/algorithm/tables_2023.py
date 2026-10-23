"""Umbrales del algoritmo Nutri-Score revisado (2022 alimentos / 2023 bebidas).

FUENTES
-------
Especificación oficial (Santé publique France, Comité Científico del Nutri-Score):
  - "Update of the Nutri-Score algorithm" — informe anual 2022 (alimentos, incluye la
    categoría grasas/aceites/frutos secos/semillas, quesos y carne roja).
  - "Update of the Nutri-Score algorithm for beverages" — informe votado el 31/01/2023,
    adoptado por el comité de dirección el 30/03/2023 (bebidas, leche y bebidas vegetales,
    edulcorantes no nutritivos).
  - Página resumen: https://www.santepubliquefrance.fr/import/nutri-score-2023-update

Tablas transcritas de la implementación de referencia de Open Food Facts, que aplica esos
informes (función compute_nutriscore_score_2023 y hash %points_thresholds_2023):
  https://github.com/openfoodfacts/openfoodfacts-server/blob/main/lib/ProductOpener/Nutriscore.pm
  (rama main, consultado el 2026-10-23). Se verifican en tests/ contra los resultados
  esperados de OFF (tests/unit/expected_test_results/nutriscore/*.json).

REGLA DE PUNTUACIÓN
-------------------
Para cada componente, los puntos = número de umbrales que el valor SUPERA estrictamente
(valor > umbral). Excepción: la proporción saturadas/grasa total usa >= (así lo indica la
especificación y lo implementa OFF). Los valores no se redondean antes de comparar
(FAQ del Nutri-Score actualizada el 27/09/2022).

IMPORTANTE: este módulo contiene SOLO el algoritmo 2023. No mezclar con el de 2017/2021.
"""

from __future__ import annotations

# --- Componentes negativos -------------------------------------------------------------

# kJ / 100 g — alimentos
ENERGY = (335, 670, 1005, 1340, 1675, 2010, 2345, 2680, 3015, 3350)
# kJ / 100 ml — bebidas
ENERGY_BEVERAGES = (30, 90, 150, 210, 240, 270, 300, 330, 360, 390)

# g / 100 g — alimentos (máx. 15 puntos)
SUGARS = (3.4, 6.8, 10, 14, 17, 20, 24, 27, 31, 34, 37, 41, 44, 48, 51)
# g / 100 ml — bebidas
SUGARS_BEVERAGES = (0.5, 2, 3.5, 5, 6, 7, 8, 9, 10, 11)

# g / 100 g (máx. 10 puntos). En bebidas se usa la misma tabla.
SATURATED_FAT = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)

# g / 100 g (máx. 20 puntos). En bebidas se usa la misma tabla.
SALT = (0.2, 0.4, 0.6, 0.8, 1, 1.2, 1.4, 1.6, 1.8, 2, 2.2, 2.4, 2.6, 2.8, 3, 3.2, 3.4, 3.6, 3.8, 4)

# Solo categoría grasas/aceites/frutos secos/semillas: sustituyen a ENERGY y SATURATED_FAT.
# kJ procedentes de grasas saturadas / 100 g (= saturadas_g * 37)
ENERGY_FROM_SATURATED_FAT = (120, 240, 360, 480, 600, 720, 840, 960, 1080, 1200)
KJ_PER_G_SATURATED_FAT = 37
# % saturadas / grasa total — se compara con >=
SATURATED_FAT_RATIO = (10, 16, 22, 28, 34, 40, 46, 52, 58, 64)

# Solo bebidas: presencia de edulcorantes no nutritivos = 4 puntos negativos.
NON_NUTRITIVE_SWEETENERS_POINTS = 4

# --- Componentes positivos -------------------------------------------------------------

# % frutas/verduras/legumbres — alimentos: >40 → 1, >60 → 2, >80 → 5
# (la tabla repite 80 para que valores >80 sumen 3 umbrales más: total 5 puntos)
FRUITS_VEGETABLES_LEGUMES = (40, 60, 80, 80, 80)
# bebidas: >40 → 2, >60 → 4, >80 → 6
FRUITS_VEGETABLES_LEGUMES_BEVERAGES = (40, 40, 60, 60, 80, 80)

# g / 100 g (método AOAC). En bebidas se usa la misma tabla.
FIBER = (3.0, 4.1, 5.2, 6.3, 7.4)

# g / 100 g — alimentos
PROTEINS = (2.4, 4.8, 7.2, 9.6, 12, 14, 17)
# g / 100 ml — bebidas
PROTEINS_BEVERAGES = (1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0)

# --- Reglas especiales -----------------------------------------------------------------

# Las proteínas solo cuentan si los puntos negativos son < este umbral
# (salvo quesos y bebidas, donde cuentan siempre).
PROTEIN_NEGATIVE_LIMIT_GENERAL = 11
PROTEIN_NEGATIVE_LIMIT_FATS = 7
# Carne roja (vacuno, ternera, cerdo, cordero, caza, caballo…): máx. 2 puntos de proteína.
RED_MEAT_MAX_PROTEIN_POINTS = 2

# --- Letras: puntuación máxima (inclusive) para cada letra -------------------------------

GRADES_GENERAL = (("A", 0), ("B", 2), ("C", 10), ("D", 18))  # resto: E
GRADES_FATS = (("A", -6), ("B", 2), ("C", 10), ("D", 18))  # resto: E
# Bebidas: A reservada al agua.
GRADES_BEVERAGES = (("B", 2), ("C", 6), ("D", 9))  # resto: E
