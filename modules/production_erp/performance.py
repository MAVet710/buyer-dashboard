"""Bounded read models for latency-sensitive production surfaces.

These projections intentionally avoid the legacy per-order ``order_360`` fan-out.
They do not change source-of-truth records or workflow semantics; they only batch
reads that the React planning surfaces already require.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import (
    BomComponent,
    CrewAvailability,
    FacilityMachine,
    InventoryLot,
    InventoryTransaction,
    MachineModel,
    MaterialReservation,
    Product,
    ProductBom,
    ProductionActual,
    ProductionOrder,
)
from modules.production_erp.models import (
    ProductionBomStandard,
    ProductionCostEvent,
    ProductionQAEvent,
    ProductionRunEvent,
    ProductionRunOutput,
)


def _variance_pct(actual: float, standard: float) -> float | None:
    if standard <= 0:
        return None
    return (actual - standard) / standard * 100.0


def _group(rows: list[Any], key: str) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[str(getattr(row, key))].append(row)
    return grouped


def _orders(session: Session, organization_id: str, facility_id: str, *, active_only: bool, limit: int | None) -> list[ProductionOrder]:
    stmt = select(ProductionOrder).where(
        ProductionOrder.organization_id == organization_id,
        ProductionOrder.facility_id == facility_id,
    )
    if active_only:
        stmt = stmt.where(ProductionOrder.status.notin_(("complete", "cancelled")))
    stmt = stmt.order_by(ProductionOrder.due_at.asc().nullslast(), ProductionOrder.created_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def _read_model(
    session: Session,
    organization_id: str,
    facility_id: str,
    orders: list[ProductionOrder],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not orders:
        return [], []

    order_ids = [row.id for row in orders]
    products = list(session.scalars(select(Product).where(Product.organization_id == organization_id, Product.active.is_(True))))
    product_by_id = {row.id: row for row in products}
    product_by_sku = {row.sku.casefold(): row for row in products if row.sku}
    product_by_name = {row.name.casefold(): row for row in products if row.name}

    output_product_by_order: dict[str, Product] = {}
    for order in orders:
        product = product_by_sku.get(str(order.sku or "").casefold()) if order.sku else None
        product = product or product_by_name.get(str(order.product_name or "").casefold())
        if product is not None:
            output_product_by_order[order.id] = product

    output_product_ids = {row.id for row in output_product_by_order.values()}
    boms = list(
        session.scalars(
            select(ProductBom)
            .where(
                ProductBom.organization_id == organization_id,
                ProductBom.active.is_(True),
                ProductBom.output_product_id.in_(output_product_ids or {"__none__"}),
            )
            .order_by(ProductBom.output_product_id, ProductBom.version.desc())
        )
    )
    bom_by_product: dict[str, ProductBom] = {}
    for bom in boms:
        bom_by_product.setdefault(bom.output_product_id, bom)
    bom_ids = [row.id for row in bom_by_product.values()]

    standards = list(
        session.scalars(
            select(ProductionBomStandard).where(
                ProductionBomStandard.organization_id == organization_id,
                ProductionBomStandard.bom_id.in_(bom_ids or {"__none__"}),
            )
        )
    )
    standard_by_bom = {row.bom_id: row for row in standards}
    components = list(session.scalars(select(BomComponent).where(BomComponent.bom_id.in_(bom_ids or {"__none__"}))))
    components_by_bom = _group(components, "bom_id")

    actuals = list(session.scalars(select(ProductionActual).where(ProductionActual.production_order_id.in_(order_ids))))
    actual_by_order = {row.production_order_id: row for row in actuals}
    outputs_by_order = _group(
        list(session.scalars(select(ProductionRunOutput).where(ProductionRunOutput.production_order_id.in_(order_ids)))),
        "production_order_id",
    )
    costs_by_order = _group(
        list(session.scalars(select(ProductionCostEvent).where(ProductionCostEvent.production_order_id.in_(order_ids)))),
        "production_order_id",
    )
    qa_by_order = _group(
        list(session.scalars(select(ProductionQAEvent).where(ProductionQAEvent.production_order_id.in_(order_ids)))),
        "production_order_id",
    )
    events_by_order = _group(
        list(session.scalars(select(ProductionRunEvent).where(ProductionRunEvent.production_order_id.in_(order_ids)))),
        "production_order_id",
    )
    reservations_by_order = _group(
        list(session.scalars(select(MaterialReservation).where(MaterialReservation.production_order_id.in_(order_ids)))),
        "production_order_id",
    )

    queue: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for order in orders:
        output_product = output_product_by_order.get(order.id)
        bom = bom_by_product.get(output_product.id) if output_product else None
        standard = standard_by_bom.get(bom.id) if bom else None
        scale = float(order.requested_units or 0) / float(bom.output_quantity or 1) if bom else 1.0

        requirements: list[dict[str, Any]] = []
        for component in components_by_bom.get(bom.id if bom else "", []):
            input_product = product_by_id.get(component.input_product_id)
            requirements.append(
                {
                    "product_id": component.input_product_id,
                    "product_name": input_product.name if input_product else component.input_product_id,
                    "quantity": float(component.quantity or 0) * scale * (1 + float(component.scrap_pct or 0) / 100.0),
                    "unit": component.unit,
                    "scrap_pct": float(component.scrap_pct or 0),
                }
            )

        outputs = outputs_by_order.get(order.id, [])
        actual = actual_by_order.get(order.id)
        planned_output = sum(float(row.planned_quantity or 0) for row in outputs) or float(order.requested_units or 0)
        actual_output = sum(float(row.actual_quantity or 0) for row in outputs) or float(getattr(actual, "actual_units", 0) or 0)
        attainment = actual_output / planned_output * 100 if planned_output > 0 else 0.0
        cogs = sum(float(row.amount_usd or 0) for row in costs_by_order.get(order.id, []))

        qa_events = qa_by_order.get(order.id, [])
        qa_blocked = any(row.event_type in {"hold", "fail"} and row.result != "passed" for row in qa_events)
        qa_passed = any(row.result == "passed" for row in qa_events)
        expected_labor = float(standard.standard_labor_hours or 0) * scale if standard else 0.0
        expected_machine = float(standard.standard_machine_hours or 0) * scale if standard else 0.0
        expected_cycle = float(standard.standard_cycle_hours or 0) * scale if standard else 0.0

        events = events_by_order.get(order.id, [])
        event_labor = sum(float(row.labor_hours or 0) for row in events)
        actual_labor = event_labor if event_labor > 0 else float(getattr(actual, "actual_labor_hours", 0) or 0)
        labor_variance_pct = _variance_pct(actual_labor, expected_labor)
        output_variance_pct = _variance_pct(actual_output, planned_output)
        standard_attention = ""
        if standard is not None:
            if labor_variance_pct is not None and labor_variance_pct > 20:
                standard_attention = "Labor above standard"
            elif output_variance_pct is not None and output_variance_pct < -10:
                standard_attention = "Output below standard"

        reservations = reservations_by_order.get(order.id, [])
        queue.append(
            {
                "order_id": order.id,
                "Order": order.order_number,
                "Product": order.product_name,
                "Status": order.status.replace("_", " ").title(),
                "Planned": order.requested_units,
                "Actual": actual_output,
                "Attainment %": attainment,
                "COGS": cogs,
                "Cost / Unit": cogs / actual_output if actual_output > 0 else 0.0,
                "Reservations": len(reservations),
                "QA": "HOLD" if qa_blocked else "Ready",
                "Attention": "QA HOLD"
                if qa_blocked
                else ("Material shortage" if requirements and not reservations else (standard_attention or "Normal")),
            }
        )
        details.append(
            {
                "order": {
                    "id": order.id,
                    "order_number": order.order_number,
                    "product_name": order.product_name,
                    "requested_units": order.requested_units,
                    "priority": order.priority,
                    "status": order.status,
                    "due_at": order.due_at,
                },
                "standard": None
                if standard is None
                else {
                    "resource_category": standard.resource_category,
                    "qa_required": bool(standard.qa_required),
                    "compliance_checkpoint": standard.compliance_checkpoint,
                },
                "variance": {
                    "expected_labor_hours": expected_labor,
                    "expected_machine_hours": expected_machine,
                    "expected_cycle_hours": expected_cycle,
                    "resource_category": standard.resource_category if standard else "",
                    "qa_required": bool(standard.qa_required) if standard else False,
                    "qa_ready": (not bool(standard.qa_required)) or qa_passed if standard else True,
                    "compliance_checkpoint": standard.compliance_checkpoint if standard else "",
                    "standard_configured": standard is not None,
                },
                "requirements": requirements,
            }
        )
    return queue, details


def queue_summary_fast(engine: Engine, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
    """Return the legacy queue shape with a bounded number of SQL round trips."""
    with Session(engine) as session:
        orders = _orders(session, organization_id, facility_id, active_only=False, limit=None)
        queue, _ = _read_model(session, organization_id, facility_id, orders)
        return queue


def planning_snapshot(engine: Engine, organization_id: str, facility_id: str, *, limit: int = 40) -> dict[str, Any]:
    """One-request read model for the decision-first Production Planning view."""
    with Session(engine) as session:
        orders = _orders(session, organization_id, facility_id, active_only=True, limit=limit)
        queue, details = _read_model(session, organization_id, facility_id, orders)

        machines = list(
            session.scalars(
                select(FacilityMachine).where(
                    FacilityMachine.organization_id == organization_id,
                    FacilityMachine.facility_id == facility_id,
                    FacilityMachine.active.is_(True),
                )
            )
        )
        model_ids = {row.machine_model_id for row in machines}
        machine_models = list(
            session.scalars(
                select(MachineModel).where(
                    MachineModel.id.in_(model_ids or {"__none__"}),
                    MachineModel.active.is_(True),
                )
            )
        )
        crew = list(
            session.scalars(
                select(CrewAvailability).where(
                    CrewAvailability.organization_id == organization_id,
                    CrewAvailability.facility_id == facility_id,
                    CrewAvailability.work_date == date.today(),
                )
            )
        )

        balance = (
            select(
                InventoryTransaction.lot_id.label("lot_id"),
                func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0).label("balance"),
            )
            .where(
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.facility_id == facility_id,
            )
            .group_by(InventoryTransaction.lot_id)
            .subquery()
        )
        lot_rows = session.execute(
            select(InventoryLot, func.coalesce(balance.c.balance, 0.0))
            .outerjoin(balance, balance.c.lot_id == InventoryLot.id)
            .where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
                InventoryLot.status.in_(("available", "released")),
                func.coalesce(balance.c.balance, 0.0) > 0,
            )
        ).all()
        reservations = list(
            session.scalars(
                select(MaterialReservation).where(
                    MaterialReservation.organization_id == organization_id,
                    MaterialReservation.facility_id == facility_id,
                    MaterialReservation.status == "reserved",
                )
            )
        )

        return {
            "workspace": {
                "machines": [
                    {"id": row.id, "machine_model_id": row.machine_model_id, "display_name": row.display_name}
                    for row in machines
                ],
                "machine_models": [
                    {"id": row.id, "category": row.category, "manufacturer": row.manufacturer, "model": row.model}
                    for row in machine_models
                ],
                "crew": [
                    {
                        "id": row.id,
                        "work_date": row.work_date,
                        "shift_name": row.shift_name,
                        "available_people": row.available_people,
                        "shift_hours": row.shift_hours,
                    }
                    for row in crew
                ],
                "lots": [
                    {"id": lot.id, "product_id": lot.product_id, "status": lot.status, "on_hand": float(on_hand or 0)}
                    for lot, on_hand in lot_rows
                ],
                "reservations": [
                    {
                        "id": row.id,
                        "production_order_id": row.production_order_id,
                        "lot_id": row.lot_id,
                        "quantity": row.quantity,
                        "unit": row.unit,
                        "status": row.status,
                    }
                    for row in reservations
                ],
            },
            "queue": queue,
            "details": details,
        }
