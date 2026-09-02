"""Bounded read model for the Production Calendar surface.

The calendar only needs production-order identity plus facility machine metadata.
Keep that projection separate from the legacy Co-Man workspace so opening the
calendar does not hydrate customers, inventory, transactions, crew, actuals, or
other unrelated production data.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import FacilityMachine, MachineModel, ProductionOrder


def production_calendar_workspace(engine: Engine, organization_id: str, facility_id: str) -> dict[str, Any]:
    """Return only the records required to render and operate Production Calendar."""
    with Session(engine) as session:
        orders = list(
            session.scalars(
                select(ProductionOrder)
                .where(
                    ProductionOrder.organization_id == organization_id,
                    ProductionOrder.facility_id == facility_id,
                )
                .order_by(ProductionOrder.due_at.asc().nullslast(), ProductionOrder.created_at.desc())
            )
        )
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

        return {
            "orders": [
                {
                    "id": row.id,
                    "order_number": row.order_number,
                    "product_name": row.product_name,
                    "status": row.status,
                    "due_at": row.due_at,
                    "priority": row.priority,
                }
                for row in orders
            ],
            "machines": [
                {
                    "id": row.id,
                    "display_name": row.display_name,
                    "machine_model_id": row.machine_model_id,
                }
                for row in machines
            ],
            "machine_models": [
                {
                    "id": row.id,
                    "category": row.category,
                    "manufacturer": row.manufacturer,
                    "model": row.model,
                }
                for row in machine_models
            ],
        }
