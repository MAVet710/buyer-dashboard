"""Bounded read model for the legacy Co-Man Production Ops workspace.

The operator-facing implementation remains in ``coman_parity_legacy`` so all
existing controls, write routes, report/export behavior, permissions, and audit
semantics stay intact.  This module replaces only the heavy workspace GET with
section-aware, bounded projections used by the React wrapper.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Depends
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from modules.coman.models import (
    CrewAvailability,
    Customer,
    FacilityMachine,
    InventoryLot,
    InventoryTransaction,
    MachineModel,
    MaterialReservation,
    Product,
    ProductionActual,
    ProductionOrder,
)
from ..auth import RequestContext, get_request_context
from ..database import get_engine
from . import coman_parity_legacy as legacy


router = legacy.router

# Preserve every existing legacy route except the unbounded workspace GET.
router.routes[:] = [
    route
    for route in router.routes
    if not (
        getattr(route, "path", None) == "/coman-parity/workspace"
        and "GET" in (getattr(route, "methods", set()) or set())
    )
]

ORDER_LIMIT = 200
CUSTOMER_LIMIT = 250
PRODUCT_LIMIT = 250
LOT_LIMIT = 250
TRANSACTION_LIMIT = 250
RESERVATION_LIMIT = 250
ACTUAL_LIMIT = 200
CREW_LIMIT = 250
MACHINE_LIMIT = 250
MACHINE_MODEL_LIMIT = 250

_COLLECTIONS = (
    "orders",
    "customers",
    "machine_models",
    "machines",
    "products",
    "lots",
    "transactions",
    "reservations",
    "crew",
    "actuals",
)


def _window(*, loaded: bool, returned: int = 0, total: int | None = None, limit: int | None = None) -> dict[str, Any]:
    return {
        "loaded": bool(loaded),
        "returned": int(returned),
        "total": int(total) if total is not None else None,
        "limit": int(limit) if limit is not None else None,
        "truncated": bool(loaded and total is not None and returned < total),
    }


def _global_stats(engine: Engine, organization_id: str, facility_id: str) -> dict[str, int]:
    order_scope = (
        ProductionOrder.organization_id == organization_id,
        ProductionOrder.facility_id == facility_id,
    )
    open_scope = order_scope + (
        ProductionOrder.status.not_in(("complete", "cancelled")),
    )
    with Session(engine) as session:
        row = session.execute(
            select(
                select(func.count(ProductionOrder.id)).where(*order_scope).scalar_subquery(),
                select(func.count(ProductionOrder.id)).where(*open_scope).scalar_subquery(),
                select(func.coalesce(func.sum(ProductionOrder.requested_units), 0)).where(*open_scope).scalar_subquery(),
                select(func.count(ProductionOrder.id)).where(*order_scope, ProductionOrder.work_type == "external").scalar_subquery(),
                select(func.count(Customer.id)).where(Customer.organization_id == organization_id, Customer.active.is_(True)).scalar_subquery(),
                select(func.count(FacilityMachine.id)).where(
                    FacilityMachine.organization_id == organization_id,
                    FacilityMachine.facility_id == facility_id,
                    FacilityMachine.active.is_(True),
                ).scalar_subquery(),
            )
        ).one()
    return {
        "orders": int(row[0] or 0),
        "open_orders": int(row[1] or 0),
        "units_planned": int(row[2] or 0),
        "external_jobs": int(row[3] or 0),
        "customers": int(row[4] or 0),
        "machines": int(row[5] or 0),
    }


def _orders(engine: Engine, organization_id: str, facility_id: str) -> list[ProductionOrder]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(ProductionOrder)
                .where(
                    ProductionOrder.organization_id == organization_id,
                    ProductionOrder.facility_id == facility_id,
                )
                .order_by(ProductionOrder.created_at.desc())
                .limit(ORDER_LIMIT)
            )
        )


def _customers_for_orders(engine: Engine, organization_id: str, orders: list[ProductionOrder]) -> list[Customer]:
    ids = sorted({row.customer_id for row in orders if row.customer_id})
    if not ids:
        return []
    with Session(engine) as session:
        return list(
            session.scalars(
                select(Customer)
                .where(Customer.organization_id == organization_id, Customer.id.in_(ids))
                .order_by(Customer.name)
            )
        )


def _customers(engine: Engine, organization_id: str) -> list[Customer]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(Customer)
                .where(Customer.organization_id == organization_id, Customer.active.is_(True))
                .order_by(Customer.name)
                .limit(CUSTOMER_LIMIT)
            )
        )


def _products(engine: Engine, organization_id: str) -> tuple[list[Product], int]:
    with Session(engine) as session:
        total = int(
            session.scalar(
                select(func.count(Product.id)).where(
                    Product.organization_id == organization_id,
                    Product.active.is_(True),
                )
            )
            or 0
        )
        rows = list(
            session.scalars(
                select(Product)
                .where(Product.organization_id == organization_id, Product.active.is_(True))
                .order_by(Product.name)
                .limit(PRODUCT_LIMIT)
            )
        )
    return rows, total


def _lots(engine: Engine, organization_id: str, facility_id: str) -> tuple[list[tuple[InventoryLot, float]], int]:
    balances = (
        select(
            InventoryTransaction.lot_id.label("lot_id"),
            func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0).label("balance"),
        )
        .where(
            InventoryTransaction.organization_id == organization_id,
            InventoryTransaction.facility_id == facility_id,
        )
        .group_by(InventoryTransaction.lot_id)
        .cte("visible_lot_balances")
    )
    with Session(engine) as session:
        total = int(
            session.scalar(
                select(func.count(InventoryLot.id)).where(
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                )
            )
            or 0
        )
        rows = session.execute(
            select(InventoryLot, func.coalesce(balances.c.balance, 0.0))
            .outerjoin(balances, balances.c.lot_id == InventoryLot.id)
            .where(
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
            )
            .order_by(InventoryLot.received_at.desc(), InventoryLot.lot_code)
            .limit(LOT_LIMIT)
        ).all()
    return [(row, float(balance or 0.0)) for row, balance in rows], total


def _transactions(engine: Engine, organization_id: str, facility_id: str) -> tuple[list[InventoryTransaction], int]:
    with Session(engine) as session:
        total = int(
            session.scalar(
                select(func.count(InventoryTransaction.id)).where(
                    InventoryTransaction.organization_id == organization_id,
                    InventoryTransaction.facility_id == facility_id,
                )
            )
            or 0
        )
        rows = list(
            session.scalars(
                select(InventoryTransaction)
                .where(
                    InventoryTransaction.organization_id == organization_id,
                    InventoryTransaction.facility_id == facility_id,
                )
                .order_by(InventoryTransaction.occurred_at.desc())
                .limit(TRANSACTION_LIMIT)
            )
        )
    return rows, total


def _reservations(engine: Engine, organization_id: str, facility_id: str) -> tuple[list[MaterialReservation], int]:
    with Session(engine) as session:
        total = int(
            session.scalar(
                select(func.count(MaterialReservation.id)).where(
                    MaterialReservation.organization_id == organization_id,
                    MaterialReservation.facility_id == facility_id,
                )
            )
            or 0
        )
        rows = list(
            session.scalars(
                select(MaterialReservation)
                .where(
                    MaterialReservation.organization_id == organization_id,
                    MaterialReservation.facility_id == facility_id,
                )
                .order_by(MaterialReservation.created_at.desc())
                .limit(RESERVATION_LIMIT)
            )
        )
    return rows, total


def _actuals(engine: Engine, organization_id: str, facility_id: str) -> tuple[list[ProductionActual], int]:
    with Session(engine) as session:
        total = int(
            session.scalar(
                select(func.count(ProductionActual.id)).where(
                    ProductionActual.organization_id == organization_id,
                    ProductionActual.facility_id == facility_id,
                )
            )
            or 0
        )
        rows = list(
            session.scalars(
                select(ProductionActual)
                .where(
                    ProductionActual.organization_id == organization_id,
                    ProductionActual.facility_id == facility_id,
                )
                .order_by(ProductionActual.completed_at.desc())
                .limit(ACTUAL_LIMIT)
            )
        )
    return rows, total


def _crew(engine: Engine, organization_id: str, facility_id: str) -> tuple[list[CrewAvailability], int]:
    today = date.today()
    with Session(engine) as session:
        total = int(
            session.scalar(
                select(func.count(CrewAvailability.id)).where(
                    CrewAvailability.organization_id == organization_id,
                    CrewAvailability.facility_id == facility_id,
                    CrewAvailability.work_date >= today,
                )
            )
            or 0
        )
        rows = list(
            session.scalars(
                select(CrewAvailability)
                .where(
                    CrewAvailability.organization_id == organization_id,
                    CrewAvailability.facility_id == facility_id,
                    CrewAvailability.work_date >= today,
                )
                .order_by(CrewAvailability.work_date, CrewAvailability.shift_name)
                .limit(CREW_LIMIT)
            )
        )
    return rows, total


def _machines(engine: Engine, organization_id: str, facility_id: str) -> list[FacilityMachine]:
    with Session(engine) as session:
        return list(
            session.scalars(
                select(FacilityMachine)
                .where(
                    FacilityMachine.organization_id == organization_id,
                    FacilityMachine.facility_id == facility_id,
                    FacilityMachine.active.is_(True),
                )
                .order_by(FacilityMachine.display_name)
                .limit(MACHINE_LIMIT)
            )
        )


def _machine_models(engine: Engine) -> tuple[list[MachineModel], int]:
    with Session(engine) as session:
        total = int(session.scalar(select(func.count(MachineModel.id)).where(MachineModel.active.is_(True))) or 0)
        rows = list(
            session.scalars(
                select(MachineModel)
                .where(MachineModel.active.is_(True))
                .order_by(MachineModel.manufacturer, MachineModel.model)
                .limit(MACHINE_MODEL_LIMIT)
            )
        )
    return rows, total


def _empty_windows() -> dict[str, dict[str, Any]]:
    return {name: _window(loaded=False) for name in _COLLECTIONS}


@router.get("/workspace")
def workspace(
    section: str = "dashboard",
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    section = str(section or "dashboard").strip().lower().replace("_", "-")
    allowed = {"dashboard", "new-job", "schedule", "resources", "inventory", "customers", "performance", "control"}
    if section not in allowed:
        section = "dashboard"

    stats = _global_stats(engine, context.organization_id, context.facility_id)
    hand = legacy._repo(engine).ensure_primary_hand_labor_area(context.organization_id, context.facility_id)
    orders = _orders(engine, context.organization_id, context.facility_id)
    windows = _empty_windows()
    windows["orders"] = _window(loaded=True, returned=len(orders), total=stats["orders"], limit=ORDER_LIMIT)

    customers: list[Customer] = []
    machine_models: list[MachineModel] = []
    machines: list[FacilityMachine] = []
    products: list[Product] = []
    lots: list[tuple[InventoryLot, float]] = []
    transactions: list[InventoryTransaction] = []
    reservations: list[MaterialReservation] = []
    crew: list[CrewAvailability] = []
    actuals: list[ProductionActual] = []

    if section == "dashboard":
        # Only the customer names referenced by the visible order window are needed
        # for the queue. This is a lookup, not the full customer collection.
        customers = _customers_for_orders(engine, context.organization_id, orders)
        windows["customers"] = _window(loaded=False, returned=len(customers))
    elif section in {"new-job", "customers"}:
        customers = _customers(engine, context.organization_id)
        windows["customers"] = _window(loaded=True, returned=len(customers), total=stats["customers"], limit=CUSTOMER_LIMIT)
    elif section == "schedule":
        machines = _machines(engine, context.organization_id, context.facility_id)
        crew, crew_total = _crew(engine, context.organization_id, context.facility_id)
        windows["machines"] = _window(loaded=True, returned=len(machines), total=stats["machines"], limit=MACHINE_LIMIT)
        windows["crew"] = _window(loaded=True, returned=len(crew), total=crew_total, limit=CREW_LIMIT)
    elif section == "resources":
        machine_models, model_total = _machine_models(engine)
        machines = _machines(engine, context.organization_id, context.facility_id)
        windows["machine_models"] = _window(loaded=True, returned=len(machine_models), total=model_total, limit=MACHINE_MODEL_LIMIT)
        windows["machines"] = _window(loaded=True, returned=len(machines), total=stats["machines"], limit=MACHINE_LIMIT)
    elif section == "inventory":
        products, product_total = _products(engine, context.organization_id)
        lots, lot_total = _lots(engine, context.organization_id, context.facility_id)
        transactions, transaction_total = _transactions(engine, context.organization_id, context.facility_id)
        reservations, reservation_total = _reservations(engine, context.organization_id, context.facility_id)
        windows["products"] = _window(loaded=True, returned=len(products), total=product_total, limit=PRODUCT_LIMIT)
        windows["lots"] = _window(loaded=True, returned=len(lots), total=lot_total, limit=LOT_LIMIT)
        windows["transactions"] = _window(loaded=True, returned=len(transactions), total=transaction_total, limit=TRANSACTION_LIMIT)
        windows["reservations"] = _window(loaded=True, returned=len(reservations), total=reservation_total, limit=RESERVATION_LIMIT)
    elif section == "performance":
        actuals, actual_total = _actuals(engine, context.organization_id, context.facility_id)
        windows["actuals"] = _window(loaded=True, returned=len(actuals), total=actual_total, limit=ACTUAL_LIMIT)
    elif section == "control":
        products, product_total = _products(engine, context.organization_id)
        windows["products"] = _window(loaded=True, returned=len(products), total=product_total, limit=PRODUCT_LIMIT)

    return {
        "metrics": {
            "open_orders": stats["open_orders"],
            "units_planned": stats["units_planned"],
            "external_jobs": stats["external_jobs"],
            "customers": stats["customers"],
        },
        "readiness": [
            {"Requirement": "Facility selected", "Status": "Ready"},
            {
                "Requirement": "Hand-labor rates",
                "Status": "Ready"
                if all(
                    (
                        hand.sticker_units_per_person_hour > 0,
                        hand.case_pack_units_per_person_hour > 0,
                        hand.final_cases_per_person_hour > 0,
                    )
                )
                else "Needs setup",
            },
            {"Requirement": "Facility machine", "Status": "Ready" if stats["machines"] else "Needs setup"},
            {"Requirement": "Production queue", "Status": "Ready" if stats["orders"] else "No jobs yet"},
        ],
        "orders": [legacy._order(row) for row in orders],
        "customers": [
            {
                "id": row.id,
                "name": row.name,
                "license_or_registration": row.license_or_registration,
                "contact_name": row.contact_name,
                "contact_email": row.contact_email,
            }
            for row in customers
        ],
        "machine_models": [
            {
                "id": row.id,
                "manufacturer": row.manufacturer,
                "model": row.model,
                "category": row.category,
                "published_max_rate": row.published_max_rate,
                "rate_unit": row.rate_unit,
                "planning_utilization_pct": row.planning_utilization_pct,
                "published_min_operators": row.published_min_operators,
                "source_url": row.source_url,
            }
            for row in machine_models
        ],
        "machines": [
            {
                "id": row.id,
                "machine_model_id": row.machine_model_id,
                "asset_code": row.asset_code,
                "display_name": row.display_name,
                "effective_rate": row.effective_rate,
                "rate_unit": row.rate_unit,
                "preferred_crew_size": row.preferred_crew_size,
                "setup_minutes": row.setup_minutes,
                "cleanup_minutes": row.cleanup_minutes,
            }
            for row in machines
        ],
        "hand_labor": {
            "id": hand.id,
            "default_crew_size": hand.default_crew_size,
            "sticker_units_per_person_hour": hand.sticker_units_per_person_hour,
            "case_pack_units_per_person_hour": hand.case_pack_units_per_person_hour,
            "final_cases_per_person_hour": hand.final_cases_per_person_hour,
            "setup_minutes": hand.setup_minutes,
            "cleanup_minutes": hand.cleanup_minutes,
        },
        "products": [
            {
                "id": row.id,
                "sku": row.sku,
                "name": row.name,
                "item_type": row.item_type,
                "base_unit": row.base_unit,
                "unit_cost": row.unit_cost,
            }
            for row in products
        ],
        "lots": [
            {
                "id": row.id,
                "product_id": row.product_id,
                "lot_code": row.lot_code,
                "compliance_package_id": row.compliance_package_id,
                "location_code": row.location_code,
                "status": row.status,
                "on_hand": balance,
            }
            for row, balance in lots
        ],
        "transactions": [
            {
                "id": row.id,
                "occurred_at": row.occurred_at,
                "lot_id": row.lot_id,
                "transaction_type": row.transaction_type,
                "quantity_delta": row.quantity_delta,
                "unit": row.unit,
                "reason": row.reason,
                "reference": row.reference,
                "actor": row.actor,
            }
            for row in transactions
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
        "crew": [
            {
                "id": row.id,
                "work_date": row.work_date,
                "shift_name": row.shift_name,
                "available_people": row.available_people,
                "shift_hours": row.shift_hours,
                "notes": row.notes,
            }
            for row in crew
        ],
        "actuals": [
            {
                "id": row.id,
                "production_order_id": row.production_order_id,
                "actual_units": row.actual_units,
                "scrap_units": row.scrap_units,
                "rework_units": row.rework_units,
                "actual_machine_hours": row.actual_machine_hours,
                "actual_labor_hours": row.actual_labor_hours,
                "completed_at": row.completed_at,
                "notes": row.notes,
            }
            for row in actuals
        ],
        "windows": windows,
        "section": section,
    }
