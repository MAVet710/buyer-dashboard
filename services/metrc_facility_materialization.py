from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction, Product, utc_now
from modules.traceability.object_links import TraceabilityObjectLink


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
    return _text(record.get("label") or _first(source, "Label", "PackageLabel", "PackageTag", "Tag"))


def _package_provider_id(record: dict[str, Any]) -> str:
    source = _source(record)
    return _text(record.get("provider_id") or _first(source, "Id", "PackageId"))


def _item_identity(record: dict[str, Any]) -> tuple[str, str, str]:
    source = _source(record)
    item = _nested(source, "Item")
    item_id = _text(_first(source, "ItemId") or _first(item, "Id", "ItemId"))
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
    return _text(_first(source, "LabTestingState", "LabTestResultStatus") or record.get("status"))


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
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _identity_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", _text(value).upper())


def _product_sku(state: str, item_id: str) -> str:
    token = re.sub(r"[^A-Z0-9]+", "-", _text(item_id).upper()).strip("-")
    return f"METRC-{state.upper()}-{token}"[:120]


def _provider_link(
    session,
    *,
    organization_id: str,
    facility_id: str,
    environment: str,
    resource: str,
    provider_id: str,
) -> TraceabilityObjectLink | None:
    return session.scalar(select(TraceabilityObjectLink).where(
        TraceabilityObjectLink.organization_id == organization_id,
        TraceabilityObjectLink.facility_id == facility_id,
        TraceabilityObjectLink.provider == "metrc",
        TraceabilityObjectLink.environment == environment,
        TraceabilityObjectLink.provider_resource == resource,
        TraceabilityObjectLink.provider_id == provider_id,
    ))


def _local_link(
    session,
    *,
    organization_id: str,
    facility_id: str,
    environment: str,
    entity_type: str,
    entity_id: str,
) -> TraceabilityObjectLink | None:
    return session.scalar(select(TraceabilityObjectLink).where(
        TraceabilityObjectLink.organization_id == organization_id,
        TraceabilityObjectLink.facility_id == facility_id,
        TraceabilityObjectLink.provider == "metrc",
        TraceabilityObjectLink.environment == environment,
        TraceabilityObjectLink.entity_type == entity_type,
        TraceabilityObjectLink.entity_id == entity_id,
    ))


def _link_scope_matches(link: TraceabilityObjectLink | None, *, state: str, license_number: str) -> bool:
    if link is None:
        return True
    return link.jurisdiction == state.upper() and link.license_number == license_number


