from nutriscore.classify import classify_from_off, classify_from_suggestion
from nutriscore.models import Category


def test_off_tags():
    assert classify_from_off(["en:beverages", "en:sodas"]).category == Category.BEVERAGE
    assert classify_from_off(["en:dairies", "en:milks"]).category == Category.BEVERAGE
    assert classify_from_off(["en:beverages", "en:waters", "en:spring-waters"]).category == Category.WATER
    flavored = ["en:beverages", "en:spring-waters", "en:flavored-waters"]
    assert classify_from_off(flavored).category == Category.BEVERAGE
    assert classify_from_off(["en:dairies", "en:cheeses"]).category == Category.CHEESE
    assert classify_from_off(["en:fats", "en:vegetable-oils", "en:olive-oils"]).category == Category.FATS
    assert classify_from_off(["en:nuts", "en:chestnuts"]).category == Category.GENERAL
    assert classify_from_off(["en:beverages", "en:soups"]).category == Category.GENERAL


def test_exempt_categories():
    c = classify_from_off(["en:beverages", "en:alcoholic-beverages", "en:wines"])
    assert c.exempt == "en:alcoholic-beverages"


def test_meat_is_doubtful_and_asks():
    c = classify_from_off(["en:meats", "en:sausages"])
    assert not c.certain and Category.RED_MEAT in c.candidates
    c = classify_from_off(["en:meats", "en:pork"])
    assert c.category == Category.RED_MEAT and not c.certain


def test_gemini_suggestion_needs_confirmation_for_special_categories():
    assert classify_from_suggestion("general", "alta").certain
    assert not classify_from_suggestion("general", "baja").certain
    assert not classify_from_suggestion("queso", "alta").certain
    assert not classify_from_suggestion(None, None).certain
