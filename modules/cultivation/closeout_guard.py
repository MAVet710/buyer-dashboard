"""Fail-closed harvest completion rules.

A harvest may remain active/drying with incomplete material disposition. It may
not become completed while the authoritative measured output basis still has
unallocated material.
"""

from __future__ import annotations

from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session

from modules.material_lineage.models import (
    MaterialTransformation,
    MaterialTransformationLoss,
    MaterialTransformationOutput,
)
from modules.operational_moats.models import CultivationHarvest


@event.listens_for(Session, "before_flush")
def require_material_closeout_before_harvest_completion(session: Session, _flush_context, _instances) -> None:
    for harvest in list(session.dirty):
        if not isinstance(harvest, CultivationHarvest) or harvest.status != "completed":
            continue
        history = inspect(harvest).attrs.status.history
        if not history.has_changes():
            continue

        dry_weight = float(harvest.dry_weight_g or 0)
        wet_weight = float(harvest.wet_weight_g or 0)
        if dry_weight > 0:
            basis = "dry"
            measured = dry_weight
        elif wet_weight > 0:
            basis = "wet"
            measured = wet_weight
        else:
            raise ValueError(
                "Record a measured harvest weight and allocate its disposition before completing the harvest."
            )

        transformation = session.scalar(
            select(MaterialTransformation).where(
                MaterialTransformation.organization_id == harvest.organization_id,
                MaterialTransformation.facility_id == harvest.facility_id,
                MaterialTransformation.transformation_type == "harvest_allocation",
                MaterialTransformation.source_entity_type == "harvest",
                MaterialTransformation.source_entity_id == harvest.id,
            )
        )
        if transformation is None:
            raise ValueError(
                f"Allocate the measured {basis}-basis harvest output into inventory/loss before completing this harvest."
            )

        output_total = float(
            session.scalar(
                select(func.coalesce(func.sum(MaterialTransformationOutput.quantity), 0.0)).where(
                    MaterialTransformationOutput.transformation_id == transformation.id,
                    MaterialTransformationOutput.measurement_basis == basis,
                )
            )
            or 0.0
        )
        loss_total = float(
            session.scalar(
                select(func.coalesce(func.sum(MaterialTransformationLoss.quantity), 0.0)).where(
                    MaterialTransformationLoss.transformation_id == transformation.id,
                    MaterialTransformationLoss.measurement_basis == basis,
                )
            )
            or 0.0
        )
        disposed = output_total + loss_total
        difference = measured - disposed
        if abs(difference) > 1e-6:
            direction = "unallocated" if difference > 0 else "over-allocated"
            raise ValueError(
                f"Harvest material closeout is incomplete: {abs(difference):,.4f} g {direction} on the {basis} basis. "
                "Post the exact inventory/loss disposition before completing the harvest."
            )
