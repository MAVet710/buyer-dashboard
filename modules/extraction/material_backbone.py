"""Canonical Extraction inventory claims, WIP handoffs, and closeout invariants.

Extraction uses the shared append-only inventory ledger and material transformation
edges.  This module closes the remaining gaps without adding a parallel quantity
system: partial Extraction reservations participate in the organization-wide
availability projection, WIP outputs become explicit downstream handoffs, and a
run cannot become complete until its physical mass and reservations reconcile.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session

from modules.coman.models import (
    CommercialOrder,
    CommercialOrderLine,
    InventoryLot,
    InventoryTransaction,
    OrderLotAllocation,
    Product,
    TradePartner,
    utc_now,
)
from modules.inventory_availability.service import InventoryAvailabilityService, _passed_coa_hint
from modules.material_lineage.models import MaterialTransformation, MaterialTransformationLoss, MaterialTransformationOutput

from .models import ExtractionRun, ExtractionRunInput, ExtractionRunOutput, ExtractionStageEvent
from .repository import ExtractionRepository, INPUT_OPEN_STATUSES


_REGISTERED = False
_ORIGINAL_AVAILABILITY_BUILD = InventoryAvailabilityService.build
_ORIGINAL_CREATE_OUTPUT = ExtractionRepository.create_output
_ACTIVE_EXTRACTION_RUN_STATUSES = {"planned", "queued", "active", "hold", "qa"}
_ACTIVE_SALES_STATUSES = {"confirmed", "allocated", "partially_fulfilled"}
_ACTIVE_ALLOCATION_STATUSES = {"reserved", "partial"}
_ACTIVE_LOT_STATUSES = {"available", "released", "reserved"}  # reserved is legacy Extraction compatibility.
_CLOSEOUT_TOLERANCE_FRACTION = 0.001
_CLOSEOUT_TOLERANCE_MIN_G = 0.01


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _pending_or_persisted(session: Session, model, object_id: str | None):
    if not object_id:
        return None
    for row in session.new:
        if isinstance(row, model) and getattr(row, "id", None) == object_id:
            return row
    with session.no_autoflush:
        return session.get(model, object_id)


def _availability_with_extraction(session: Session, organization_id: str, facility_id: str) -> dict[str, Any]:
    """Extend the canonical projection with active Extraction claims.

    The base service already owns Production, hard Wholesale allocations, and soft
    sales commitments.  We add Extraction before recomputing soft commitments so
    one gram cannot be promised simultaneously to Extraction and a sales order.
    """

    snapshot = _ORIGINAL_AVAILABILITY_BUILD(session, organization_id, facility_id)
    lot_rows = snapshot.get("by_lot", {})
    if not lot_rows:
        return snapshot

    runs = {
        row.id: row
        for row in session.scalars(
            select(ExtractionRun).where(
                ExtractionRun.organization_id == organization_id,
                ExtractionRun.facility_id == facility_id,
            )
        )
    }
    reservations = list(
        session.scalars(
            select(ExtractionRunInput).where(
                ExtractionRunInput.organization_id == organization_id,
                ExtractionRunInput.facility_id == facility_id,
                ExtractionRunInput.status.in_(tuple(INPUT_OPEN_STATUSES)),
            )
        )
    )
    extraction_reserved_by_lot: dict[str, float] = defaultdict(float)
    integrity_issues = list(snapshot.get("integrity_issues") or [])

    for reservation in reservations:
        remaining = max(
            0.0,
            float(reservation.reserved_quantity or 0.0) - float(reservation.consumed_quantity or 0.0),
        )
        if remaining <= 1e-9:
            continue
        row = lot_rows.get(reservation.lot_id)
        if row is None:
            integrity_issues.append(
                {
                    "code": "extraction_reservation_outside_scope",
                    "severity": "blocker",
                    "lot_id": reservation.lot_id,
                    "reference_id": reservation.id,
                    "message": "Active Extraction reservation references a lot outside the active facility.",
                }
            )
            continue
        run = runs.get(reservation.run_id)
        if run is None:
            integrity_issues.append(
                {
                    "code": "extraction_reservation_missing_run",
                    "severity": "blocker",
                    "lot_id": reservation.lot_id,
                    "reference_id": reservation.id,
                    "message": "Active Extraction reservation has no scoped Extraction run.",
                }
            )
            continue
        if str(run.status or "").casefold() not in _ACTIVE_EXTRACTION_RUN_STATUSES:
            integrity_issues.append(
                {
                    "code": "stale_extraction_reservation",
                    "severity": "warning",
                    "lot_id": reservation.lot_id,
                    "reference_id": reservation.id,
                    "message": f"Extraction reservation remains open after run {run.batch_number} reached {run.status}.",
                }
            )
            continue
        extraction_reserved_by_lot[reservation.lot_id] += remaining
        row.setdefault("claims", []).append(
            {
                "source": "extraction",
                "claim_type": "reserved",
                "quantity": remaining,
                "reference_id": run.id,
                "reference": run.batch_number,
                "label": f"Extraction {run.batch_number}",
            }
        )

    # Rebuild physical-free quantity before unallocated Wholesale commitments.
    for row in lot_rows.values():
        lot = row["lot"]
        extraction_reserved = max(0.0, extraction_reserved_by_lot.get(lot.id, 0.0))
        row["extraction_reserved"] = extraction_reserved
        row["claims"] = [claim for claim in row.get("claims", []) if claim.get("claim_type") != "committed"]
        row["wholesale_committed"] = 0.0
        active = str(lot.status or "").casefold() in _ACTIVE_LOT_STATUSES
        row["active"] = active
        row["physical_free"] = (
            max(
                0.0,
                float(row.get("on_hand", 0.0))
                - float(row.get("production_reserved", 0.0))
                - float(row.get("wholesale_reserved", 0.0))
                - extraction_reserved,
            )
            if active
            else 0.0
        )

    # Re-run the soft Wholesale commitment assignment after Extraction claims.
    sales_orders = list(
        session.scalars(
            select(CommercialOrder).where(
                CommercialOrder.organization_id == organization_id,
                CommercialOrder.facility_id == facility_id,
                CommercialOrder.order_type == "sales",
                CommercialOrder.status.in_(_ACTIVE_SALES_STATUSES),
            )
        )
    )
    sales_order_by_id = {row.id: row for row in sales_orders}
    sales_order_ids = set(sales_order_by_id)
    sales_lines = (
        list(
            session.scalars(
                select(CommercialOrderLine).where(
                    CommercialOrderLine.organization_id == organization_id,
                    CommercialOrderLine.commercial_order_id.in_(sales_order_ids),
                )
            )
        )
        if sales_order_ids
        else []
    )
    allocations = list(
        session.scalars(
            select(OrderLotAllocation).where(
                OrderLotAllocation.organization_id == organization_id,
                OrderLotAllocation.facility_id == facility_id,
                OrderLotAllocation.status.in_(_ACTIVE_ALLOCATION_STATUSES),
            )
        )
    )
    allocated_by_line: dict[str, float] = defaultdict(float)
    for allocation in allocations:
        if allocation.commercial_order_id not in sales_order_by_id:
            continue
        allocated_by_line[allocation.commercial_order_line_id] += max(
            0.0,
            float(allocation.quantity or 0.0) - float(allocation.fulfilled_quantity or 0.0),
        )
    partners = {
        row.id: row
        for row in session.scalars(
            select(TradePartner).where(TradePartner.organization_id == organization_id)
        )
    }
    commitments: list[dict[str, Any]] = []
    for line in sales_lines:
        order = sales_order_by_id.get(line.commercial_order_id)
        if order is None:
            continue
        remaining_line = max(0.0, float(line.quantity or 0.0) - float(line.fulfilled_quantity or 0.0))
        unallocated = max(0.0, remaining_line - allocated_by_line.get(line.id, 0.0))
        if unallocated <= 0:
            continue
        commitments.append(
            {
                "line_id": line.id,
                "product_id": line.product_id,
                "quantity": unallocated,
                "order_id": order.id,
                "order_number": order.order_number,
                "customer": getattr(partners.get(order.partner_id), "name", ""),
                "due_at": order.due_at,
                "created_at": order.created_at,
            }
        )
    commitments.sort(
        key=lambda row: (
            str(row.get("due_at") or "9999-12-31"),
            str(row.get("created_at") or ""),
            str(row.get("order_number") or ""),
        )
    )
    lots_by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in lot_rows.values():
        lots_by_product[row["lot"].product_id].append(row)
    uncovered_by_product: dict[str, float] = defaultdict(float)
    for commitment in commitments:
        remaining = float(commitment["quantity"])
        candidates = sorted(
            lots_by_product.get(commitment["product_id"], []),
            key=lambda row: (
                0 if _passed_coa_hint(row["lot"]) else 1,
                str(row["lot"].expiration_at or "9999-12-31"),
                str(row["lot"].received_at or "9999-12-31"),
                row["lot"].lot_code,
            ),
        )
        for row in candidates:
            room = max(
                0.0,
                float(row.get("physical_free", 0.0)) - float(row.get("wholesale_committed", 0.0)),
            )
            if room <= 0 or remaining <= 0:
                continue
            claimed = min(room, remaining)
            row["wholesale_committed"] += claimed
            row.setdefault("claims", []).append(
                {
                    "source": "wholesale",
                    "claim_type": "committed",
                    "quantity": claimed,
                    "reference_id": commitment["order_id"],
                    "reference": commitment["order_number"],
                    "customer": commitment["customer"],
                    "label": f"Wholesale {commitment['order_number']}",
                }
            )
            remaining -= claimed
        if remaining > 1e-9:
            uncovered_by_product[commitment["product_id"]] += remaining

    by_product: dict[str, dict[str, Any]] = {}
    for product_id, rows in lots_by_product.items():
        for row in rows:
            row["reserved"] = (
                float(row.get("production_reserved", 0.0))
                + float(row.get("wholesale_reserved", 0.0))
                + float(row.get("extraction_reserved", 0.0))
                + float(row.get("wholesale_committed", 0.0))
            )
            row["available"] = (
                max(0.0, float(row.get("on_hand", 0.0)) - row["reserved"])
                if row.get("active")
                else 0.0
            )
        by_product[product_id] = {
            "product_id": product_id,
            "on_hand": sum(float(row.get("on_hand", 0.0)) for row in rows),
            "production_reserved": sum(float(row.get("production_reserved", 0.0)) for row in rows),
            "wholesale_reserved": sum(float(row.get("wholesale_reserved", 0.0)) for row in rows),
            "extraction_reserved": sum(float(row.get("extraction_reserved", 0.0)) for row in rows),
            "wholesale_committed": sum(float(row.get("wholesale_committed", 0.0)) for row in rows),
            "reserved": sum(float(row.get("reserved", 0.0)) for row in rows),
            "available": sum(float(row.get("available", 0.0)) for row in rows),
            "uncovered_commitment": float(uncovered_by_product.get(product_id, 0.0)),
        }

    snapshot["lots"] = list(lot_rows.values())
    snapshot["by_lot"] = lot_rows
    snapshot["by_product"] = by_product
    snapshot["uncovered_commitments"] = dict(uncovered_by_product)
    snapshot["integrity_issues"] = integrity_issues
    return snapshot


def _latest_completed_losses(session: Session, run: ExtractionRun) -> float:
    """Use the latest completed measurement per stage as explicit process loss."""

    with session.no_autoflush:
        events = list(
            session.scalars(
                select(ExtractionStageEvent)
                .where(
                    ExtractionStageEvent.organization_id == run.organization_id,
                    ExtractionStageEvent.facility_id == run.facility_id,
                    ExtractionStageEvent.run_id == run.id,
                    ExtractionStageEvent.event_type == "completed",
                )
                .order_by(ExtractionStageEvent.occurred_at, ExtractionStageEvent.id)
            )
        )
    for pending in session.new:
        if (
            isinstance(pending, ExtractionStageEvent)
            and pending.organization_id == run.organization_id
            and pending.facility_id == run.facility_id
            and pending.run_id == run.id
            and pending.event_type == "completed"
        ):
            events.append(pending)
    latest: dict[str, ExtractionStageEvent] = {}
    for row in events:
        latest[row.stage_key] = row
    return sum(max(0.0, float(row.loss_weight_g or 0.0)) for row in latest.values())


def _run_inputs(session: Session, run: ExtractionRun) -> list[ExtractionRunInput]:
    with session.no_autoflush:
        rows = list(
            session.scalars(
                select(ExtractionRunInput).where(
                    ExtractionRunInput.organization_id == run.organization_id,
                    ExtractionRunInput.facility_id == run.facility_id,
                    ExtractionRunInput.run_id == run.id,
                )
            )
        )
    return rows


def _run_outputs(session: Session, run: ExtractionRun) -> list[ExtractionRunOutput]:
    with session.no_autoflush:
        rows = list(
            session.scalars(
                select(ExtractionRunOutput).where(
                    ExtractionRunOutput.organization_id == run.organization_id,
                    ExtractionRunOutput.facility_id == run.facility_id,
                    ExtractionRunOutput.run_id == run.id,
                )
            )
        )
    rows.extend(
        row
        for row in session.new
        if isinstance(row, ExtractionRunOutput)
        and row.organization_id == run.organization_id
        and row.facility_id == run.facility_id
        and row.run_id == run.id
        and row not in rows
    )
    return rows


def _closeout_state(session: Session, run: ExtractionRun) -> dict[str, Any]:
    inputs = _run_inputs(session, run)
    outputs = _run_outputs(session, run)
    open_reservations = [
        row
        for row in inputs
        if row.status in INPUT_OPEN_STATUSES
        and float(row.reserved_quantity or 0.0) - float(row.consumed_quantity or 0.0) > 1e-9
    ]
    units = {str(row.unit or "").strip().casefold() for row in inputs + outputs if str(row.unit or "").strip()}
    consumed = sum(max(0.0, float(row.consumed_quantity or 0.0)) for row in inputs)
    output_quantity = sum(max(0.0, float(row.quantity or 0.0)) for row in outputs)
    explicit_loss = _latest_completed_losses(session, run)
    unexplained = consumed - output_quantity - explicit_loss
    tolerance = max(_CLOSEOUT_TOLERANCE_MIN_G, consumed * _CLOSEOUT_TOLERANCE_FRACTION)
    blockers: list[str] = []
    if consumed <= 1e-9:
        blockers.append("No actual source material has been consumed.")
    if not outputs:
        blockers.append("No durable Extraction output has been posted to inventory.")
    if open_reservations:
        blockers.append("Unused Extraction reservations remain open; consume or release them before closeout.")
    if units and units != {"g"}:
        blockers.append("Extraction closeout requires one canonical gram basis for inputs and outputs.")
    if consumed > 1e-9 and abs(unexplained) > tolerance:
        direction = "unexplained loss" if unexplained > 0 else "over-accounted material"
        blockers.append(
            f"Mass balance has {abs(unexplained):.4f} g {direction}; record the exact stage loss/output before closeout."
        )
    return {
        "consumed_input": consumed,
        "recorded_output": output_quantity,
        "explicit_process_loss": explicit_loss,
        "unexplained_variance": unexplained,
        "tolerance_g": tolerance,
        "open_reservation_count": len(open_reservations),
        "blockers": blockers,
    }


def _require_closeout(session: Session, run: ExtractionRun) -> dict[str, Any]:
    state = _closeout_state(session, run)
    if state["blockers"]:
        raise ValueError("Extraction closeout is incomplete: " + " ".join(state["blockers"]))
    return state


def _find_transformation(session: Session, run: ExtractionRun) -> MaterialTransformation | None:
    for row in session.new:
        if (
            isinstance(row, MaterialTransformation)
            and row.organization_id == run.organization_id
            and row.facility_id == run.facility_id
            and row.transformation_type == "extraction_run"
            and row.source_entity_type == "extraction_run"
            and row.source_entity_id == run.id
        ):
            return row
    with session.no_autoflush:
        return session.scalar(
            select(MaterialTransformation).where(
                MaterialTransformation.organization_id == run.organization_id,
                MaterialTransformation.facility_id == run.facility_id,
                MaterialTransformation.transformation_type == "extraction_run",
                MaterialTransformation.source_entity_type == "extraction_run",
                MaterialTransformation.source_entity_id == run.id,
            )
        )


def _commit_transformation(session: Session, run: ExtractionRun, closeout: dict[str, Any]) -> None:
    transform = _find_transformation(session, run)
    if transform is None:
        raise ValueError("Extraction closeout cannot complete before canonical material genealogy exists.")
    explicit_loss = max(0.0, float(closeout.get("explicit_process_loss") or 0.0))
    existing = None
    for row in session.new:
        if (
            isinstance(row, MaterialTransformationLoss)
            and row.transformation_id == transform.id
            and row.loss_type == "extraction_process_loss"
        ):
            existing = row
            break
    if existing is None:
        with session.no_autoflush:
            existing = session.scalar(
                select(MaterialTransformationLoss).where(
                    MaterialTransformationLoss.transformation_id == transform.id,
                    MaterialTransformationLoss.loss_type == "extraction_process_loss",
                )
            )
    if explicit_loss > 1e-9:
        if existing is None:
            session.add(
                MaterialTransformationLoss(
                    organization_id=run.organization_id,
                    facility_id=run.facility_id,
                    transformation_id=transform.id,
                    quantity=explicit_loss,
                    unit="g",
                    loss_type="extraction_process_loss",
                    measurement_basis="actual",
                    reason="Explicit stage loss reconciled at Extraction closeout",
                )
            )
        else:
            existing.quantity = explicit_loss
            existing.unit = "g"
            existing.measurement_basis = "actual"
            existing.reason = "Explicit stage loss reconciled at Extraction closeout"
    elif existing is not None:
        existing.quantity = 0.0
    transform.status = "committed"
    transform.actor = str(run.updated_by or run.created_by or "system")


def _canonical_create_output(
    self: ExtractionRepository,
    *,
    organization_id: str,
    facility_id: str,
    run_id: str,
    product_id: str,
    lot_code: str,
    quantity: float,
    actor: str,
    output_label: str = "",
    unit: str | None = None,
    compliance_package_id: str = "",
    location_code: str = "WIP-EXTRACTION",
    notes: str = "",
) -> ExtractionRunOutput:
    """Create either a released WIP handoff or a quarantined final output.

    Product Master ``item_type='wip'`` is the deterministic branch. WIP closes the
    current run as a reconciled handoff and can feed a downstream run. Finished
    outputs enter QA/quarantine and are closed only by the governed release path.
    """

    qty = float(quantity)
    if qty <= 0:
        raise ValueError("Extraction output quantity must be positive.")
    with self._session_factory.begin() as session:
        run = self._require_run(session, organization_id, facility_id, run_id)
        self._require_open_run(run)
        product = session.get(Product, product_id)
        if not product or product.organization_id != organization_id:
            raise ValueError("Output product was not found in the active organization.")
        output_unit = _clean(unit) or product.base_unit
        if output_unit.casefold() != product.base_unit.casefold():
            raise ValueError("Extraction output must use the product base unit.")
        if not _clean(lot_code):
            raise ValueError("Extraction output requires a durable lot code.")
        duplicate = session.scalar(
            select(InventoryLot.id).where(
                InventoryLot.facility_id == facility_id,
                func.lower(InventoryLot.lot_code) == _clean(lot_code).casefold(),
            )
        )
        if duplicate:
            raise ValueError("That Extraction output lot code already exists in this facility.")

        is_wip = str(product.item_type or "").casefold() == "wip"
        output_status = "released" if is_wip else "quarantine"
        lot_status = "available" if is_wip else "quarantine"
        destination = _clean(location_code).upper() or ("WIP-EXTRACTION" if is_wip else "QA-HOLD")
        lot = InventoryLot(
            organization_id=organization_id,
            facility_id=facility_id,
            product_id=product.id,
            lot_code=_clean(lot_code),
            compliance_package_id=_clean(compliance_package_id),
            location_code=destination,
            status=lot_status,
            received_at=utc_now(),
            notes=json.dumps(
                {
                    "source": "extraction",
                    "run_id": run.id,
                    "batch_number": run.batch_number,
                    "output_role": "intermediate_wip" if is_wip else "final_output",
                    "note": _clean(notes),
                },
                sort_keys=True,
            ),
        )
        session.add(lot)
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=organization_id,
                facility_id=facility_id,
                lot_id=lot.id,
                transaction_type="production_output",
                quantity_delta=qty,
                unit=output_unit,
                production_order_id=run.production_order_id,
                reason="Extraction WIP handoff" if is_wip else "Extraction final output",
                reference=f"extraction:{run.id}",
                actor=_clean(actor),
            )
        )
        position = int(
            session.scalar(
                select(func.coalesce(func.max(ExtractionRunOutput.position), 0)).where(
                    ExtractionRunOutput.run_id == run.id
                )
            )
            or 0
        ) + 1
        output = ExtractionRunOutput(
            organization_id=organization_id,
            facility_id=facility_id,
            run_id=run.id,
            product_id=product.id,
            lot_id=lot.id,
            position=position,
            output_label=_clean(output_label) or product.name,
            quantity=qty,
            unit=output_unit,
            status=output_status,
            coa_status="not_submitted",
            compliance_package_id=_clean(compliance_package_id),
            output_cost_usd=0.0,
            notes=_clean(notes),
            created_by=_clean(actor),
        )
        session.add(output)
        run.updated_by = _clean(actor)
        if is_wip:
            # WIP is a terminal handoff for this transformation. Any further
            # refinement/formulation consumes this lot in a downstream run.
            closeout = _require_closeout(session, run)
            run.status = "complete"
            run.release_status = "approved"
            run.current_stage_key = "handoff"
            run.completed_at = utc_now()
        else:
            run.current_stage_key = "qa"
            run.status = "qa"
            run.release_status = "pending"
            closeout = None
        session.flush()
        self._allocate_output_cogs(session, run.id)
        self._audit(
            session,
            organization_id,
            facility_id,
            "extraction_run_output",
            output.id,
            "wip_handoff_created" if is_wip else "created",
            actor,
            {
                "run_id": run.id,
                "lot_id": lot.id,
                "quantity": qty,
                "unit": output_unit,
                "output_role": "intermediate_wip" if is_wip else "final_output",
                "closeout": closeout,
            },
        )
        session.flush()
        return output


def _normalize_extraction_lot_status(session: Session, lot: InventoryLot) -> None:
    """Reservation is a claim, not a physical lot state."""

    history = inspect(lot).attrs.status.history
    if not history.has_changes() or str(lot.status or "").casefold() != "reserved":
        return
    previous = str(history.deleted[0] if history.deleted else "available").casefold()
    if previous not in {"available", "released", "reserved"}:
        return
    has_extraction_claim = False
    with session.no_autoflush:
        has_extraction_claim = bool(
            session.scalar(
                select(ExtractionRunInput.id).where(
                    ExtractionRunInput.lot_id == lot.id,
                    ExtractionRunInput.status.in_(tuple(INPUT_OPEN_STATUSES)),
                ).limit(1)
            )
        )
    if not has_extraction_claim:
        has_extraction_claim = any(
            isinstance(row, ExtractionRunInput)
            and row.lot_id == lot.id
            and row.status in INPUT_OPEN_STATUSES
            for row in session.new
        )
    if has_extraction_claim:
        lot.status = "available" if previous == "reserved" else previous


def _tag_output_purpose(session: Session, output: ExtractionRunOutput) -> None:
    if not output.lot_id:
        return
    product = _pending_or_persisted(session, Product, output.product_id)
    purpose = "extraction_intermediate" if product and str(product.item_type or "").casefold() == "wip" else "extraction_final"
    for row in session.new:
        if isinstance(row, MaterialTransformationOutput) and row.lot_id == output.lot_id:
            row.purpose = purpose
            row.measurement_basis = "actual"
            return
    with session.no_autoflush:
        row = session.scalar(
            select(MaterialTransformationOutput).where(MaterialTransformationOutput.lot_id == output.lot_id)
        )
    if row is not None:
        row.purpose = purpose
        row.measurement_basis = "actual"


def _before_flush(session: Session, _flush_context, _instances) -> None:
    for row in list(session.dirty):
        if isinstance(row, InventoryLot):
            _normalize_extraction_lot_status(session, row)

    for row in list(session.new):
        if isinstance(row, ExtractionRunOutput):
            _tag_output_purpose(session, row)

    for run in list(session.dirty):
        if not isinstance(run, ExtractionRun) or str(run.status or "").casefold() != "complete":
            continue
        history = inspect(run).attrs.status.history
        if not history.has_changes():
            continue
        closeout = _require_closeout(session, run)
        _commit_transformation(session, run, closeout)


def register_material_backbone() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    InventoryAvailabilityService.build = staticmethod(_availability_with_extraction)
    ExtractionRepository.create_output = _canonical_create_output
    event.listen(Session, "before_flush", _before_flush)
    _REGISTERED = True


register_material_backbone()
