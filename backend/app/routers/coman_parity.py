"""Compatibility entrypoint for the bounded Production Ops read model.

Routine React reads use explicit section windows from ``coman_parity_bounded``.
The historical no-section API shape is retained only while the complete result
fits inside those same routine caps; once facility history exceeds a cap, the
no-section call automatically falls back to the bounded dashboard projection.
This keeps existing small-facility/API consumers compatible without creating an
unbounded growth path.
"""

from __future__ import annotations

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
from . import coman_parity_bounded as bounded
from . import coman_parity_legacy as legacy


router = bounded.router

ORDER_LIMIT = bounded.ORDER_LIMIT
CUSTOMER_LIMIT = bounded.CUSTOMER_LIMIT
PRODUCT_LIMIT = bounded.PRODUCT_LIMIT
LOT_LIMIT = bounded.LOT_LIMIT
TRANSACTION_LIMIT = bounded.TRANSACTION_LIMIT
RESERVATION_LIMIT = bounded.RESERVATION_LIMIT
ACTUAL_LIMIT = bounded.ACTUAL_LIMIT
CREW_LIMIT = bounded.CREW_LIMIT
MACHINE_LIMIT = bounded.MACHINE_LIMIT
MACHINE_MODEL_LIMIT = bounded.MACHINE_MODEL_LIMIT

# ``bounded`` registers its own workspace route when imported. Keep all of its
# legacy write/report routes, but replace the GET so omitted ``section`` can
# preserve the old small-dataset response without ever becoming unbounded.
router.routes[:] = [
    route
    for route in router.routes
    if not (
        getattr(route, "path", None) == "/coman-parity/workspace"
        and "GET" in (getattr(route, "methods", set()) or set())
    )
]


def _fits_legacy_window(engine: Engine, organization_id: str, facility_id: str) -> bool:
    """Return True only when the complete historical payload is already bounded."""
    with Session(engine) as session:
        counts = session.execute(
            select(
                select(func.count(ProductionOrder.id)).where(
                    ProductionOrder.organization_id == organization_id,
                    ProductionOrder.facility_id == facility_id,
                ).scalar_subquery(),
                select(func.count(Customer.id)).where(
                    Customer.organization_id == organization_id,
                    Customer.active.is_(True),
                ).scalar_subquery(),
                select(func.count(Product.id)).where(
                    Product.organization_id == organization_id,
                    Product.active.is_(True),
                ).scalar_subquery(),
                select(func.count(InventoryLot.id)).where(
                    InventoryLot.organization_id == organization_id,
                    InventoryLot.facility_id == facility_id,
                ).scalar_subquery(),
                select(func.count(InventoryTransaction.id)).where(
                    InventoryTransaction.organization_id == organization_id,
                    InventoryTransaction.facility_id == facility_id,
                ).scalar_subquery(),
                select(func.count(MaterialReservation.id)).where(
                    MaterialReservation.organization_id == organization_id,
                    MaterialReservation.facility_id == facility_id,
                ).scalar_subquery(),
                select(func.count(ProductionActual.id)).where(
                    ProductionActual.organization_id == organization_id,
                    ProductionActual.facility_id == facility_id,
                ).scalar_subquery(),
                select(func.count(CrewAvailability.id)).where(
                    CrewAvailability.organization_id == organization_id,
                    CrewAvailability.facility_id == facility_id,
                ).scalar_subquery(),
                select(func.count(FacilityMachine.id)).where(
                    FacilityMachine.organization_id == organization_id,
                    FacilityMachine.facility_id == facility_id,
                    FacilityMachine.active.is_(True),
                ).scalar_subquery(),
                select(func.count(MachineModel.id)).where(MachineModel.active.is_(True)).scalar_subquery(),
            )
        ).one()
    limits = (
        ORDER_LIMIT,
        CUSTOMER_LIMIT,
        PRODUCT_LIMIT,
        LOT_LIMIT,
        TRANSACTION_LIMIT,
        RESERVATION_LIMIT,
        ACTUAL_LIMIT,
        CREW_LIMIT,
        MACHINE_LIMIT,
        MACHINE_MODEL_LIMIT,
    )
    return all(int(count or 0) <= limit for count, limit in zip(counts, limits, strict=True))


@router.get("/workspace")
def workspace(
    section: str | None = None,
    context: RequestContext = Depends(get_request_context),
    engine: Engine = Depends(get_engine),
):
    if section is None:
        if _fits_legacy_window(engine, context.organization_id, context.facility_id):
            return legacy.workspace(context=context, engine=engine)
        section = "dashboard"
    return bounded.workspace(section=section, context=context, engine=engine)
