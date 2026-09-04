from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction, Product, utc_now


def _source(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("source")
    return value if isinstance(value, dict) else record


def _first(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def _nested(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _package_label(record: dict[str, Any]) -> str:
    source = _source(record)
    return _text(
        record.get("label")
        or _first(source, "Label", "PackageLabel", "PackageTag", "Tag")
        or record.get("provider_id")
    )


def _package_provider_id(record: dict[str, Any]) -> str:
    source = _source(record)
    return _text(record.get("provider_id") or _first(source, "Id", "PackageId"))


def _item_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    source = _source(record)
    item = _nested(source, "Item")
    item_id = _text(
        _first(source, "ItemId")
        or _first(item, "Id", "ItemId")
    )
    item_name = _text(
        _first(source, "ItemName", "ProductName")
        or _first(item, "Name", "ItemName", "ProductName")
        or record.get("name")
    )
    category = _text(
        _first(source, "ItemCategoryName", "ProductCategoryName", "CategoryName")
        or _first(item, "ProductCategoryName", "ItemCategoryName", "CategoryName")
    )
    return item_id, item_name, category


def _unit(record: dict[str, Any]) -> str:
    source = _source(record)
    item = _nested(source, "Item")
    return _text(
        record.get("unit_of_measure")
        or _first(source, "UnitOfMeasureName", "UnitOfMeasureAbbreviation", "UnitOfMeasure")
        or _first(item, "UnitOfMeasureName", "UnitOfMeasureAbbreviation", "UnitOfMeasure")
        or "unit"
    )


def _quantity(record: dict[str, Any]) -> float:
    source = _source(record)
    value = record.get("quantity")
    if value in (None, ""):
        value = _first(source, "Quantity", "CurrentQuantity")
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _location(record: dict[str, Any]) -> str:
    source = _source(record)
    location = source.get("Location")
    if isinstance(location, dict):
        nested = _first(location, "Name", "LocationName")
        if nested:
            return _text(nested)
    return _text(_first(source, "LocationName", "CurrentLocationName", "Location") or "UNASSIGNED")


def _lab_state(record: dict[str, Any]) -> str:
    source = _source(record)
    return _text(
        _first(source, "LabTestingState", "LabTestResultStatus")
        or record.get("status")
    )


def _local_status(lab_state: str) -> str:
    token = re.sub(r"[^a-z]", "", _text(lab_state).casefold())
    if token in {"testpassed", "passed", "released", "notrequired", "notestrequired"}:
        return "available"
    return "hold"


def _received_at(record: dict[str, Any]) -> datetime | None:
    source = _source(record)
    value = _first(
        source,
        "ReceivedDateTime",
        "ReceivedDate",
        "PackagedDate",
        "PackagedDateTime",
        "CreatedDateTime",
    )
    if not value:
        return None
    text = _text(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _identity_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", _text(value).upper())


def _external_product_id(state: str, item_id: str) -> str:
    return f"metrc:{state.upper()}:{item_id}"[:120]


def _product_sku(state: str, item_id: str) -> str:
    token = re.sub(r"[^A-Z0-9]+", "-", _text(item_id).upper()).strip("-")
    return f"METRC-{state.upper()}-{token}"[:120]


class MetrcCanonicalInventorySeeder:
    """Seed canonical DoobieLogic inventory from a verified Metrc package snapshot.

    This service is intentionally conservative. It creates canonical records only
    when a Metrc package is not already represented locally and its exact Metrc
    Item identity is available. Existing local package/product state is never
    overwritten. Any collision or ambiguity is returned for reconciliation.
    """

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def seed(
        self,
        *,
        organization_id: str,
        facility_id: str,
        state: str,
        environment: str,
        license_number: str,
        actor: str,
        packages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        actor = _text(actor) or "system"
        conflicts: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        created_products = 0
        created_lots = 0
        created_transactions = 0
        existing_packages = 0
        skipped = 0

        with self.sessions.begin() as session:
            existing_lots = list(session.scalars(select(InventoryLot).where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
            )))
            by_package: dict[str, list[InventoryLot]] = {}
            by_lot_code: dict[str, InventoryLot] = {}
            for lot in existing_lots:
                if lot.compliance_package_id:
                    by_package.setdefault(_identity_key(lot.compliance_package_id), []).append(lot)
                by_lot_code[_identity_key(lot.lot_code)] = lot

            products = list(session.scalars(select(Product).where(Product.organization_id == organization_id)))
            by_external = {
                _text(product.external_product_id): product
                for product in products
                if _text(product.external_product_id)
            }
            by_sku = {_text(product.sku).casefold(): product for product in products}

            seen_provider_packages: set[str] = set()
            for record in packages:
                if not isinstance(record, dict):
                    skipped += 1
                    continue
                label = _package_label(record)
                package_key = _identity_key(label)
                if not label or not package_key:
                    skipped += 1
                    conflicts.append({"code": "missing_package_identity", "package_id": label, "message": "Metrc package has no usable label or id."})
                    continue
                if package_key in seen_provider_packages:
                    skipped += 1
                    conflicts.append({"code": "duplicate_provider_package", "package_id": label, "message": "The same Metrc package identity appeared more than once in the import snapshot."})
                    continue
                seen_provider_packages.add(package_key)

                local_matches = by_package.get(package_key, [])
                if len(local_matches) > 1:
                    skipped += 1
                    conflicts.append({"code": "duplicate_local_package", "package_id": label, "message": "Multiple DoobieLogic lots already use this Metrc package identity."})
                    continue
                if len(local_matches) == 1:
                    existing_packages += 1
                    continue
                lot_collision = by_lot_code.get(package_key)
                if lot_collision is not None:
                    skipped += 1
                    conflicts.append({"code": "lot_code_collision", "package_id": label, "message": "A local lot already uses this package label without the same compliance-package identity."})
                    continue

                item_id, item_name, category = _item_identity(record)
                if not item_id or not item_name:
                    skipped += 1
                    conflicts.append({
                        "code": "missing_item_identity",
                        "package_id": label,
                        "message": "Metrc package has no exact Item id/name pair, so DoobieLogic will not guess Product Master identity.",
                    })
                    continue
                quantity = _quantity(record)
                if quantity < -1e-12:
                    skipped += 1
                    conflicts.append({
                        "code": "invalid_negative_quantity",
                        "package_id": label,
                        "message": "Metrc returned a negative active-package quantity; canonical inventory was not seeded.",
                    })
                    continue

                unit = _unit(record)
                external_id = _external_product_id(state, item_id)
                product = by_external.get(external_id)
                if product is None:
                    sku = _product_sku(state, item_id)
                    sku_owner = by_sku.get(sku.casefold())
                    if sku_owner is not None and _text(sku_owner.external_product_id) != external_id:
                        digest = hashlib.sha256(external_id.encode("utf-8")).hexdigest()[:8].upper()
                        sku = f"{sku[:110]}-{digest}"[:120]
                        sku_owner = by_sku.get(sku.casefold())
                    if sku_owner is not None and _text(sku_owner.external_product_id) != external_id:
                        skipped += 1
                        conflicts.append({"code": "product_sku_collision", "package_id": label, "message": "A local Product Master SKU collides with the deterministic Metrc Item SKU."})
                        continue
                    product = Product(
                        organization_id=organization_id,
                        sku=sku,
                        name=item_name,
                        item_type="cannabis",
                        base_unit=unit or "unit",
                        unit_cost=0.0,
                        retail_price=0.0,
                        upc="",
                        external_product_id=external_id,
                        active=True,
                    )
                    session.add(product)
                    session.flush()
                    by_external[external_id] = product
                    by_sku[sku.casefold()] = product
                    created_products += 1
                elif _text(product.name) != item_name or (_text(product.base_unit) and _text(product.base_unit).casefold() != unit.casefold()):
                    warnings.append({
                        "code": "existing_product_metadata_differs",
                        "package_id": label,
                        "message": "Exact Metrc Item identity already exists locally, but Product Master name/unit differs; the local Product was preserved unchanged.",
                    })

                lab_state = _lab_state(record)
                provider_id = _package_provider_id(record)
                metadata = {
                    "operation": "metrc_facility_hydration",
                    "source_name": "Metrc",
                    "provider": "metrc",
                    "provider_seeded": True,
                    "jurisdiction_code": state.upper(),
                    "environment": environment,
                    "license_number": license_number,
                    "metrc_package_id": provider_id,
                    "metrc_item_id": item_id,
                    "metrc_item_category": category,
                    "lab_testing_state": lab_state,
                    "hydrated_at": utc_now().isoformat(),
                }
                lot = InventoryLot(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    product_id=product.id,
                    lot_code=label,
                    compliance_package_id=label,
                    external_inventory_id=f"metrc:{state.upper()}:{provider_id or label}"[:120],
                    barcode_value=label,
                    location_code=_location(record) or "UNASSIGNED",
                    status=_local_status(lab_state),
                    received_at=_received_at(record),
                    expiration_at=None,
                    notes=json.dumps(metadata, sort_keys=True),
                )
                session.add(lot)
                session.flush()
                by_package[package_key] = [lot]
                by_lot_code[package_key] = lot
                created_lots += 1

                if quantity > 1e-12:
                    session.add(InventoryTransaction(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        lot_id=lot.id,
                        transaction_type="metrc_initial_import",
                        quantity_delta=quantity,
                        unit=unit or "unit",
                        production_order_id=None,
                        commercial_order_id=None,
                        commercial_order_line_id=None,
                        reason="Initial inventory balance seeded from verified Metrc facility state",
                        reference=label,
                        actor=actor,
                    ))
                    created_transactions += 1

                session.add(AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="inventory_lot",
                    entity_id=lot.id,
                    action="metrc_inventory_seeded",
                    actor=actor,
                    changes_json=json.dumps({
                        "package_id": label,
                        "metrc_package_id": provider_id,
                        "metrc_item_id": item_id,
                        "quantity": quantity,
                        "unit": unit,
                        "location": lot.location_code,
                        "lab_testing_state": lab_state,
                        "environment": environment,
                        "license_number": license_number,
                    }, sort_keys=True),
                ))

            summary = {
                "provider": "metrc",
                "state": state.upper(),
                "environment": environment,
                "license_number": license_number,
                "source_package_count": len(packages),
                "created_products": created_products,
                "created_inventory_lots": created_lots,
                "created_inventory_transactions": created_transactions,
                "existing_package_count": existing_packages,
                "skipped_count": skipped,
                "conflict_count": len(conflicts),
                "warning_count": len(warnings),
                "conflicts": conflicts[:100],
                "warnings": warnings[:100],
                "overwrite_existing": False,
            }
            session.add(AuditEvent(
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="metrc_facility_hydration",
                entity_id=facility_id,
                action="metrc_initial_inventory_hydration_completed",
                actor=actor,
                changes_json=json.dumps({key: value for key, value in summary.items() if key not in {"conflicts", "warnings"}}, sort_keys=True),
            ))
            return summary
