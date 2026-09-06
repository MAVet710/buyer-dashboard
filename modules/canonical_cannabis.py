"""Provider-neutral cannabis domain vocabulary for DoobieLogic.

These names are semantic contracts, not a second operational data model. Domain
services keep their existing authoritative tables while integrations translate
external terminology into the canonical vocabulary at the boundary.
"""

from __future__ import annotations

import re
from enum import StrEnum


class CannabisEntityType(StrEnum):
    ORGANIZATION = "organization"
    FACILITY = "facility"
    LICENSE = "license"
    USER = "user"
    ROOM = "room"
    STRAIN = "strain"
    PLANT = "plant"
    PLANT_BATCH = "plant_batch"
    HARVEST = "harvest"
    INVENTORY_LOT = "inventory_lot"
    PRODUCT = "product"
    PRODUCTION_RUN = "production_run"
    EXTRACTION_RUN = "extraction_run"
    PACKAGE_RUN = "package_run"
    LAB_RESULT = "lab_result"
    COA_DOCUMENT = "coa_document"
    TRANSFER = "transfer"
    PURCHASE_ORDER = "purchase_order"
    SALES_ORDER = "sales_order"
    TRADE_PARTNER = "trade_partner"
    INVENTORY_AUDIT = "inventory_audit"
    TRACEABILITY_TRANSACTION = "traceability_transaction"


_ALIASES = {
    "package": CannabisEntityType.INVENTORY_LOT.value,
    "packages": CannabisEntityType.INVENTORY_LOT.value,
    "lot": CannabisEntityType.INVENTORY_LOT.value,
    "lots": CannabisEntityType.INVENTORY_LOT.value,
    "inventorypackage": CannabisEntityType.INVENTORY_LOT.value,
    "inventory_package": CannabisEntityType.INVENTORY_LOT.value,
    "item": CannabisEntityType.PRODUCT.value,
    "items": CannabisEntityType.PRODUCT.value,
    "catalog_item": CannabisEntityType.PRODUCT.value,
    "plants": CannabisEntityType.PLANT.value,
    "plantbatches": CannabisEntityType.PLANT_BATCH.value,
    "plant_batches": CannabisEntityType.PLANT_BATCH.value,
    "harvests": CannabisEntityType.HARVEST.value,
    "labtest": CannabisEntityType.LAB_RESULT.value,
    "labtests": CannabisEntityType.LAB_RESULT.value,
    "lab_test": CannabisEntityType.LAB_RESULT.value,
    "lab_tests": CannabisEntityType.LAB_RESULT.value,
    "coa": CannabisEntityType.COA_DOCUMENT.value,
    "coas": CannabisEntityType.COA_DOCUMENT.value,
    "manifest": CannabisEntityType.TRANSFER.value,
    "manifests": CannabisEntityType.TRANSFER.value,
    "transfer_manifest": CannabisEntityType.TRANSFER.value,
    "po": CannabisEntityType.PURCHASE_ORDER.value,
    "purchaseorder": CannabisEntityType.PURCHASE_ORDER.value,
    "purchase_orders": CannabisEntityType.PURCHASE_ORDER.value,
    "salesorder": CannabisEntityType.SALES_ORDER.value,
    "sales_orders": CannabisEntityType.SALES_ORDER.value,
    "vendor": CannabisEntityType.TRADE_PARTNER.value,
    "supplier": CannabisEntityType.TRADE_PARTNER.value,
    "customer": CannabisEntityType.TRADE_PARTNER.value,
}

_PROVIDER_RESOURCE_ALIASES = {
    "metrc": {
        "packages": CannabisEntityType.INVENTORY_LOT.value,
        "items": CannabisEntityType.PRODUCT.value,
        "plants": CannabisEntityType.PLANT.value,
        "plantbatches": CannabisEntityType.PLANT_BATCH.value,
        "harvests": CannabisEntityType.HARVEST.value,
        "transfers": CannabisEntityType.TRANSFER.value,
        "labtests": CannabisEntityType.LAB_RESULT.value,
    },
    "biotrack": {
        "inventory": CannabisEntityType.INVENTORY_LOT.value,
        "plants": CannabisEntityType.PLANT.value,
        "harvests": CannabisEntityType.HARVEST.value,
        "transfers": CannabisEntityType.TRANSFER.value,
    },
}


def _token(value: str) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value or "").strip())
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").casefold()
    return text


def canonical_entity_type(value: str, *, provider: str = "") -> str:
    """Translate provider/domain terminology into one stable DoobieLogic name.

    Unknown values remain normalized rather than being rejected so new provider
    resources can be ingested safely before a reviewed alias is added.
    """

    normalized = _token(value)
    provider_key = _token(provider)
    if provider_key:
        mapped = _PROVIDER_RESOURCE_ALIASES.get(provider_key, {}).get(normalized)
        if mapped:
            return mapped
    return _ALIASES.get(normalized, normalized)


def provider_resource_entity(provider: str, resource: str) -> str:
    return canonical_entity_type(resource, provider=provider)


def operational_correlation_id(domain: str, record_id: str) -> str:
    """Create a stable human-readable correlation key without leaking secrets."""

    clean_domain = _token(domain) or "operation"
    clean_record = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(record_id or "").strip()).strip("-")
    if not clean_record:
        raise ValueError("A record identifier is required for an operational correlation id.")
    return f"{clean_domain}:{clean_record}"
