"""Atomic preview-before-mutation guardrails for high-impact Production Run 360 actions."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import (
    AuditEvent,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    ProductionOrder,
)
from modules.production_erp.models import (
    ProductionCostEvent,
    ProductionQAEvent,
    ProductionRunEvent,
    ProductionRunOutput,
)
from modules.production_erp.service import ProductionERPService


MUTATION_ACTIONS = {
    "reserve_materials",
    "run_event",
    "record_output_actual",
    "qa_decision",
    "cost_event",
}
RISKY_RUN_EVENTS = {"hold", "release", "completed", "waste", "rework"}
QA_EVENT_TYPES = {"hold", "sample", "pass", "fail", "release", "retest", "deviation", "remediation"}
QA_RESULTS = {"pending", "passed", "failed", "not_applicable"}
COST_CATEGORIES = {"material", "labor", "packaging", "machine", "overhead", "waste", "other"}


class ProductionMutationService:
    """Preview exact consequences and commit them against the same locked operational state."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.erp = ProductionERPService(engine)

    def preview(
        self,
        *,
        organization_id: str,
        facility_id: str,
        order_id: str,
        action_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with Session(self.engine) as session:
            order = self._require_order(session, organization_id, facility_id, order_id)
            return self._build_preview(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                order=order,
                action_type=action_type,
                payload=payload,
                lock=False,
            )

    def commit(
        self,
        *,
        organization_id: str,
        facility_id: str,
        order_id: str,
        action_type: str,
        payload: dict[str, Any],
        preview_key: str,
        actor: str,
    ) -> dict[str, Any]:
        if not str(preview_key or "").strip():
            raise ValueError("Review the exact change preview before applying this action.")
        with Session(self.engine) as session:
            order = session.scalar(
                select(ProductionOrder)
                .where(
                    ProductionOrder.id == order_id,
                    ProductionOrder.organization_id == organization_id,
                    ProductionOrder.facility_id == facility_id,
                )
                .with_for_update()
            )
            if order is None:
                raise ValueError("Production order was not found in the active facility.")
            preview = self._build_preview(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                order=order,
                action_type=action_type,
                payload=payload,
                lock=True,
            )
            if preview_key != preview["preview_key"]:
                raise ValueError(
                    "This change preview is stale. Review the current consequences again before applying it."
                )
            if preview["blocker_count"]:
                raise ValueError("This change has blockers that must be resolved before it can be applied.")

            result = self._apply(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                order=order,
                action_type=action_type,
                payload=payload,
                preview=preview,
                actor=actor,
            )
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="production_order",
                    entity_id=order.id,
                    action=f"run360_{action_type}",
                    actor=actor,
                    changes_json=json.dumps(
                        {
                            "preview_key": preview["preview_key"],
                            "summary": preview["summary"],
                            "consequences": preview["consequences"],
                            "warnings": preview["warnings"],
                            "result": result,
                        },
                        default=str,
                        sort_keys=True,
                    ),
                )
            )
            session.commit()
            return {
                "status": "applied",
                "action_type": action_type,
                "summary": preview["summary"],
                "result": result,
            }

    @staticmethod
    def _require_order(session: Session, organization_id: str, facility_id: str, order_id: str) -> ProductionOrder:
        order = session.get(ProductionOrder, order_id)
        if not order or order.organization_id != organization_id or order.facility_id != facility_id:
            raise ValueError("Production order was not found in the active facility.")
        return order

    def _build_preview(
        self,
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        action_type: str,
        payload: dict[str, Any],
        lock: bool,
    ) -> dict[str, Any]:
        action_type = str(action_type or "").strip()
        if action_type not in MUTATION_ACTIONS:
            raise ValueError("This Production Run 360 action does not support consequence preview.")
        payload = dict(payload or {})
        if action_type == "reserve_materials":
            preview = self._preview_reservations(
                session, organization_id, facility_id, order, lock=lock
            )
        elif action_type == "run_event":
            preview = self._preview_run_event(session, order, payload)
        elif action_type == "record_output_actual":
            preview = self._preview_output_actual(session, facility_id, order, payload, lock=lock)
        elif action_type == "qa_decision":
            preview = self._preview_qa(session, order, payload, lock=lock)
        else:
            preview = self._preview_cost(session, order, payload)

        key_material = {
            "action_type": action_type,
            "order_id": order.id,
            "payload": self._normalized(payload),
            "state": preview.pop("_state"),
        }
        preview["action_type"] = action_type
        preview["preview_key"] = self._fingerprint(key_material)
        preview["blocker_count"] = sum(
            1 for row in preview.get("warnings", []) if row.get("severity") == "blocker"
        )
        return preview

    def _preview_reservations(
        self,
        session: Session,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        *,
        lock: bool,
    ) -> dict[str, Any]:
        product = self.erp._resolve_output_product(session, organization_id, order)
        if not product:
            raise ValueError("Link this production order to a canonical Product Master item first.")
        bom = self.erp._active_bom(session, organization_id, product.id)
        if not bom:
            raise ValueError("No active BOM exists for this product.")
        requirements = self.erp._bom_requirements(session, bom, order.requested_units)
        reservations = list(
            session.scalars(
                select(MaterialReservation).where(
                    MaterialReservation.production_order_id == order.id,
                    MaterialReservation.status == "reserved",
                )
            )
        )
        lot_ids = [row.lot_id for row in reservations]
        reserved_lots = {
            row.id: row
            for row in session.scalars(select(InventoryLot).where(InventoryLot.id.in_(lot_ids))).all()
        } if lot_ids else {}
        existing_by_product: dict[str, float] = {}
        for row in reservations:
            lot = reserved_lots.get(row.lot_id)
            if lot:
                existing_by_product[lot.product_id] = existing_by_product.get(lot.product_id, 0.0) + float(row.quantity or 0)

        allocations: list[dict[str, Any]] = []
        shortages: list[dict[str, Any]] = []
        lot_state: list[dict[str, Any]] = []
        for requirement in requirements:
            needed = max(
                0.0,
                float(requirement["quantity"])
                - existing_by_product.get(str(requirement["product_id"]), 0.0),
            )
            query = (
                select(InventoryLot)
                .where(
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                    InventoryLot.product_id == requirement["product_id"],
                    InventoryLot.status.in_(("available", "released")),
                )
                .order_by(InventoryLot.received_at.asc().nullsfirst(), InventoryLot.created_at.asc())
            )
            if lock:
                query = query.with_for_update()
            lots = list(session.scalars(query))
            for lot in lots:
                balance = float(
                    session.scalar(
                        select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                            InventoryTransaction.lot_id == lot.id
                        )
                    )
                    or 0.0
                )
                total_reserved = float(
                    session.scalar(
                        select(func.coalesce(func.sum(MaterialReservation.quantity), 0.0)).where(
                            MaterialReservation.lot_id == lot.id,
                            MaterialReservation.status == "reserved",
                        )
                    )
                    or 0.0
                )
                available = max(0.0, balance - total_reserved)
                lot_state.append(
                    {
                        "lot_id": lot.id,
                        "lot_code": lot.lot_code,
                        "product_id": lot.product_id,
                        "status": lot.status,
                        "balance": balance,
                        "reserved": total_reserved,
                        "available": available,
                        "updated_at": getattr(lot, "updated_at", None),
                    }
                )
                if needed <= 1e-9 or available <= 1e-9:
                    continue
                take = min(needed, available)
                allocations.append(
                    {
                        "product_id": requirement["product_id"],
                        "product": requirement["product_name"],
                        "lot_id": lot.id,
                        "lot_code": lot.lot_code,
                        "quantity": round(take, 6),
                        "unit": requirement["unit"],
                        "available_before": round(available, 6),
                    }
                )
                needed -= take
            if needed > 1e-9:
                shortages.append(
                    {
                        "product": requirement["product_name"],
                        "quantity": round(needed, 6),
                        "unit": requirement["unit"],
                    }
                )

        consequences = [
            {
                "label": f"Reserve {row['product']}",
                "before": f"{row['available_before']} {row['unit']} available in {row['lot_code']}",
                "after": f"Reserve {row['quantity']} {row['unit']} from lot {row['lot_code']}",
            }
            for row in allocations
        ]
        if not allocations and not shortages:
            consequences.append(
                {
                    "label": "Material readiness",
                    "before": "BOM requirements already covered",
                    "after": "No additional reservation will be created",
                }
            )
        warnings = [
            {
                "severity": "warning",
                "message": f"Buyer Review: {row['product']} is short {row['quantity']} {row['unit']}. No purchase order will be created automatically.",
            }
            for row in shortages
        ]
        return {
            "title": "Reserve BOM materials",
            "summary": f"{len(allocations)} lot allocation(s) will be added; {len(shortages)} shortage(s) remain for Buyer Review.",
            "consequences": consequences,
            "warnings": warnings,
            "details": {"allocations": allocations, "shortages": shortages},
            "_state": {
                "order_status": order.status,
                "order_updated_at": getattr(order, "updated_at", None),
                "bom_id": bom.id,
                "bom_version": bom.version,
                "bom_updated_at": getattr(bom, "updated_at", None),
                "requirements": requirements,
                "reservations": [
                    {
                        "id": row.id,
                        "lot_id": row.lot_id,
                        "quantity": row.quantity,
                        "unit": row.unit,
                        "status": row.status,
                        "updated_at": getattr(row, "updated_at", None),
                    }
                    for row in reservations
                ],
                "lots": lot_state,
            },
        }

    def _preview_run_event(self, session: Session, order: ProductionOrder, payload: dict[str, Any]) -> dict[str, Any]:
        event_type = str(payload.get("event_type") or "").strip()
        if event_type not in RISKY_RUN_EVENTS:
            raise ValueError("Routine measurements and notes do not require a consequence preview.")
        quantity = self._optional_nonnegative(payload.get("quantity"), "Quantity")
        waste_quantity = self._optional_nonnegative(payload.get("waste_quantity"), "Waste quantity")
        labor_hours = self._optional_nonnegative(payload.get("labor_hours"), "Labor hours")
        machine_hours = self._optional_nonnegative(payload.get("machine_hours"), "Machine hours")
        if event_type == "waste" and not waste_quantity:
            raise ValueError("Enter the measured waste quantity before previewing a waste event.")

        status_after = order.status
        if event_type == "hold":
            status_after = "on_hold"
        elif event_type == "release" and order.status == "on_hold":
            status_after = "in_progress"
        elif event_type == "completed":
            status_after = "complete"

        latest = session.scalar(
            select(ProductionRunEvent)
            .where(ProductionRunEvent.production_order_id == order.id)
            .order_by(ProductionRunEvent.occurred_at.desc())
            .limit(1)
        )
        qa_events = list(
            session.scalars(select(ProductionQAEvent).where(ProductionQAEvent.production_order_id == order.id))
        )
        qa_passed = any(row.result == "passed" for row in qa_events)
        standard = self._standard_for_order(session, order)
        qa_required = bool(getattr(standard, "qa_required", False))
        actual_output = float(
            session.scalar(
                select(func.coalesce(func.sum(ProductionRunOutput.actual_quantity), 0.0)).where(
                    ProductionRunOutput.production_order_id == order.id
                )
            )
            or 0.0
        )
        warnings: list[dict[str, str]] = []
        if event_type == "completed" and qa_required and not qa_passed:
            warnings.append(
                {
                    "severity": "warning",
                    "message": "The run can be completed, but finished output remains blocked until the required QA release is recorded.",
                }
            )
        if event_type == "completed" and actual_output <= 0:
            warnings.append(
                {
                    "severity": "warning",
                    "message": "This run has no recorded finished output yet. Completion will not create inventory automatically.",
                }
            )
        consequences = [
            {
                "label": "Run status",
                "before": str(order.status).replace("_", " ").title(),
                "after": str(status_after).replace("_", " ").title(),
            }
        ]
        if waste_quantity is not None:
            consequences.append(
                {
                    "label": "Measured waste",
                    "before": "No new waste event",
                    "after": f"Record {waste_quantity:g} {payload.get('unit') or 'unit'} waste",
                }
            )
        if quantity is not None:
            consequences.append(
                {
                    "label": "Recorded quantity",
                    "before": "No new event quantity",
                    "after": f"Record {quantity:g} {payload.get('unit') or 'unit'}",
                }
            )
        return {
            "title": f"{event_type.replace('_', ' ').title()} run",
            "summary": f"Record a {event_type.replace('_', ' ')} event and move the run from {order.status} to {status_after}.",
            "consequences": consequences,
            "warnings": warnings,
            "details": {
                "event_type": event_type,
                "status_before": order.status,
                "status_after": status_after,
                "quantity": quantity,
                "waste_quantity": waste_quantity,
                "labor_hours": labor_hours,
                "machine_hours": machine_hours,
            },
            "_state": {
                "order_status": order.status,
                "order_updated_at": getattr(order, "updated_at", None),
                "latest_event": None
                if latest is None
                else {"id": latest.id, "event_type": latest.event_type, "occurred_at": latest.occurred_at},
                "actual_output": actual_output,
                "qa_required": qa_required,
                "qa_passed": qa_passed,
            },
        }

    def _preview_output_actual(
        self,
        session: Session,
        facility_id: str,
        order: ProductionOrder,
        payload: dict[str, Any],
        *,
        lock: bool,
    ) -> dict[str, Any]:
        output_id = str(payload.get("output_id") or "").strip()
        if not output_id:
            raise ValueError("Choose a production output before previewing the actual quantity.")
        query = select(ProductionRunOutput).where(
            ProductionRunOutput.id == output_id,
            ProductionRunOutput.production_order_id == order.id,
        )
        if lock:
            query = query.with_for_update()
        output = session.scalar(query)
        if output is None:
            raise ValueError("Production output was not found on this run.")
        actual_quantity = self._required_nonnegative(payload.get("actual_quantity"), "Actual output")
        lot_code = str(payload.get("lot_code") or "").strip()
        old_actual = float(output.actual_quantity or 0.0)
        delta = actual_quantity - old_actual
        lot = None
        balance = 0.0
        if output.lot_id:
            lot_query = select(InventoryLot).where(InventoryLot.id == output.lot_id)
            if lock:
                lot_query = lot_query.with_for_update()
            lot = session.scalar(lot_query)
            if lot is None:
                raise ValueError("The output points to an inventory lot that no longer exists.")
            balance = float(
                session.scalar(
                    select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                        InventoryTransaction.lot_id == lot.id
                    )
                )
                or 0.0
            )
        elif actual_quantity > 0:
            if not lot_code:
                raise ValueError("Enter a finished lot code so the measured output can be placed on the inventory ledger.")
            duplicate = session.scalar(
                select(InventoryLot).where(
                    InventoryLot.facility_id == facility_id,
                    InventoryLot.lot_code == lot_code,
                )
            )
            if duplicate:
                raise ValueError("That finished lot code already exists in this facility.")

        planned_total = float(
            session.scalar(
                select(func.coalesce(func.sum(ProductionRunOutput.planned_quantity), 0.0)).where(
                    ProductionRunOutput.production_order_id == order.id
                )
            )
            or float(order.requested_units or 0)
        )
        actual_total = float(
            session.scalar(
                select(func.coalesce(func.sum(ProductionRunOutput.actual_quantity), 0.0)).where(
                    ProductionRunOutput.production_order_id == order.id
                )
            )
            or 0.0
        )
        actual_after = actual_total + delta
        warnings: list[dict[str, str]] = []
        if lot is not None and balance + delta < -1e-9:
            warnings.append(
                {
                    "severity": "blocker",
                    "message": "The proposed reduction is larger than the remaining lot balance. Downstream inventory use must be reconciled before lowering this production actual.",
                }
            )
        if delta != 0 and output.status == "released":
            warnings.append(
                {
                    "severity": "warning",
                    "message": "Changing a released output will return it to QA quarantine and revoke lot availability until QA releases it again.",
                }
            )

        consequences = [
            {
                "label": output.label,
                "before": f"Actual {old_actual:g} {output.unit}",
                "after": f"Actual {actual_quantity:g} {output.unit}",
            },
            {
                "label": "Run attainment",
                "before": self._pct(actual_total, planned_total),
                "after": self._pct(actual_after, planned_total),
            },
        ]
        if delta != 0:
            consequences.append(
                {
                    "label": "Inventory ledger",
                    "before": f"{balance:g} {output.unit} on lot" if lot else "No finished lot exists",
                    "after": (
                        f"Append {delta:+g} {output.unit} adjustment to {lot.lot_code}"
                        if lot
                        else f"Create {lot_code} in QA hold with +{actual_quantity:g} {output.unit}"
                    ),
                }
            )
            consequences.append(
                {
                    "label": "QA status",
                    "before": str(output.status).replace("_", " ").title(),
                    "after": "Quarantine",
                }
            )
        else:
            consequences.append(
                {
                    "label": "Inventory ledger",
                    "before": "Current ledger remains authoritative",
                    "after": "No inventory quantity change",
                }
            )
        return {
            "title": "Post measured output",
            "summary": f"Change {output.label} from {old_actual:g} to {actual_quantity:g} {output.unit}; inventory delta {delta:+g} {output.unit}.",
            "consequences": consequences,
            "warnings": warnings,
            "details": {
                "output_id": output.id,
                "old_actual": old_actual,
                "new_actual": actual_quantity,
                "inventory_delta": delta,
                "existing_lot_id": output.lot_id,
                "lot_code": lot.lot_code if lot else lot_code,
                "actual_total_after": actual_after,
                "attainment_after": (actual_after / planned_total * 100.0) if planned_total > 0 else 0.0,
            },
            "_state": {
                "order_status": order.status,
                "order_updated_at": getattr(order, "updated_at", None),
                "output": {
                    "id": output.id,
                    "actual_quantity": old_actual,
                    "planned_quantity": output.planned_quantity,
                    "status": output.status,
                    "lot_id": output.lot_id,
                    "updated_at": getattr(output, "updated_at", None),
                },
                "lot": None
                if lot is None
                else {
                    "id": lot.id,
                    "lot_code": lot.lot_code,
                    "status": lot.status,
                    "location_code": lot.location_code,
                    "balance": balance,
                    "updated_at": getattr(lot, "updated_at", None),
                },
                "actual_total": actual_total,
                "planned_total": planned_total,
            },
        }

    def _preview_qa(
        self,
        session: Session,
        order: ProductionOrder,
        payload: dict[str, Any],
        *,
        lock: bool,
    ) -> dict[str, Any]:
        event_type = str(payload.get("event_type") or "").strip()
        result = str(payload.get("result") or "pending").strip()
        if event_type not in QA_EVENT_TYPES:
            raise ValueError("Unsupported QA event type.")
        if result not in QA_RESULTS:
            raise ValueError("Unsupported QA result.")
        if event_type == "release" and result != "passed":
            raise ValueError("A QA release requires a passed result.")
        output_id = str(payload.get("output_id") or "").strip() or None
        query = select(ProductionRunOutput).where(ProductionRunOutput.production_order_id == order.id)
        if output_id:
            query = query.where(ProductionRunOutput.id == output_id)
        if lock:
            query = query.with_for_update()
        outputs = list(session.scalars(query))
        if output_id and not outputs:
            raise ValueError("QA output is not part of this production order.")
        target_ids = {row.id for row in outputs}
        lots: dict[str, InventoryLot] = {}
        lot_state: list[dict[str, Any]] = []
        for output in outputs:
            if not output.lot_id:
                continue
            lot_query = select(InventoryLot).where(InventoryLot.id == output.lot_id)
            if lock:
                lot_query = lot_query.with_for_update()
            lot = session.scalar(lot_query)
            if lot:
                lots[output.id] = lot
                lot_state.append(
                    {
                        "id": lot.id,
                        "output_id": output.id,
                        "status": lot.status,
                        "location_code": lot.location_code,
                        "updated_at": getattr(lot, "updated_at", None),
                    }
                )
        latest = session.scalar(
            select(ProductionQAEvent)
            .where(ProductionQAEvent.production_order_id == order.id)
            .order_by(ProductionQAEvent.occurred_at.desc())
            .limit(1)
        )
        standard = self._standard_for_order(session, order)
        warnings: list[dict[str, str]] = []
        document_reference = str(payload.get("document_reference") or "").strip()
        if event_type == "release" and bool(getattr(standard, "qa_required", False)) and not document_reference:
            warnings.append(
                {
                    "severity": "warning",
                    "message": "This BOM requires QA. Add the COA/document reference when available so the release evidence is complete.",
                }
            )
        if event_type == "release" and not outputs:
            warnings.append(
                {
                    "severity": "warning",
                    "message": "There are no production output rows to release; this will only record the QA decision.",
                }
            )

        consequences: list[dict[str, str]] = [
            {
                "label": "QA evidence",
                "before": "No new QA event",
                "after": f"Record {event_type.replace('_', ' ')} / {result.replace('_', ' ')}",
            }
        ]
        status_after = order.status
        if event_type == "hold" or result == "failed":
            status_after = "on_hold"
            for output in outputs:
                consequences.append(
                    {
                        "label": output.label,
                        "before": str(output.status).replace("_", " ").title(),
                        "after": "Quarantine / unavailable",
                    }
                )
        elif event_type == "release" and result == "passed":
            completed = session.scalar(
                select(ProductionRunEvent.id).where(
                    ProductionRunEvent.production_order_id == order.id,
                    ProductionRunEvent.event_type == "completed",
                ).limit(1)
            )
            if order.status == "on_hold":
                status_after = "complete" if completed else "in_progress"
            for output in outputs:
                if output.status in {"quarantine", "rework"}:
                    consequences.append(
                        {
                            "label": output.label,
                            "before": str(output.status).replace("_", " ").title(),
                            "after": "Released / inventory available",
                        }
                    )
        if status_after != order.status:
            consequences.insert(
                0,
                {
                    "label": "Run status",
                    "before": str(order.status).replace("_", " ").title(),
                    "after": str(status_after).replace("_", " ").title(),
                },
            )
        return {
            "title": "Post QA decision",
            "summary": f"Apply {event_type.replace('_', ' ')} / {result.replace('_', ' ')} to {'the whole run' if not output_id else 'one output'}.",
            "consequences": consequences,
            "warnings": warnings,
            "details": {
                "event_type": event_type,
                "result": result,
                "output_id": output_id,
                "target_output_ids": sorted(target_ids),
                "status_before": order.status,
                "status_after": status_after,
            },
            "_state": {
                "order_status": order.status,
                "order_updated_at": getattr(order, "updated_at", None),
                "latest_qa": None
                if latest is None
                else {"id": latest.id, "event_type": latest.event_type, "result": latest.result, "occurred_at": latest.occurred_at},
                "outputs": [
                    {
                        "id": row.id,
                        "status": row.status,
                        "actual_quantity": row.actual_quantity,
                        "lot_id": row.lot_id,
                        "updated_at": getattr(row, "updated_at", None),
                    }
                    for row in outputs
                ],
                "lots": lot_state,
            },
        }

    def _preview_cost(self, session: Session, order: ProductionOrder, payload: dict[str, Any]) -> dict[str, Any]:
        category = str(payload.get("category") or "").strip()
        if category not in COST_CATEGORIES:
            raise ValueError("Unsupported production cost category.")
        amount = self._required_nonnegative(payload.get("amount_usd"), "Cost amount")
        quantity = self._optional_nonnegative(payload.get("quantity"), "Cost quantity")
        current_total = float(
            session.scalar(
                select(func.coalesce(func.sum(ProductionCostEvent.amount_usd), 0.0)).where(
                    ProductionCostEvent.production_order_id == order.id
                )
            )
            or 0.0
        )
        actual_output = float(
            session.scalar(
                select(func.coalesce(func.sum(ProductionRunOutput.actual_quantity), 0.0)).where(
                    ProductionRunOutput.production_order_id == order.id
                )
            )
            or 0.0
        )
        latest = session.scalar(
            select(ProductionCostEvent)
            .where(ProductionCostEvent.production_order_id == order.id)
            .order_by(ProductionCostEvent.occurred_at.desc())
            .limit(1)
        )
        after = current_total + amount
        consequences = [
            {"label": "Run COGS", "before": f"${current_total:,.2f}", "after": f"${after:,.2f}"},
            {
                "label": "Cost / actual unit",
                "before": self._money_per_unit(current_total, actual_output),
                "after": self._money_per_unit(after, actual_output),
            },
            {
                "label": category.replace("_", " ").title(),
                "before": "No new cost event",
                "after": f"Add ${amount:,.2f}",
            },
        ]
        warnings = []
        if actual_output <= 0:
            warnings.append(
                {
                    "severity": "warning",
                    "message": "No finished output has been posted yet, so cost per unit will remain unavailable until output exists.",
                }
            )
        return {
            "title": "Add run cost",
            "summary": f"Add ${amount:,.2f} of {category.replace('_', ' ')} cost; total COGS becomes ${after:,.2f}.",
            "consequences": consequences,
            "warnings": warnings,
            "details": {
                "category": category,
                "amount_usd": amount,
                "quantity": quantity,
                "cogs_before": current_total,
                "cogs_after": after,
                "actual_output": actual_output,
            },
            "_state": {
                "order_status": order.status,
                "order_updated_at": getattr(order, "updated_at", None),
                "current_total": current_total,
                "actual_output": actual_output,
                "latest_cost": None
                if latest is None
                else {"id": latest.id, "amount_usd": latest.amount_usd, "occurred_at": latest.occurred_at},
            },
        }

    def _apply(
        self,
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        action_type: str,
        payload: dict[str, Any],
        preview: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        if action_type == "reserve_materials":
            return self._apply_reservations(
                session, organization_id, facility_id, order, preview, actor
            )
        if action_type == "run_event":
            return self._apply_run_event(session, organization_id, facility_id, order, payload, actor)
        if action_type == "record_output_actual":
            return self._apply_output_actual(session, organization_id, facility_id, order, payload, actor)
        if action_type == "qa_decision":
            return self._apply_qa(session, organization_id, facility_id, order, payload, actor)
        return self._apply_cost(session, organization_id, facility_id, order, payload, actor)

    @staticmethod
    def _apply_reservations(
        session: Session,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        preview: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        allocations = list(preview.get("details", {}).get("allocations") or [])
        for allocation in allocations:
            reservation = session.scalar(
                select(MaterialReservation).where(
                    MaterialReservation.production_order_id == order.id,
                    MaterialReservation.lot_id == allocation["lot_id"],
                )
            )
            if reservation is None:
                reservation = MaterialReservation(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    production_order_id=order.id,
                    lot_id=allocation["lot_id"],
                    quantity=float(allocation["quantity"]),
                    unit=allocation["unit"],
                    status="reserved",
                    reserved_by=actor,
                )
                session.add(reservation)
            else:
                reservation.quantity = float(reservation.quantity or 0) + float(allocation["quantity"])
                reservation.status = "reserved"
                reservation.reserved_by = actor
        return {
            "allocations_added": allocations,
            "shortages": list(preview.get("details", {}).get("shortages") or []),
        }

    @staticmethod
    def _apply_run_event(
        session: Session,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        event_type = str(payload.get("event_type") or "").strip()
        event = ProductionRunEvent(
            organization_id=organization_id,
            facility_id=facility_id,
            production_order_id=order.id,
            stage_key=str(payload.get("stage_key") or "execution"),
            event_type=event_type,
            quantity=ProductionMutationService._float_or_none(payload.get("quantity")),
            unit=str(payload.get("unit") or "unit"),
            waste_quantity=ProductionMutationService._float_or_none(payload.get("waste_quantity")),
            labor_hours=ProductionMutationService._float_or_none(payload.get("labor_hours")),
            machine_hours=ProductionMutationService._float_or_none(payload.get("machine_hours")),
            notes=str(payload.get("notes") or ""),
            actor=actor,
        )
        session.add(event)
        if event_type == "hold":
            order.status = "on_hold"
        elif event_type == "release" and order.status == "on_hold":
            order.status = "in_progress"
        elif event_type == "completed":
            order.status = "complete"
        session.flush()
        return {"event_id": event.id, "event_type": event_type, "order_status": order.status}

    @staticmethod
    def _apply_output_actual(
        session: Session,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        output_id = str(payload.get("output_id") or "").strip()
        output = session.scalar(
            select(ProductionRunOutput).where(
                ProductionRunOutput.id == output_id,
                ProductionRunOutput.production_order_id == order.id,
            )
        )
        if output is None:
            raise ValueError("Production output was not found on this run.")
        new_actual = float(payload.get("actual_quantity") or 0.0)
        old_actual = float(output.actual_quantity or 0.0)
        delta = new_actual - old_actual
        lot_code = str(payload.get("lot_code") or "").strip()
        lot = session.get(InventoryLot, output.lot_id) if output.lot_id else None
        if abs(delta) <= 1e-9:
            return {
                "output_id": output.id,
                "actual_quantity": old_actual,
                "inventory_delta": 0.0,
                "lot_id": output.lot_id,
                "status": output.status,
            }
        if lot is None:
            lot = InventoryLot(
                organization_id=organization_id,
                facility_id=facility_id,
                product_id=output.product_id,
                lot_code=lot_code,
                location_code="QA-HOLD",
                status="quarantine",
                notes=f"Production output {output.id}",
            )
            session.add(lot)
            session.flush()
            output.lot_id = lot.id
            transaction_delta = new_actual
            transaction_type = "production_output"
        else:
            transaction_delta = delta
            transaction_type = "production_output_adjustment"
        if abs(transaction_delta) > 1e-9:
            session.add(
                InventoryTransaction(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    lot_id=lot.id,
                    transaction_type=transaction_type,
                    quantity_delta=transaction_delta,
                    unit=output.unit,
                    production_order_id=order.id,
                    commercial_order_id=None,
                    commercial_order_line_id=None,
                    reason="Production output quantity posted from Run 360; QA release required",
                    reference=output.id,
                    actor=actor,
                )
            )
        output.actual_quantity = new_actual
        output.status = "quarantine"
        lot.status = "quarantine"
        lot.location_code = "QA-HOLD"
        session.flush()
        return {
            "output_id": output.id,
            "actual_quantity": new_actual,
            "inventory_delta": transaction_delta,
            "lot_id": lot.id,
            "lot_code": lot.lot_code,
            "status": output.status,
        }

    @staticmethod
    def _apply_qa(
        session: Session,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        output_id = str(payload.get("output_id") or "").strip() or None
        event_type = str(payload.get("event_type") or "").strip()
        result = str(payload.get("result") or "pending").strip()
        event = ProductionQAEvent(
            organization_id=organization_id,
            facility_id=facility_id,
            production_order_id=order.id,
            output_id=output_id,
            event_type=event_type,
            result=result,
            document_reference=str(payload.get("document_reference") or ""),
            notes=str(payload.get("notes") or ""),
            actor=actor,
        )
        session.add(event)
        outputs_query = select(ProductionRunOutput).where(ProductionRunOutput.production_order_id == order.id)
        if output_id:
            outputs_query = outputs_query.where(ProductionRunOutput.id == output_id)
        outputs = list(session.scalars(outputs_query))
        if event_type == "hold" or result == "failed":
            order.status = "on_hold"
            for output in outputs:
                if output.status not in {"waste", "destroyed"}:
                    output.status = "quarantine"
                if output.lot_id:
                    lot = session.get(InventoryLot, output.lot_id)
                    if lot:
                        lot.status = "quarantine"
                        lot.location_code = "QA-HOLD"
        elif event_type == "release" and result == "passed":
            for output in outputs:
                if output.status in {"quarantine", "rework"}:
                    output.status = "released"
                    if output.lot_id:
                        lot = session.get(InventoryLot, output.lot_id)
                        if lot:
                            lot.status = "available"
                            if lot.location_code == "QA-HOLD":
                                lot.location_code = "UNASSIGNED"
            if order.status == "on_hold":
                completed = session.scalar(
                    select(ProductionRunEvent.id).where(
                        ProductionRunEvent.production_order_id == order.id,
                        ProductionRunEvent.event_type == "completed",
                    ).limit(1)
                )
                order.status = "complete" if completed else "in_progress"
        session.flush()
        return {
            "qa_event_id": event.id,
            "event_type": event_type,
            "result": result,
            "output_id": output_id,
            "order_status": order.status,
        }

    @staticmethod
    def _apply_cost(
        session: Session,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        event = ProductionCostEvent(
            organization_id=organization_id,
            facility_id=facility_id,
            production_order_id=order.id,
            category=str(payload.get("category") or "other"),
            amount_usd=float(payload.get("amount_usd") or 0.0),
            quantity=ProductionMutationService._float_or_none(payload.get("quantity")),
            unit=str(payload.get("unit") or ""),
            source_type=str(payload.get("source_type") or "manual"),
            source_id=str(payload.get("source_id") or ""),
            notes=str(payload.get("notes") or ""),
            actor=actor,
        )
        session.add(event)
        session.flush()
        return {"cost_event_id": event.id, "category": event.category, "amount_usd": event.amount_usd}

    def _standard_for_order(self, session: Session, order: ProductionOrder):
        product = self.erp._resolve_output_product(session, order.organization_id, order)
        if not product:
            return None
        bom = self.erp._active_bom(session, order.organization_id, product.id)
        return self.erp._standard_for_bom(session, order.organization_id, bom)

    @staticmethod
    def _required_nonnegative(value: Any, label: str) -> float:
        if value is None or value == "":
            raise ValueError(f"{label} is required.")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be numeric.") from exc
        if parsed < 0:
            raise ValueError(f"{label} cannot be negative.")
        return parsed

    @staticmethod
    def _optional_nonnegative(value: Any, label: str) -> float | None:
        if value is None or value == "":
            return None
        return ProductionMutationService._required_nonnegative(value, label)

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        return None if value is None or value == "" else float(value)

    @staticmethod
    def _normalized(value: Any) -> Any:
        return json.loads(json.dumps(value, default=str, sort_keys=True))

    @staticmethod
    def _fingerprint(value: Any) -> str:
        payload = json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _pct(actual: float, planned: float) -> str:
        return f"{(actual / planned * 100.0):.1f}%" if planned > 0 else "—"

    @staticmethod
    def _money_per_unit(total: float, actual_output: float) -> str:
        return f"${(total / actual_output):,.2f}" if actual_output > 0 else "—"
