"""Shared vocabulary for the menu editor, guest filters and recipe comparisons."""

import re
import unicodedata
from enum import StrEnum


class Allergen(StrEnum):
    MILK = "milk"
    EGG = "egg"
    PEANUT = "peanut"
    TREE_NUT = "tree_nut"
    WHEAT = "wheat"
    GLUTEN = "gluten"
    SOY = "soy"
    SESAME = "sesame"
    MUSTARD = "mustard"
    FISH = "fish"
    CRUSTACEAN = "crustacean"
    MOLLUSC = "mollusc"
    CELERY = "celery"
    LUPIN = "lupin"
    SULPHITES = "sulphites"
    COCONUT = "coconut"


LABELS = dict(
    zip(
        Allergen,
        (
            "Milk / dairy",
            "Egg",
            "Peanuts",
            "Tree nuts",
            "Wheat",
            "Gluten cereals",
            "Soy",
            "Sesame",
            "Mustard",
            "Fish",
            "Crustaceans",
            "Molluscs",
            "Celery",
            "Lupin",
            "Sulphites",
            "Coconut",
        ),
        strict=True,
    )
)

_TERMS = {
    "milk": "milk|dairy|lactose|paneer|ghee|butter|cream|yogurt|yoghurt|curd|cheese|khoya|whey|casein|buttermilk|doodh|dudh|dahi|दूध|दही|पनीर|घी|मक्खन",
    "egg": "eggs|egg|albumen|anda|ande|अंडा|अंडे|अंडों",
    "peanut": "peanut|peanuts|groundnut|groundnuts|peanut butter|moongfali|mungfali|मूंगफली|मूँगफली",
    "tree_nut": "tree nut|tree nuts|treenuts|almond|almonds|cashew|cashews|pistachio|pistachios|walnut|walnuts|hazelnut|hazelnuts|pecans|pecan|brazil nuts|macadamia|badam|badaam|kaju|pista|बादाम|काजू|पिस्ता|अखरोट",
    "wheat": "wheat|atta|maida|semolina|sooji|suji|गेहूँ|गेहूं|आटा|मैदा|सूजी",
    "gluten": "gluten|barley|rye|malt|oats|oat|ग्लूटेन|जौ",
    "soy": "soy|soya|soybean|soybeans|tofu|tamari|miso|सोया|टोफू",
    "sesame": "sesame|tahini|til|तिल",
    "mustard": "mustard|sarson|rai|सरसों|राई",
    "fish": "fish|salmon|pomfret|rohu|cod|anchovy|anchovies|tuna|machhli|machli|मछली",
    "crustacean": "crustacean|crustaceans|prawns|prawn|shrimp|shrimps|lobster|crab|crabs|jhinga|झींगा",
    "mollusc": "mollusc|molluscs|mollusk|mollusks|squid|clam|clams|mussels|oyster|oysters|octopus",
    "celery": "celery|celeriac",
    "lupin": "lupin|lupine",
    "sulphites": "sulphite|sulphites|sulfite|sulfites|sulphur dioxide|sulfur dioxide",
    "coconut": "coconut|coconuts|coconut milk|coconut cream|nariyal|नारियल",
}
TERMS = {word: {code} for code, words in _TERMS.items() for word in words.split("|")}
TERMS.update(
    {
        "nuts": {"tree_nut", "peanut"},
        "nut": {"tree_nut", "peanut"},
        "shellfish": {"crustacean", "mollusc"},
        "seafood": {"crustacean", "mollusc", "fish"},
        "soy milk": {"soy"},
        "almond milk": {"tree_nut"},
        "oat milk": {"gluten"},
        "cashew cream": {"tree_nut"},
        "cocoa butter": set(),
        "butternut squash": set(),
        "oyster mushrooms": set(),
        "oyster mushroom": set(),
        "cream of tartar": set(),
    }
)
BOUND = r"[\w\u0900-\u097f]"
TERM = re.compile(
    r"(?<!"
    + BOUND
    + r")(?:"
    + "|".join(re.escape(t) for t in sorted(TERMS, key=len, reverse=True))
    + r")(?!"
    + BOUND
    + r")"
)


def normalize(text):
    return (
        unicodedata.normalize("NFKC", text)
        .casefold()
        .replace("’", "'")
        .replace("-", " ")
    )


def detected(text):
    return {
        code for match in TERM.finditer(normalize(text)) for code in TERMS[match[0]]
    }


def eligible(item, avoid):
    if not avoid:
        return True
    if item.get("recipe_status") not in {"reviewed", "sample"} or not item.get(
        "ingredients"
    ):
        return False
    # The written names also guard against a missed checkbox, including paid options.
    options = [o["name"] for g in item.get("groups", []) for o in g["options"]]
    recorded = set(item.get("allergens", [])) | set(item.get("may_contain", []))
    recorded |= detected(", ".join([item["name"], item["ingredients"], *options]))
    if "wheat" in recorded:
        recorded.add("gluten")
    return not recorded.intersection(avoid)


def choices():
    return [{"id": k.value, "name": v} for k, v in LABELS.items()]
