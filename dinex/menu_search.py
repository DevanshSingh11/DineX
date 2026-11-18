"""Deterministic search of all currently available dishes in one restaurant."""

import re
from decimal import Decimal

from .allergens import detected, normalize

WORDS = re.compile(r"[a-z0-9]+|[\u0900-\u097f]+")
FILLER = set(
    """a an the and or is are was can could would what which how i im i'm i'd id
    me my we us you your any this that it something some have has having want like feel feeling
    recommend recommendations suggest suggestive give get find look looking for show please
    need serve served serves dish dishes item items menu menus option options only available
    m d ve re ll should goes into there out today match matches all on of to from with in at by does do contain contains list listed
    ingredients ingredient compare sort order find try good best tasty under below less than
    up most maximum max budget within rupees rs inr around go craving vegetarian vegan veg
    non nonveg meat free allergy allergies allergic safe avoid without no exclude excluding
    staff allergy sensitive am i'm got has cannot eat having per person what s t can
    kuch koi mera meri mujhe mein hai hain dikhao batao chahiye ke ki ka se ko aur
    मुझे कोई कुछ में है हैं चाहिए दिखाओ का की के से और बताओ मदद""".split()
)
TRANSLATE = {
    "मीठा": "dessert",
    "मिठाई": "dessert",
    "meetha": "dessert",
    "mithai": "dessert",
    "शाकाहारी": "vegetarian",
    "शाकाहार": "vegetarian",
    "शाकाहारी खाना": "vegetarian",
    "वीगन": "vegan",
    "बिरयानी": "biryani",
    "पनीर": "paneer",
    "आलू": "aloo",
    "चावल": "rice",
    "चिकन": "chicken",
    "मशरूम": "mushroom",
    "मसालेदार": "spicy",
    "तीखा": "spicy",
    "teekha": "spicy",
    "तीखी": "spicy",
    "तीखे": "spicy",
    "स्टार्टर": "starter",
    "मिठाइयाँ": "dessert",
    "मिठाइयां": "dessert",
    "डोसा": "dosa",
    "इडली": "idli",
    "सूप": "soup",
    "ठंडा": "cold",
    "शरबत": "cooler",
    "रुपये": "rupees",
    "रुपए": "rupees",
    "पेय": "drink",
}
COURSES = {
    "dessert": ("dessert", "sweet", "cake", "ice cream", "frozen", "mithai"),
    "starter": ("starter", "small plate", "chaat", "appetizer", "appetiser", "snack"),
    "assortment": ("assortment", "platter", "thali", "sharing"),
    "drink": ("drink", "cooler", "beverage", "coffee", "tea bar"),
    "main": ("curries", "mains", "biryani", "entree", "wok"),
    "breakfast": ("breakfast",),
    "soup": ("soup",),
    "salad": ("salad",),
    "bread": ("bread",),
    "side": ("side", "accompaniment"),
}
SYNONYMS = {
    "desserts": "dessert",
    "sweets": "dessert",
    "sweet": "dessert",
    "appetizer": "starter",
    "appetiser": "starter",
    "appetizers": "starter",
    "starters": "starter",
    "platters": "assortment",
    "platter": "assortment",
    "assorted": "assortment",
    "assortments": "assortment",
    "drinks": "drink",
    "beverages": "drink",
    "beverage": "drink",
    "soups": "soup",
    "salads": "salad",
    "breads": "bread",
    "sides": "side",
    "spiced": "spicy",
    "fiery": "spicy",
    "hot": "hot",
    "tart": "tangy",
    "crunchy": "crispy",
    "crisp": "crispy",
    "chilled": "cold",
    "aubergine": "eggplant",
    "prawns": "prawn",
    "noodles": "noodle",
    "mushrooms": "mushroom",
}
PRICE = re.compile(
    r"\b(under|below|less than|up to|at most|within|budget(?: of)?|maximum|max)\s*"
    r"(?:₹|\$|€|£|rs\.?|inr|usd|eur|gbp)?\s*(\d+(?:[,.]\d{3})*(?:\.\d{1,2})?)"
)


def english_text(value):
    value = normalize(value).replace("।", " ").replace("॥", " ")
    for original, replacement in TRANSLATE.items():
        value = value.replace(original, replacement)
    return re.sub(
        r"(?:₹\s*)?(\d+)\s*(?:rupees?\s*)?(?:से कम|se kam|के अंदर|ke andar)",
        r"under \1",
        value,
    )


def tokens(s):
    return {
        SYNONYMS.get(w, w)
        for w in WORDS.findall(s)
        if w not in FILLER and not w.isdecimal()
    }


def price_caps(s):
    return [
        (
            int(Decimal(m[2].replace(",", "")) * 100),
            m[1] not in {"under", "below", "less than"},
        )
        for m in PRICE.finditer(s)
    ]


def apply_limits(items, *queries):
    queries = [english_text(s) for s in queries]
    diet = {"vegetarian", "vegan", "non-vegetarian", "unspecified"}
    for q in queries:
        if re.search(r"\bnon\s?veg(?:etarian)?\b", q):
            diet &= {"non-vegetarian"}
        elif re.search(r"\bvegan\b", q):
            diet &= {"vegan"}
        elif re.search(r"\bveg(?:etarian)?\b", q):
            diet &= {"vegan", "vegetarian"}
    caps = [c for q in queries for c in price_caps(q)]
    return [
        i
        for i in items
        if i["dietary"] in diet
        and all(
            i["price"] <= limit if inclusive else i["price"] < limit
            for limit, inclusive in caps
        )
    ]


def rank_all(items, question):
    q = english_text(question)
    terms = tokens(PRICE.sub(" ", q))
    cheapest = bool(terms & {"cheap", "cheapest", "affordable", "budget"})
    terms -= {"cheapest", "cheap", "affordable", "first"}
    requested = {c for c in COURSES if c in terms}
    categories = {english_text(i["category"]) for i in items}
    known = {
        c for c in requested if any(w in cat for w in COURSES[c] for cat in categories)
    }
    terms -= known
    named = [
        i
        for i in items
        if re.search(r"(?<!\w)" + re.escape(normalize(i["name"])) + r"(?!\w)", q)
    ]
    if named:
        return sorted(named, key=lambda i: (-len(i["name"]), i["id"]))
    scores = []
    for row in items:
        if "seafood" in terms:
            marine = detected(row["ingredients"]) & {"fish", "mollusc", "crustacean"}
            if not marine:
                continue
        category = english_text(row["category"])
        if known and not any(w in category for c in known for w in COURSES[c]):
            continue
        name = tokens(english_text(row["name"]))
        category_words = tokens(category)
        description = tokens(english_text(row["description"]))
        ingredients = tokens(english_text(row["ingredients"]))
        score = (
            8 * len(terms & name)
            + 4 * len(terms & category_words)
            + 2 * len(terms & description)
            + len(terms & ingredients)
        )
        if terms and not score:
            continue
        scores.append((score, row))
    scores.sort(
        key=lambda pair: (
            pair[1]["price"] if cheapest else 0,
            -pair[0],
            not pair[1]["featured"],
            pair[1]["name"],
        )
    )
    return [row for _, row in scores]
