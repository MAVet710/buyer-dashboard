from __future__ import annotations

import json
import re
from typing import Any, Mapping

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction, Product, utc_now
from modules.traceability.object_links import TraceabilityObjectLink


_EPSILON = 1e-9


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source(record: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = record.get("source")
    return nested if isinstance(nested, Mapping) else record


def _nested(source: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = source.get(key)
    return value if isinstance(value, Mapping) else {}


def _first(source: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, "") and _text(value):
            return value
    return None


def _package_id(record: Mapping[str, Any]) -> str:
    source = _source(record)
    return _text(record.get("provider_id") or _first(source, "Id", "ID", "id", "PackageId"))


def _package_label(record: Mapping[str, Any]) -> str:
    source = _source(record)
    return _text(record.get("label") or _first(source, "Label", "PackageLabel", "PackageTag", "Tag"))


def _item_id(record: Mapping[str, Any]) -> str:
    source = _source(record)
    item = _nested(source, "Item")
    return _text(_first(source, "ItemId") or _first(item, "Id", "ID", "id", "ItemId"))


def _provider_quantity(record: Mapping[str, Any]) -> tuple[bool, float]:
    source = _source(record)
    value = record.get("quantity")
    if value in (None, ""):
        value = _first(source, "Quantity", "CurrentQuantity")
    if value in (None, ""):
        return False, 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False, 0.0
    if parsed < -_EPSILON:
        return False, parsed
    return True, max(0.0, parsed)


def _provider_unit(record: Mapping[str, Any]) -> str:
    source = _source(record)
    item = _nested(source, "Item")
    return _text(
        record.get("unit_of_measure")
        or _first(source, "UnitOfMeasureName", "UnitOfMeasureAbbreviation", "UnitOfMeasure")
        or _first(item, "UnitOfMeasureName", "UnitOfMeasureAbbreviation", "UnitOfMeasure")
    )


def _unit_key(value: Any) -> str:
    token = re.sub(r"[^a-z0-9]+", "", _text(value).casefold())
    aliases = {
        "g": "grams",
        "gram": "grams",
        "grams": "grams",
        "oz": "ounces",
        "ounce": "ounces",
        "ounces": "ounces",
        "lb": "pounds",
        "lbs": "pounds",
        "pound": "pounds",
        "pounds": "pounds",
        "ea": "each",
        "each": "each",
        "unit": "each",
        "units": "each",
    }
    return aliases.get(token, token)


def _provider_location(record: Mapping[str, Any]) -> tuple[bool, str]:
    source = _source(record)
    location = source.get("Location")
    if isinstance(location, Mapping):
        value = _first(location, "Name", "LocationName")
        if value not in (None, ""):
            return True, _text(value)
    value = _first(source, "LocationName", "CurrentLocationName")
    if value not in (None, ""):
        return True, _text(value)
    return False, ""


def _provider_lab_state(record: Mapping[str, Any]) -> tuple[bool, str]:
    source = _source(record)
    value = _first(source, "LabTestingState", "LabTestResultStatus")
    if value in (None, ""):
        return False, ""
    return True, _text(value)


def _local_status(lab_state: str) -> str:
    token = re.sub(r"[^a-z]", "", _text(lab_state).casefold())
    if token in {"testpassed", "passed", "released", "notrequired", "notestrequired"}:
        return "available"
    return "hold"


def _lot_balance(session: Session, lot_id: str) -> float:
    return float(
        session.scalar(
            select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                InventoryTransaction.lot_id == lot_id
            )
        )
        or 0.0
    )


def _provider_link(
    session: Session,
    *,
    organization_id: str,
    facility_id: str,
    environment: str,
    resource: str,
    provider_id: str,
) -> TraceabilityObjectLink | None:
    return session.scalar(
        select(TraceabilityObjectLink).where(
            TraceabilityObjectLink.organization_id == organization_id,
            TraceabilityObjectLink.facility_id == facility_id,
            TraceabilityObjectLink.provider == "metrc",
            TraceabilityObjectLink.environment == environment,
            TraceabilityObjectLink.provider_resource == resource,
            TraceabilityObjectLink.provider_id == provider_id,
        )
    )


def _conflict(conflicts: list[dict[str, str]], code: str, provider_id: str, message: str) -> None:
    conflicts.append({"code": code, "provider_id": provider_id, "message": message})


class MetrcAuthoritativeInventoryReconciler:
    """Project verified Metrc package state into the canonical inventory ledger.

    Metrc is authoritative for regulated package identity, quantity, location and
    testing state. DoobieLogic preserves its append-only inventory history by writing
    only the delta required to make the current ledger balance equal the freshly
    synchronized Metrc quantity. Product cost, pricing, descriptions, notes and other
    local ERP enrichment are never overwritten here.

    Reconciliation is fail-closed: mutable names and labels are never used to bind an
    object. Every mutation requires the exact Metrc Package link, exact license scope,
    exact linked Metrc Item/Product identity and compatible units.
    """

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def reconcile(
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
        state = _text(state).upper()
        environment = _text(environment).casefold()
        license_number = _text(license_number)
        actor = _text(actor) or "system"

        matched = 0
        quantity_reconciliations = 0
        location_updates = 0
        status_updates = 0
        unchanged = 0
        skipped = 0
        conflicts: list[dict[str, str]] = []
        reconciled: list[dict[str, Any]] = []

        with self.sessions.begin() as session:
            for record in packages:
                if not isinstance(record, dict):
                    skipped += 1
                    continue

                provider_id = _package_id(record)
                label = _package_label(record)
                item_id = _item_id(record)
                if not provider_id:
                    skipped += 1
                    _conflict(conflicts, "missing_package_provider_id", "", "Metrc package has no exact provider ID; regulated state was not guessed.")
                    continue

                package_link = _provider_link(
                    session,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    environment=environment,
                    resource="packages",
                    provider_id=provider_id,
                )
                if package_link is None:
                    skipped += 1
                    _conflict(conflicts, "unlinked_package", provider_id, "No exact Metrc Package identity link exists; DoobieLogic did not match by label or name.")
                    continue
                if (
                    package_link.jurisdiction != state
                    or package_link.license_number != license_number
                    or package_link.entity_type != "inventory_lot"
                ):
                    skipped += 1
                    package_link.status = "reconciliation_required"
                    package_link.mismatch_reason = "Package identity scope or local entity type does not match this Metrc facility/license."
                    _conflict(conflicts, "package_identity_scope_mismatch", provider_id, package_link.mismatch_reason)
                    continue

                lot = session.get(InventoryLot, package_link.entity_id)
                if lot is None or lot.organization_id != organization_id or lot.facility_id != facility_id:
                    skipped += 1
                    package_link.status = "reconciliation_required"
                    package_link.mismatch_reason = "Exact Metrc Package link points to a missing or out-of-scope inventory lot."
                    _conflict(conflicts, "orphan_package_link", provider_id, package_link.mismatch_reason)
                    continue

                if label and lot.compliance_package_id and _text(lot.compliance_package_id) != label:
                    skipped += 1
                    package_link.status = "reconciliation_required"
                    package_link.mismatch_reason = "Metrc package label differs from the linked local compliance package identity."
                    _conflict(conflicts, "package_label_mismatch", provider_id, package_link.mismatch_reason)
                    continue
                if not lot.compliance_package_id and label:
                    lot.compliance_package_id = label
                    lot.barcode_value = lot.barcode_value or label

                product = session.get(Product, lot.product_id)
                if product is None or product.organization_id != organization_id:
                    skipped += 1
                    package_link.status = "reconciliation_required"
                    package_link.mismatch_reason = "Linked inventory lot has no in-scope Product Master record."
                    _conflict(conflicts, "missing_linked_product", provider_id, package_link.mismatch_reason)
                    continue

                item_link = _provider_link(
                    session,
                    organization_id=organization_id,
                    facility_id=facility_id,
                    environment=environment,
                    resource="items",
                    provider_id=item_id,
                ) if item_id else None
                if (
                    not item_id
                    or item_link is None
                    or item_link.jurisdiction != state
                    or item_link.license_number != license_number
                    or item_link.entity_type != "product"
                    or item_link.entity_id != product.id
                ):
                    skipped += 1
                    package_link.status = "reconciliation_required"
                    package_link.mismatch_reason = "Metrc Package Item identity does not exactly match the linked local Product."
                    _conflict(conflicts, "package_item_identity_mismatch", provider_id, package_link.mismatch_reason)
                    continue

                matched += 1
                now = utc_now()
                old_balance = _lot_balance(session, lot.id)
                old_location = _text(lot.location_code)
                old_status = _text(lot.status)
                row_changes: dict[str, Any] = {}

                quantity_ok, provider_quantity = _provider_quantity(record)
                provider_unit = _provider_unit(record)
                local_unit = _text(product.base_unit)
                if not quantity_ok:
                    _conflict(conflicts, "invalid_or_missing_package_quantity", provider_id, "Metrc did not provide a valid non-negative package quantity; local balance was not changed.")
                elif not provider_unit:
                    _conflict(conflicts, "missing_package_unit", provider_id, "Metrc did not provide a package unit; quantity reconciliation was not attempted.")
                elif not local_unit or _unit_key(local_unit) != _unit_key(provider_unit):
                    _conflict(
                        conflicts,
                        "package_unit_mismatch",
                        provider_id,
                        f"Metrc quantity unit {provider_unit!r} does not match local Product unit {local_unit!r}; no conversion was guessed.",
                    )
                else:
                    correction = provider_quantity - old_balance
                    if abs(correction) > _EPSILON:
                        session.add(
                            InventoryTransaction(
                                organization_id=organization_id,
                                facility_id=facility_id,
                                lot_id=lot.id,
                                transaction_type="metrc_authoritative_reconciliation",
                                quantity_delta=correction,
                                unit=provider_unit,
                                production_order_id=None,
                                commercial_order_id=None,
                                commercial_order_line_id=None,
                                reason="Reconcile canonical inventory to authoritative Metrc package quantity",
                                reference=label or provider_id,
                                actor=actor,
                            )
                        )
                        quantity_reconciliations += 1
                        row_changes["quantity"] = {
                            "before": old_balance,
                            "after": provider_quantity,
                            "delta": correction,
                            "unit": provider_unit,
                        }

                has_location, provider_location = _provider_location(record)
                if has_location and provider_location and old_location != provider_location:
                    lot.location_code = provider_location
                    location_updates += 1
                    row_changes["location"] = {"before": old_location, "after": provider_location}

                has_lab_state, provider_lab_state = _provider_lab_state(record)
                if has_lab_state:
                    provider_status = _local_status(provider_lab_state)
                    if old_status != provider_status:
                        lot.status = provider_status
                        status_updates += 1
                        row_changes["status"] = {
                            "before": old_status,
                            "after": provider_status,
                            "metrc_lab_testing_state": provider_lab_state,
                        }

                package_link.provider_label = label or package_link.provider_label
                package_link.status = "verified"
                package_link.mismatch_reason = ""
                package_link.verified_at = now
                package_link.last_seen_at = now
                item_link.status = "verified"
                item_link.mismatch_reason = ""
                item_link.verified_at = now
                item_link.last_seen_at = now

                if row_changes:
                    reconciled.append({
                        "provider_id": provider_id,
                        "package_label": label,
                        "changes": row_changes,
                    })
                    session.add(
                        AuditEvent(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            entity_type="inventory_lot",
                            entity_id=lot.id,
                            action="metrc_authoritative_inventory_reconciled",
                            actor=actor,
                            changes_json=json.dumps(
                                {
                                    "provider": "metrc",
                                    "environment": environment,
                                    "jurisdiction_code": state,
                                    "license_number": license_number,
                                    "metrc_package_id": provider_id,
                                    "package_label": label,
                                    "changes": row_changes,
                                    "local_enrichment_preserved": True,
                                },
                                sort_keys=True,
                            ),
                        )
                    )
                else:
                    unchanged += 1

            summary = {
                "provider": "metrc",
                "authoritative_provider": "metrc",
                "environment": environment,
                "jurisdiction_code": state,
                "license_number": license_number,
                "source_package_count": len(packages),
                "matched_package_count": matched,
                "quantity_reconciliations": quantity_reconciliations,
                "location_updates": location_updates,
                "status_updates": status_updates,
                "unchanged_package_count": unchanged,
                "skipped_count": skipped,
                "conflict_count": len(conflicts),
                "conflicts": conflicts[:100],
                "reconciled": reconciled[:100],
                "regulated_fields": ["package_identity", "quantity", "location", "testing_state"],
                "local_enrichment_preserved": True,
                "ledger_strategy": "append_only_delta_to_provider_truth",
                "identity_strategy": "exact_traceability_object_link",
            }
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="metrc_authoritative_inventory",
                    entity_id=facility_id,
                    action="metrc_authoritative_inventory_reconciliation_completed",
                    actor=actor,
                    changes_json=json.dumps(
                        {key: value for key, value in summary.items() if key not in {"conflicts", "reconciled"}},
                        sort_keys=True,
                    ),
                )
            )
            return summary
