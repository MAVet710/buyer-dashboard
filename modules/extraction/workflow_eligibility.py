"""Workflow-specific extraction source eligibility built on the shared inventory classifier."""

from __future__ import annotations

from modules.product_master.models import ProductMasterProfile
from modules.coman.models import Product

from .inventory_eligibility import classify_extraction_inventory
from .workflows import get_extraction_workflow


def infer_material_family(product: Product, profile: ProductMasterProfile | None = None) -> str:
    text = " ".join(
        value
        for value in (
            product.name,
            product.sku,
            profile.category if profile else "",
            profile.subcategory if profile else "",
            profile.product_format if profile else "",
        )
        if value
    ).casefold().replace("_", " ")
    if "fresh frozen" in text or "fresh-frozen" in text:
        return "fresh_frozen"
    if "biomass" in text:
        return "biomass"
    if "trim" in text or "shake" in text:
        return "trim"
    if "crude" in text:
        return "crude"
    if "rosin" in text:
        return "rosin"
    if "kief" in text or "dry sift" in text:
        return "kief"
    if "hash" in text or "full melt" in text or "bubble" in text:
        return "hash"
    if "flower" in text:
        return "cured_flower"
    return ""


def is_workflow_input_eligible(product: Product, profile: ProductMasterProfile | None, workflow_key: str) -> tuple[bool, str]:
    classification = classify_extraction_inventory(
        item_type=product.item_type,
        product_name=product.name,
        sku=product.sku,
        base_unit=product.base_unit,
        category=profile.category if profile else "",
        subcategory=profile.subcategory if profile else "",
        product_format=profile.product_format if profile else "",
    )
    if not classification.eligible:
        return False, classification.reason
    if str(product.item_type or "").casefold() == "finished_good":
        return False, "Consumer-ready finished goods cannot be used as extraction feedstock"
    family = infer_material_family(product, profile)
    workflow = get_extraction_workflow(workflow_key)
    allowed = set(workflow.input_families)
    aliases = {family}
    if family == "cured_flower":
        aliases.add("flower")
    if family == "flower":
        aliases.add("cured_flower")
    if not family or aliases.isdisjoint(allowed):
        return False, f"Material family {family or 'unknown'} is not compatible with {workflow.label}"
    return True, f"{family} is compatible with {workflow.label}"
