from nutriscore.fvl import estimate_fvl
from nutriscore.sweeteners import find_non_nutritive_sweeteners


def test_sweeteners_by_name_and_e_number():
    assert find_non_nutritive_sweeteners(
        "agua, edulcorantes (ciclamato sódico, acesulfamo K, sucralosa)") == ["E950", "E952", "E955"]
    assert find_non_nutritive_sweeteners("water, sugar, E-951") == ["E951"]
    assert find_non_nutritive_sweeteners("agua, glucósidos de esteviol") == ["E960"]


def test_polyols_are_not_non_nutritive_sweeteners():
    assert find_non_nutritive_sweeteners("zumo, eritritol (E968), sorbitol E420") == []


def test_no_ingredients_means_unknown():
    assert find_non_nutritive_sweeteners(None) is None
    assert find_non_nutritive_sweeteners("  ") is None


def test_fvl_zero_when_no_fvl_ingredient():
    e = estimate_fvl("Harina de trigo, azúcar, aceite de palma, sal")
    assert (e.low, e.high) == (0, 0)
    assert "ESTIMACIÓN" in e.note


def test_fvl_declared_percentages_and_order_bounds():
    e = estimate_fvl("Tomate (45%), pimiento 20%, cebolla, aceite de oliva virgen extra (3%), sal")
    # cebolla sin %: entre 3 % (siguiente declarado) y 20 % (anterior declarado)
    assert (e.low, e.high) == (71.0, 88.0)


def test_fvl_upper_bound_by_position():
    e = estimate_fvl("Agua, zumo de naranja, azúcar")
    assert (e.low, e.high) == (0.0, 50.0)


def test_potatoes_and_flavourings_do_not_count():
    assert estimate_fvl("patatas, aceite de girasol, sal").high == 0
    assert estimate_fvl("agua, azúcar, aroma de fresa").high == 0


def test_word_boundaries_avoid_false_positives():
    # "pera" dentro de "temperatura", "ajo" dentro de "trabajo"
    assert estimate_fvl("leche tratada a alta temperatura, trabajo artesanal").high == 0
