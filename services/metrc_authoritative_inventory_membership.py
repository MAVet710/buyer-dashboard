from __future__ import annotations

import json
from typing import Any, Mapping

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import AuditEvent, InventoryLot, InventoryTransaction, Product
from modules.traceability.object_links import TraceabilityObjectLink


_EPSILON = 1e-9


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source(record: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = record.get("source")
    return nested if isinstance(nested, Mapping) else record


def _provider_id(record: Mapping[str, Any]) -> str:
    if _text(record.get("provider_id")):
        return _text(record.get("provider_id"))
    source = _source(record)
    for key in ("Id", "ID", "id", "PackageId"):
        if _text(source.get(key)):
            return _text(source.get(key))
    return ""


def _balance(session: Session, lot_id: str) -> float:
    return float(
        session.scalar(
            select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                InventoryTransaction.lot_id == lot_id
            )
        )
        or 0.0
    )


class MetrcAuthoritativeInventoryMembershipReconciler:
    """Close canonical package balances missing from a complete Metrc active snapshot.

    Absence is meaningful only after a complete `packages/active` snapshot. Incremental
    LastModified windows must never call this service because omission in a delta does
    not mean a package is inactive. The natural full-bootstrap layer owns that gate.
    """

    def __init__(self, engine: Engine):
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def reconcile_absent(
        self,
        *,
        organization_id: str,
        facility_id: str,
        state: str,
        environment: str,
        license_number: str,
        actor: str,
        current_packages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        state = _text(state).upper()
        environment = _text(environment).casefold()
        license_number = _text(license_number)
        actor = _text(actor) or "system"
        current_ids = {
            provider_id
            for row in current_packages
            if isinstance(row, Mapping)
            for provider_id in (_provider_id(row),)
            if provider_id
        }

        closed_balances = 0
        status_updates = 0
        unchanged = 0
        conflicts: list[dict[str, str]] = []
        affected: list[dict[str, Any]] = []

        with self.sessions.begin() as session:
            links = list(
                session.scalars(
                    select(TraceabilityObjectLink).where(
                        TraceabilityObjectLink.organization_id == organization_id,
                        TraceabilityObjectLink.facility_id == facility_id,
                        TraceabilityObjectLink.provider == "metrc",
                        TraceabilityObjectLink.environment == environment,
                        TraceabilityObjectLink.jurisdiction == state,
                        TraceabilityObjectLink.license_number == license_number,
                        TraceabilityObjectLink.provider_resource == "packages",
                        TraceabilityObjectLink.entity_type == "inventory_lot",
                    )
                )
            )

            absent_links = [row for row in links if row.provider_id not in current_ids]
            for link in absent_links:
                lot = session.scalar(
                    select(InventoryLot)
                    .where(InventoryLot.id == link.entity_id)
                    .with_for_update()
                )
                if lot is None or lot.organization_id != organization_id or lot.facility_id != facility_id:
                    link.status = "reconciliation_required"
                    link.mismatch_reason = "Metrc Package identity points to a missing or out-of-scope inventory lot."
                    conflicts.append({
                        "code": "orphan_absent_package_link",
                        "provider_id": link.provider_id,
                        "message": link.mismatch_reason,
                    })
                    continue

                product = session.get(Product, lot.product_id)
                unit = _text(product.base_unit) if product is not None and product.organization_id == organization_id else ""
                current_balance = _balance(session, lot.id)
                row_changes: dict[str, Any] = {}

                if abs(current_balance) > _EPSILON:
                    if not unit:
                        link.status = "reconciliation_required"
                        link.mismatch_reason = "Cannot close absent Metrc package balance because the linked Product has no unit."
                        conflicts.append({
                            "code": "absent_package_missing_unit",
                            "provider_id": link.provider_id,
                            "message": link.mismatch_reason,
                        })
                    else:
                        session.add(
                            InventoryTransaction(
                                organization_id=organization_id,
                                facility_id=facility_id,
                                lot_id=lot.id,
                                transaction_type="metrc_authoritative_absence_reconciliation",
                                quantity_delta=-current_balance,
                                unit=unit,
                                production_order_id=None,
                                commercial_order_id=None,
                                commercial_order_line_id=None,
                                reason="Package absent from complete authoritative Metrc active-package snapshot",
                                reference=lot.compliance_package_id or link.provider_label or link.provider_id,
                                actor=actor,
                            )
                        )
                        closed_balances += 1
                        row_changes["quantity"] = {
                            "before": current_balance,
                            "after": 0.0,
                            "delta": -current_balance,
                            "unit": unit,
                        }

                if lot.status != "inactive":
                    previous = lot.status
                    lot.status = "inactive"
                    status_updates += 1
                    row_changes["status"] = {"before": previous, "after": "inactive"}

                if link.status != "reconciliation_required":
                    link.status = "verified"
                    link.mismatch_reason = ""

                if row_changes:
                    affected.append({
                        "provider_id": link.provider_id,
                        "package_label": lot.compliance_package_id or link.provider_label,
                        "changes": row_changes,
                    })
                    session.add(
                        AuditEvent(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            entity_type="inventory_lot",
                            entity_id=lot.id,
                            action="metrc_authoritative_package_became_inactive",
                            actor=actor,
                            changes_json=json.dumps(
                                {
                                    "provider": "metrc",
                                    "environment": environment,
                                    "jurisdiction_code": state,
                                    "license_number": license_number,
                                    "metrc_package_id": link.provider_id,
                                    "complete_active_snapshot": True,
                                    "changes": row_changes,
                                },
                                sort_keys=True,
                            ),
                        )
                    )
                else:
                    unchanged += 1

            return {
                "provider": "metrc",
                "authoritative_provider": "metrc",
                "complete_active_snapshot": True,
                "current_provider_package_count": len(current_ids),
                "linked_package_count": len(links),
                "absent_linked_package_count": len(absent_links),
                "closed_balance_count": closed_balances,
                "status_update_count": status_updates,
                "unchanged_absent_count": unchanged,
                "conflict_count": len(conflicts),
                "conflicts": conflicts[:100],
                "affected": affected[:100],
                "absence_semantics": "inactive_only_after_complete_active_snapshot",
                "incremental_absence_inference": False,
                "local_enrichment_preserved": True,
            }
