from __future__ import annotations

import re
from typing import Any

MASTER_CATEGORIES = [
    "Flower", "Pre-Rolls", "Vapes", "Edibles", "Concentrates", "Topicals", "Tinctures", "Beverages", "Accessories", "Other",
]


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _canon_category(value: str) -> str:
    n = _norm(value)
    mapping = {
        "flower": "Flower", "pre-rolls": "Pre-Rolls", "pre roll": "Pre-Rolls", "prerolls": "Pre-Rolls",
        "vapes": "Vapes", "edibles": "Edibles", "concentrates": "Concentrates", "topicals": "Topicals",
        "tinctures": "Tinctures", "beverages": "Beverages", "accessories": "Accessories", "other": "Other",
    }
    return mapping.get(n, "")


def normalize_competitor_category(product_name: str = "", raw_text: str = "", page_category: str = "", existing_category: str = "", existing_subcategory: str = "") -> dict:
    text = _norm(f"{product_name} {raw_text}")
    page = _canon_category(page_category)
    existing = _canon_category(existing_category)

    vape_terms = ["cart", "cartridge", "vape", "disposable", "all-in-one", "aio", "pod", "vape pen"]
    preroll_terms = ["pre-roll", "preroll", "joint", "blunt", "cannagar", "cigarillo", "dogwalker", "mini pre-roll", "mini joint"]
    edible_terms = ["gummy", "gummies", "chews", "chocolate", "brownie", "cookie", "mint", "mints", "candy", "capsule", "softgel", "tablet"]
    mg_hint = "mg" in text

    def finish(category: str, sub: str, source: str = "product_text", conf: str = "High"):
        return {"category": category, "subcategory": sub, "product_type": sub, "category_confidence": conf, "category_source": source}

    # precedence: vape over concentrate
    if _has_any(text, vape_terms):
        if _has_any(text, ["live resin cart", "live resin cartridge", "llr cart", "llr cartridge", "liquid live resin cart", "liquid live resin cartridge"]):
            return finish("Vapes", "Live Resin Cartridge")
        if _has_any(text, ["live rosin cart", "rosin cart", "rosin cartridge", "solventless cart", "solventless cartridge"]):
            return finish("Vapes", "Live Rosin Cartridge")
        if _has_any(text, ["disposable", "all-in-one", "aio", "vape pen"]):
            return finish("Vapes", "Disposable")
        if _has_any(text, ["pod", "pax pod", "era pod"]):
            return finish("Vapes", "Pod")
        return finish("Vapes", "Distillate Cartridge")

    # precedence: pre-roll over flower
    if _has_any(text, preroll_terms):
        if _has_any(text, ["infused pre-roll", "infused preroll", "infused joint", "hash infused", "kief infused", "rosin infused", "resin infused", "diamond infused"]):
            return finish("Pre-Rolls", "Infused Pre-Roll")
        if _has_any(text, ["2pk", "2 pack", "5pk", "5 pack", "10pk", "10 pack", "multipack", "multi-pack"]):
            return finish("Pre-Rolls", "Multi-Pack")
        if _has_any(text, ["blunt", "cannagar", "cigarillo"]):
            return finish("Pre-Rolls", "Blunt")
        if _has_any(text, ["dogwalker", "mini pre-roll", "mini joint"]):
            return finish("Pre-Rolls", "Dogwalker")
        return finish("Pre-Rolls", "Standard Pre-Roll")

    # edible override concentrate with mg hint
    if _has_any(text, edible_terms) and mg_hint:
        if _has_any(text, ["gummy", "gummies", "chews", "fruit chews"]):
            return finish("Edibles", "Gummies")
        if _has_any(text, ["chocolate", "bar", "truffle"]):
            return finish("Edibles", "Chocolate")
        if _has_any(text, ["brownie", "cookie", "cereal treat", "rice crispy", "blondie"]):
            return finish("Edibles", "Baked Goods")
        if _has_any(text, ["candy", "lozenge", "hard candy", "taffy"]):
            return finish("Edibles", "Candy")
        if _has_any(text, ["capsule", "capsules", "softgel", "soft gel", "tablet"]):
            return finish("Edibles", "Capsules")
        if _has_any(text, ["mint", "mints"]):
            return finish("Edibles", "Mints")
        return finish("Edibles", "Edible")

    if _has_any(text, ["tincture", "drops", "oral solution"]):
        return finish("Tinctures", "Tincture")
    if _has_any(text, ["beverage", "drink", "seltzer", "soda", "tea", "lemonade", "tonic"]):
        return finish("Beverages", "Beverage")
    if _has_any(text, ["papers", "grinder", "pipe", "bong", "battery", "lighter", "tray", "accessory"]):
        return finish("Accessories", "Accessory")

    conc_map = [
        ("Live Rosin", ["live rosin", "cold cure rosin", "cold cured rosin", "solventless rosin", "rosin jam", "rosin badder", "rosin batter"]),
        ("Live Resin", ["live resin", "llr", "liquid live resin", "cured live resin"]),
        ("RSO", ["rso", "rick simpson oil"]),
        ("Distillate", ["distillate", "dart", "syringe"]),
        ("Shatter", ["shatter"]),
        ("Wax", ["wax"]),
        ("Badder", ["badder", "batter", "budder", "butter"]),
        ("Sugar", ["sugar", "live sugar"]),
        ("Sauce", ["terp sauce", "diamonds and sauce", "diamonds & sauce", "sauce"]),
        ("Diamonds", ["thca diamonds", "diamonds"]),
        ("Crumble", ["crumble"]),
        ("Hash", ["bubble hash", "temple ball", "hash"]),
        ("Kief", ["kief"]),
        ("Resin", ["cured resin", "resin"]),
        ("Rosin", ["rosin"]),
    ]
    for sub, terms in conc_map:
        if _has_any(text, terms):
            return finish("Concentrates", sub)

    if _has_any(text, ["lotion", "cream", "balm", "salve", "patch", "transdermal", "roll-on", "roll on", "bath bomb", "soak", "epsom", "lubricant", "lube"]):
        if "lotion" in text: return finish("Topicals", "Lotion")
        if "cream" in text: return finish("Topicals", "Cream")
        if "patch" in text or "transdermal" in text: return finish("Topicals", "Patch")
        if "roll-on" in text or "roll on" in text: return finish("Topicals", "Roll-On")
        if _has_any(text, ["bath bomb", "soak", "epsom"]): return finish("Topicals", "Bath")
        if _has_any(text, ["lubricant", "lube"]): return finish("Topicals", "Lubricant")
        return finish("Topicals", "Balm")

    if _has_any(text, ["flower", "buds", "premium flower", "smalls", "small buds", "popcorn", "shake", "ground flower", "trim", "bulk flower", "14g", "half ounce", "28g", "ounce", " oz", "moon rocks", "infused flower"]):
        if _has_any(text, ["smalls", "small buds", "popcorn"]): return finish("Flower", "Small Buds")
        if "shake" in text: return finish("Flower", "Shake")
        if _has_any(text, ["ground flower", " ground "]): return finish("Flower", "Ground Flower")
        if "trim" in text: return finish("Flower", "Trim")
        if _has_any(text, ["bulk flower", "14g", "half ounce", "28g", " ounce", " oz"]): return finish("Flower", "Bulk Flower")
        if _has_any(text, ["moon rocks", "infused flower"]): return finish("Flower", "Moon Rocks")
        return finish("Flower", "Whole Flower")

    if page:
        fallback_sub = {
            "Concentrates": "Concentrate", "Vapes": "Vape", "Flower": "Flower", "Pre-Rolls": "Pre-Roll", "Edibles": "Edible", "Topicals": "Topical",
            "Tinctures": "Tincture", "Beverages": "Beverage", "Accessories": "Accessory", "Other": "Other",
        }.get(page, "Other")
        return finish(page, existing_subcategory or fallback_sub, "page_url", "Medium")
    if existing:
        return finish(existing, existing_subcategory or existing, "existing_field", "Low")
    return finish("Other", existing_subcategory or "Other", "fallback", "Low")