def _ensure_verified_link(
    session,
    *,
    organization_id: str,
    facility_id: str,
    state: str,
    environment: str,
    license_number: str,
    entity_type: str,
    entity_id: str,
    provider_resource: str,
    provider_id: str,
    provider_label: str,
) -> TraceabilityObjectLink:
    local = _local_link(
        session,
        organization_id=organization_id,
        facility_id=facility_id,
        environment=environment,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    provider = _provider_link(
        session,
        organization_id=organization_id,
        facility_id=facility_id,
        environment=environment,
        resource=provider_resource,
        provider_id=provider_id,
    )
    if not _link_scope_matches(local, state=state, license_number=license_number):
        raise ValueError("This DoobieLogic object is linked under a different Metrc license scope.")
    if not _link_scope_matches(provider, state=state, license_number=license_number):
        raise ValueError("That Metrc object is linked under a different facility license scope.")
    if provider is not None and (provider.entity_type != entity_type or provider.entity_id != entity_id):
        raise ValueError("That Metrc object is already linked to a different DoobieLogic object.")
    if local is not None and (local.provider_resource != provider_resource or local.provider_id != provider_id):
        raise ValueError("This DoobieLogic object is already linked to a different Metrc identity.")

    row = local or provider
    now = utc_now()
    if row is None:
        row = TraceabilityObjectLink(
            organization_id=organization_id,
            facility_id=facility_id,
            provider="metrc",
            jurisdiction=state.upper(),
            environment=environment,
            license_number=license_number,
            entity_type=entity_type,
            entity_id=entity_id,
            provider_resource=provider_resource,
            provider_id=provider_id,
            provider_label=provider_label,
            status="verified",
            verified_at=now,
            last_seen_at=now,
        )
        session.add(row)
    else:
        row.provider_label = provider_label or row.provider_label
        row.status = "verified"
        row.mismatch_reason = ""
        row.verified_at = now
        row.last_seen_at = now
    return row


def _conflict(conflicts: list[dict[str, str]], code: str, package_id: str, message: str) -> None:
    conflicts.append({"code": code, "package_id": package_id, "message": message})


class MetrcCanonicalInventorySeeder:
    """Seed canonical inventory from a complete, verified Metrc package snapshot.

    TraceabilityObjectLink is the provider-neutral identity spine. New Products
    and Inventory Lots are linked to exact Metrc Item/Package IDs atomically with
    canonical creation. Generic Product/external inventory IDs remain available
    for POS/catalog providers and are not claimed by Metrc hydration.

    Existing balances, Product metadata, locations and statuses are never silently
    overwritten. Exact identity may be enriched when unambiguous; every collision
    or cross-license identity is returned for controlled reconciliation.
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
        state = _text(state).upper()
        environment = _text(environment).casefold()
        license_number = _text(license_number)
        conflicts: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        created_products = 0
        created_lots = 0
        created_transactions = 0
        created_product_links = 0
        created_package_links = 0
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
            by_product_id = {product.id: product for product in products}
            by_sku = {_text(product.sku).casefold(): product for product in products}
            seen_provider_packages: set[str] = set()

            for record in packages:
                if not isinstance(record, dict):
                    skipped += 1
                    continue
                label = _package_label(record)
                package_id = _package_provider_id(record)
                package_key = _identity_key(label)
                item_id, item_name, category = _item_identity(record)
                quantity = _quantity(record)
                unit = _unit(record)

                if not label or not package_id or not package_key:
                    skipped += 1
                    _conflict(conflicts, "missing_package_identity", label, "Metrc package has no exact provider id + label pair.")
                    continue
                provider_package_key = f"{package_id.casefold()}|{package_key}"
                if provider_package_key in seen_provider_packages:
                    skipped += 1
                    _conflict(conflicts, "duplicate_provider_package", label, "The same Metrc package identity appeared more than once in the import snapshot.")
                    continue
                seen_provider_packages.add(provider_package_key)
                if not item_id or not item_name:
                    skipped += 1
                    _conflict(conflicts, "missing_item_identity", label, "Metrc package has no exact Item id/name pair, so DoobieLogic will not guess Product Master identity.")
                    continue
                if quantity < -1e-12:
                    skipped += 1
                    _conflict(conflicts, "invalid_negative_quantity", label, "Metrc returned a negative active-package quantity; canonical inventory was not seeded.")
                    continue

                item_link = _provider_link(
                    session,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    environment=environment,
                    resource="items",
                    provider_id=item_id,
                )
                if not _link_scope_matches(item_link, state=state, license_number=license_number):
                    skipped += 1
                    _conflict(conflicts, "item_link_license_mismatch", label, "The exact Metrc Item is already linked under a different facility license scope.")
                    continue
                product: Product | None = None
                if item_link is not None:
                    if item_link.entity_type != "product":
                        skipped += 1
                        _conflict(conflicts, "item_link_collision", label, "This Metrc Item is linked to a non-Product DoobieLogic object.")
                        continue
                    product = by_product_id.get(item_link.entity_id)
                    if product is None:
                        skipped += 1
                        _conflict(conflicts, "orphan_item_link", label, "The exact Metrc Item link points to a Product that is not present in this organization.")
                        continue

                local_matches = by_package.get(package_key, [])
                if len(local_matches) > 1:
                    skipped += 1
                    _conflict(conflicts, "duplicate_local_package", label, "Multiple DoobieLogic lots already use this Metrc package label.")
                    continue

                package_link = _provider_link(
                    session,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    environment=environment,
                    resource="packages",
                    provider_id=package_id,
                )
                if not _link_scope_matches(package_link, state=state, license_number=license_number):
                    skipped += 1
                    _conflict(conflicts, "package_link_license_mismatch", label, "The exact Metrc Package is already linked under a different facility license scope.")
                    continue
                if package_link is not None and package_link.entity_type != "inventory_lot":
                    skipped += 1
                    _conflict(conflicts, "package_link_collision", label, "This Metrc Package is linked to a non-inventory DoobieLogic object.")
                    continue

                if len(local_matches) == 1:
                    lot = local_matches[0]
                    if package_link is not None and package_link.entity_id != lot.id:
                        skipped += 1
                        _conflict(conflicts, "package_link_collision", label, "The exact Metrc Package is already linked to a different DoobieLogic lot.")
                        continue
                    local_package_link = _local_link(
                        session,
                        organization_id=organization_id,
                        facility_id=facility_id,
                        environment=environment,
                        entity_type="inventory_lot",
                        entity_id=lot.id,
                    )
                    if not _link_scope_matches(local_package_link, state=state, license_number=license_number):
                        skipped += 1
                        _conflict(conflicts, "local_package_link_license_mismatch", label, "This DoobieLogic lot is already linked under a different Metrc license scope.")
                        continue
                    if local_package_link is not None and (
                        local_package_link.provider_resource != "packages" or local_package_link.provider_id != package_id
                    ):
                        skipped += 1
                        _conflict(conflicts, "local_package_link_differs", label, "This DoobieLogic lot is already linked to a different provider package identity.")
                        continue

                    local_product = by_product_id.get(lot.product_id)
                    if local_product is None:
                        skipped += 1
                        _conflict(conflicts, "missing_local_product", label, "Existing DoobieLogic lot has no valid Product Master record.")
                        continue
                    local_product_link = _local_link(
                        session,
                        organization_id=organization_id,
                        facility_id=facility_id,
                        environment=environment,
                        entity_type="product",
                        entity_id=local_product.id,
                    )
                    if not _link_scope_matches(local_product_link, state=state, license_number=license_number):
                        skipped += 1
                        _conflict(conflicts, "local_product_link_license_mismatch", label, "This package's local Product is already linked under a different Metrc license scope.")
                        continue
                    if local_product_link is not None and (
                        local_product_link.provider_resource != "items" or local_product_link.provider_id != item_id
                    ):
                        skipped += 1
                        _conflict(conflicts, "local_product_link_differs", label, "This package's local Product is already linked to a different Metrc Item.")
                        continue
                    if item_link is not None and item_link.entity_id != local_product.id:
                        skipped += 1
                        _conflict(conflicts, "item_link_collision", label, "The package's Metrc Item is already linked to a different DoobieLogic Product.")
                        continue

                    if local_product_link is None:
                        _ensure_verified_link(
                            session,
                            organization_id=organization_id,
                            facility_id=facility_id,
                            state=state,
                            environment=environment,
                            license_number=license_number,
                            entity_type="product",
                            entity_id=local_product.id,
                            provider_resource="items",
                            provider_id=item_id,
                            provider_label=item_name,
                        )
                        created_product_links += 1
                    if local_package_link is None:
                        _ensure_verified_link(
                            session,
                            organization_id=organization_id,
                            facility_id=facility_id,
                            state=state,
                            environment=environment,
                            license_number=license_number,
                            entity_type="inventory_lot",
                            entity_id=lot.id,
                            provider_resource="packages",
                            provider_id=package_id,
                            provider_label=label,
                        )
                        created_package_links += 1
                    existing_packages += 1
                    continue

                lot_collision = by_lot_code.get(package_key)
                if lot_collision is not None:
                    skipped += 1
                    _conflict(conflicts, "lot_code_collision", label, "A local lot already uses this package label without the same compliance-package identity.")
                    continue
                if package_link is not None:
                    skipped += 1
                    _conflict(conflicts, "orphan_or_mismatched_package_link", label, "The Metrc Package already has a provider link but no matching local package label was found.")
                    continue

                if product is None:
                    sku = _product_sku(state, item_id)
                    sku_owner = by_sku.get(sku.casefold())
                    if sku_owner is not None:
                        digest = hashlib.sha256(f"{state}:{item_id}".encode("utf-8")).hexdigest()[:8].upper()
                        sku = f"{sku[:110]}-{digest}"[:120]
                        sku_owner = by_sku.get(sku.casefold())
                    if sku_owner is not None:
                        skipped += 1
                        _conflict(conflicts, "product_sku_collision", label, "A local Product Master SKU collides with the deterministic Metrc Item SKU.")
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
                        external_product_id="",
                        active=True,
                    )
                    session.add(product)
                    session.flush()
                    by_product_id[product.id] = product
                    by_sku[sku.casefold()] = product
                    created_products += 1
                    _ensure_verified_link(
                        session,
                        organization_id=organization_id,
                        facility_id=facility_id,
                        state=state,
                        environment=environment,
                        license_number=license_number,
                        entity_type="product",
                        entity_id=product.id,
                        provider_resource="items",
                        provider_id=item_id,
                        provider_label=item_name,
                    )
                    created_product_links += 1
                elif _text(product.name) != item_name or (
                    _text(product.base_unit) and _text(product.base_unit).casefold() != unit.casefold()
                ):
                    warnings.append({
                        "code": "existing_product_metadata_differs",
                        "package_id": label,
                        "message": "Exact Metrc Item identity already exists locally, but Product Master name/unit differs; the local Product was preserved unchanged.",
                    })

                lab_state = _lab_state(record)
                metadata = {
                    "operation": "metrc_facility_hydration",
                    "source_name": "Metrc",
                    "provider": "metrc",
                    "provider_seeded": True,
                    "jurisdiction_code": state,
                    "environment": environment,
                    "license_number": license_number,
                    "metrc_package_id": package_id,
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
                    external_inventory_id="",
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
                _ensure_verified_link(
                    session,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    state=state,
                    environment=environment,
                    license_number=license_number,
                    entity_type="inventory_lot",
                    entity_id=lot.id,
                    provider_resource="packages",
                    provider_id=package_id,
                    provider_label=label,
                )
                created_package_links += 1

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
                        "metrc_package_id": package_id,
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
                "state": state,
                "environment": environment,
                "license_number": license_number,
                "source_package_count": len(packages),
                "created_products": created_products,
                "created_inventory_lots": created_lots,
                "created_inventory_transactions": created_transactions,
                "created_product_links": created_product_links,
                "created_package_links": created_package_links,
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
                changes_json=json.dumps(
                    {key: value for key, value in summary.items() if key not in {"conflicts", "warnings"}},
                    sort_keys=True,
                ),
            ))
            return summary
