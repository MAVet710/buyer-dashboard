"""Shared extraction-inventory eligibility rules.

Extraction works from the same durable inventory ledger as Production.  This
module only defines which products belong in the Extraction working projection;
it never changes, deletes, or moves inventory records.
"""

from __future__ import annotations

from dataclasses import dataclass


WEIGHT_UNITS = {
    "g",
    "gram",
    "grams",
    "kg",
    "kilogram",
    "kilograms",
    "oz",
    "ounce",
    "ounces",
    "lb",
    "lbs",
    "pound",
    "pounds",
}

SOURCE_TERMS = (
    "bulk flower",
    "flower",
    "trim",
    "shake",
    "biomass",
    "fresh frozen",
    "fresh-frozen",
    "fresh frozen material",
    "dry material",
    "plant material",
    "kief",
    "dry sift",
    "hash",
)

WIP_TERMS = (
    "wip",
    "work in process",
    "work-in-process",
    "crude",
    "winterized",
    "filtered oil",
    "decarb",
    "decarbed",
    "distillate",
    "resin",
    "rosin",
    "concentrate",
    "sauce",
    "diamonds",
    "terp fraction",
    "terpene fraction",
    "extract",
)

BULK_TERMS = (
    "bulk",
    "unpackaged",
    "intermediate",
    "wip",
    "work in process",
    "work-in-process",
)

# These descriptors represent consumer-ready or unrelated production items.
# Explicit bulk/WIP classification still wins where appropriate.
CONSUMER_READY_TERMS = (
    "pre-roll",
    "pre roll",
    "preroll",
    "gummy",
    "gummies",
    "edible",
    "cartridge",
    "disposable",
    "vape",
    "packaged flower",
    "retail flower",
    "eighth",
    "1/8",
    "quarter ounce",
    "half ounce",
    "multipack",
    "multi-pack",
    "retail-ready",
    "retail ready",
)

PACKAGING_TERMS = (
    "label",
    "jar",
    "bottle",
    "cap",
    "lid",
    "carton",
    "case",
    "pouch",
    "bag",
    "tube",
    "cartridge hardware",
    "vape hardware",
)


@dataclass(frozen=True)
class ExtractionEligibility:
    eligible: bool
    role: str
    reason: str


def _descriptor(*values: str) -> str:
    return " ".join(str(value or "").strip().casefold() for value in values if value).replace("_", " ")


def classify_extraction_inventory(
    *,
    item_type: str,
    product_name: str,
    sku: str = "",
    base_unit: str = "",
    category: str = "",
    subcategory: str = "",
    product_format: str = "",
) -> ExtractionEligibility:
    """Classify a Product Master item for the Extraction working inventory.

    The rule favors durable product semantics over package quantity.  A package
    can contain a large or small amount without changing what the product is.
    """

    kind = str(item_type or "").strip().casefold().replace(" ", "_")
    unit = str(base_unit or "").strip().casefold()
    text = _descriptor(product_name, sku, category, subcategory, product_format)
    explicit_bulk = any(token in text for token in BULK_TERMS)
    wip_like = kind == "wip" or any(token in text for token in WIP_TERMS)

    if kind == "packaging" or any(token in text for token in PACKAGING_TERMS):
        return ExtractionEligibility(False, "excluded", "Packaging or non-cannabis production material")

    if any(token in text for token in CONSUMER_READY_TERMS) and not explicit_bulk and not wip_like:
        return ExtractionEligibility(False, "excluded", "Consumer-ready packaged product")

    if wip_like:
        return ExtractionEligibility(True, "extraction_wip", "Extraction work-in-process or intermediate")

    if kind == "cannabis":
        if any(token in text for token in SOURCE_TERMS):
            return ExtractionEligibility(True, "source_material", "Cannabis source material")
        if unit in WEIGHT_UNITS:
            return ExtractionEligibility(True, "source_material", "Weight-based cannabis source material")
        return ExtractionEligibility(False, "excluded", "Cannabis item is not identified as extraction source material")

    if kind == "finished_good":
        if explicit_bulk and any(token in text for token in WIP_TERMS):
            return ExtractionEligibility(True, "bulk_output", "Explicit bulk extraction output")
        return ExtractionEligibility(False, "excluded", "Finished packaged product")

    if explicit_bulk and any(token in text for token in SOURCE_TERMS + WIP_TERMS):
        return ExtractionEligibility(True, "bulk_output", "Explicit bulk extraction material")

    return ExtractionEligibility(False, "excluded", "Not extraction-eligible")


def is_extraction_inventory_eligible(**kwargs) -> bool:
    return classify_extraction_inventory(**kwargs).eligible
