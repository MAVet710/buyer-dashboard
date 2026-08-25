from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import (
    CommercialOrder,
    CommercialOrderLine,
    InventoryAudit,
    InventoryAuditLine,
    InventoryLot,
    InventoryTransaction,
    OrderLotAllocation,
    Product,
)
from modules.package_studio.models import PackageStudioInput, PackageStudioOutput, PackageStudioRun
from modules.traceability.models import TraceabilityTransaction
from ..auth import RequestContext, get_request_context
from ..database import get_engine

router = APIRouter(prefix="/package-360", tags=["package-360"])


def _event(*, occurred_at: datetime | None, area: str, event_type: str, title: str, detail: str = "", actor: str = "", reference: str = "", status: str = "", quantity: float | None = None, unit: str = "") -> dict[str, Any]:
    return {
        "occurred_at": occurred_at,
        "area": area,
        "event_type": event_type,
        "title": title,
        "detail": detail,
        "actor": actor,
        "reference": reference,
        "status": status,
        "quantity": quantity,
        "unit": unit,
    }


def _sort_timestamp(value: datetime | None) -> float:
    """Treat SQLite's timezone-naive persisted timestamps as UTC for stable ordering."""
    if value is None:
        return float("-inf")
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return normalized.timestamp()


def _snapshot(lot: InventoryLot, context: RequestContext, engine: Engine) -> dict[str, Any]:
    with Session(engine) as session:
        product = session.get(Product, lot.product_id)
        if not product or product.organization_id != context.organization_id:
            raise HTTPException(404, "Package product was not found in the active organization.")

        transactions = list(session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.organization_id == context.organization_id,
                InventoryTransaction.facility_id == context.facility_id,
                InventoryTransaction.lot_id == lot.id,
            ).order_by(InventoryTransaction.occurred_at)
        ))
        balance = sum(float(row.quantity_delta or 0) for row in transactions)

        studio_inputs = list(session.execute(
            select(PackageStudioInput, PackageStudioRun)
            .join(PackageStudioRun, PackageStudioRun.id == PackageStudioInput.run_id)
            .where(
                PackageStudioInput.organization_id == context.organization_id,
                PackageStudioInput.facility_id == context.facility_id,
                PackageStudioInput.lot_id == lot.id,
            )
        ))
        studio_outputs = list(session.execute(
            select(PackageStudioOutput, PackageStudioRun)
            .join(PackageStudioRun, PackageStudioRun.id == PackageStudioOutput.run_id)
            .where(
                PackageStudioOutput.organization_id == context.organization_id,
                PackageStudioOutput.facility_id == context.facility_id,
                PackageStudioOutput.lot_id == lot.id,
            )
        ))
        related_run_ids = {run.id for _, run in studio_inputs} | {run.id for _, run in studio_outputs}
        lineage_inputs: list[dict[str, Any]] = []
        lineage_outputs: list[dict[str, Any]] = []
        if related_run_ids:
            input_rows = list(session.execute(
                select(PackageStudioInput, InventoryLot, Product)
                .join(InventoryLot, InventoryLot.id == PackageStudioInput.lot_id)
                .join(Product, Product.id == InventoryLot.product_id)
                .where(
                    PackageStudioInput.organization_id == context.organization_id,
                    PackageStudioInput.facility_id == context.facility_id,
                    PackageStudioInput.run_id.in_(related_run_ids),
                )
            ))
            output_rows = list(session.execute(
                select(PackageStudioOutput, Product)
                .join(Product, Product.id == PackageStudioOutput.product_id)
                .where(
                    PackageStudioOutput.organization_id == context.organization_id,
                    PackageStudioOutput.facility_id == context.facility_id,
                    PackageStudioOutput.run_id.in_(related_run_ids),
                )
            ))
            lineage_inputs = [
                {"run_id": row.run_id, "lot_id": source.id, "lot_code": source.lot_code, "package_id": source.compliance_package_id, "product_name": source_product.name, "quantity": float(row.quantity), "unit": row.unit, "purpose": row.purpose}
                for row, source, source_product in input_rows
            ]
            lineage_outputs = [
                {"run_id": row.run_id, "lot_id": row.lot_id, "lot_code": row.lot_code, "package_id": row.compliance_package_id, "product_name": output_product.name, "quantity": float(row.inventory_quantity), "unit": row.inventory_unit, "purpose": row.purpose}
                for row, output_product in output_rows
            ]

        audit_rows = list(session.execute(
            select(InventoryAuditLine, InventoryAudit)
            .join(InventoryAudit, InventoryAudit.id == InventoryAuditLine.audit_id)
            .where(
                InventoryAuditLine.organization_id == context.organization_id,
                InventoryAuditLine.facility_id == context.facility_id,
                InventoryAuditLine.lot_id == lot.id,
            )
            .order_by(InventoryAudit.started_at)
        ))

        allocation_rows = list(session.execute(
            select(OrderLotAllocation, CommercialOrderLine, CommercialOrder)
            .join(CommercialOrderLine, CommercialOrderLine.id == OrderLotAllocation.commercial_order_line_id)
            .join(CommercialOrder, CommercialOrder.id == OrderLotAllocation.commercial_order_id)
            .where(
                OrderLotAllocation.organization_id == context.organization_id,
                OrderLotAllocation.facility_id == context.facility_id,
                OrderLotAllocation.lot_id == lot.id,
            )
            .order_by(OrderLotAllocation.created_at)
        ))

        identifiers = {lot.id, lot.lot_code}
        if lot.compliance_package_id:
            identifiers.add(lot.compliance_package_id)
        trace_rows = list(session.scalars(
            select(TraceabilityTransaction).where(
                TraceabilityTransaction.organization_id == context.organization_id,
                TraceabilityTransaction.facility_id == context.facility_id,
                TraceabilityTransaction.entity_id.in_(identifiers),
            ).order_by(TraceabilityTransaction.requested_at)
        ))

    events: list[dict[str, Any]] = []
    if lot.received_at:
        events.append(_event(occurred_at=lot.received_at, area="Inventory", event_type="received", title="Package entered facility inventory", detail=lot.location_code, reference=lot.compliance_package_id or lot.lot_code, status=lot.status))
    for row in transactions:
        events.append(_event(occurred_at=row.occurred_at, area="Inventory", event_type=row.transaction_type, title=row.transaction_type.replace("_", " ").title(), detail=row.reason, actor=row.actor, reference=row.reference, quantity=float(row.quantity_delta), unit=row.unit))
    for input_row, run in studio_inputs:
        events.append(_event(occurred_at=run.committed_at or run.created_at, area="Package Studio", event_type="input", title=f"Used in {run.action_type.replace('_', ' ')}", detail=f"Run {run.run_number} · {input_row.purpose}", actor=run.completed_by or run.created_by, reference=run.run_number, status=run.status, quantity=-float(input_row.quantity), unit=input_row.unit))
    for output_row, run in studio_outputs:
        events.append(_event(occurred_at=run.committed_at or run.created_at, area="Package Studio", event_type="output", title=f"Created by {run.action_type.replace('_', ' ')}", detail=f"Run {run.run_number} · {output_row.purpose}", actor=run.completed_by or run.created_by, reference=run.run_number, status=run.status, quantity=float(output_row.inventory_quantity), unit=output_row.inventory_unit))
    for line, audit in audit_rows:
        final_count = line.counted_quantity if line.counted_quantity is not None else line.recount_quantity if line.recount_quantity is not None else line.first_count_quantity
        events.append(_event(occurred_at=line.counted_at or audit.started_at, area="Audit", event_type="physical_count", title=f"Inventory audit {audit.audit_number}", detail=f"Expected {line.expected_quantity:g}; counted {final_count if final_count is not None else 'pending'}; variance {line.variance_quantity:g}", actor=line.counted_by or audit.created_by, reference=audit.audit_number, status=audit.status, quantity=float(line.variance_quantity), unit=line.unit))
    for allocation, line, order in allocation_rows:
        events.append(_event(occurred_at=allocation.created_at, area="Orders", event_type="allocation", title=f"Allocated to {order.order_number}", detail=f"{line.description} · {allocation.fulfilled_quantity:g}/{allocation.quantity:g} fulfilled", actor=allocation.reserved_by, reference=order.order_number, status=allocation.status, quantity=-float(allocation.quantity), unit=line.unit))
    for tx in trace_rows:
        events.append(_event(occurred_at=tx.requested_at, area="Traceability", event_type=tx.operation_type, title=f"{tx.provider.upper()} · {tx.operation_type.replace('_', ' ')}", detail=tx.reason or tx.error_message, actor=tx.requested_by, reference=tx.external_reference or tx.id, status=tx.status))

    events.sort(key=lambda row: _sort_timestamp(row["occurred_at"]), reverse=True)
    return {
        "package": {
            "id": lot.id,
            "lot_code": lot.lot_code,
            "package_id": lot.compliance_package_id,
            "location": lot.location_code,
            "status": lot.status,
            "received_at": lot.received_at,
            "expiration_at": lot.expiration_at,
            "balance": balance,
            "unit": product.base_unit,
        },
        "product": {"id": product.id, "sku": product.sku, "name": product.name, "item_type": product.item_type},
        "lineage": {"inputs": lineage_inputs, "outputs": lineage_outputs, "run_count": len(related_run_ids)},
        "summary": {
            "inventory_events": len(transactions),
            "package_studio_runs": len(related_run_ids),
            "audits": len(audit_rows),
            "order_allocations": len(allocation_rows),
            "traceability_actions": len(trace_rows),
        },
        "timeline": events,
    }


@router.get("/resolve")
def resolve_package(
    code: str = Query(min_length=1, max_length=512),
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    needle = code.strip()
    with Session(engine) as session:
        lot = session.scalar(
            select(InventoryLot).where(
                InventoryLot.organization_id == context.organization_id,
                InventoryLot.facility_id == context.facility_id,
                or_(
                    func.lower(InventoryLot.id) == needle.casefold(),
                    func.lower(InventoryLot.lot_code) == needle.casefold(),
                    func.lower(InventoryLot.compliance_package_id) == needle.casefold(),
                    func.lower(InventoryLot.barcode_value) == needle.casefold(),
                ),
            ).limit(1)
        )
        if not lot:
            raise HTTPException(404, "No package or lot matched that identifier in the active facility.")
        session.expunge(lot)
    return _snapshot(lot, context, engine)


@router.get("/{lot_id}")
def package_360(
    lot_id: str,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    with Session(engine) as session:
        lot = session.get(InventoryLot, lot_id)
        if not lot or lot.organization_id != context.organization_id or lot.facility_id != context.facility_id:
            raise HTTPException(404, "Package or lot was not found in the active facility.")
        session.expunge(lot)
    return _snapshot(lot, context, engine)
