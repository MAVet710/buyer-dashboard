"""Package Studio saleability hooks.

Package Studio already owns exact physical transformations. These hooks carry
quality evidence and source-material COGS across those transformations so the
child inventory is commercially usable without copying metadata by hand.
"""

from __future__ import annotations

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from modules.coman.models import AuditEvent, InventoryLot, Product
from modules.inventory_quality.service import LotQualityService

from .models import PackageStudioInput, PackageStudioOutput, PackageStudioRun


_REGISTERED = False


def _run_inputs(session: Session, run_id: str) -> list[PackageStudioInput]:
    pending = [row for row in session.new if isinstance(row, PackageStudioInput) and row.run_id == run_id]
    with session.no_autoflush:
        persisted = list(session.scalars(select(PackageStudioInput).where(PackageStudioInput.run_id == run_id)))
    seen = {row.id for row in persisted if row.id}
    persisted.extend(row for row in pending if not row.id or row.id not in seen)
    return persisted


def _inherit_quality(session: Session, output: PackageStudioOutput, run: PackageStudioRun) -> None:
    if not output.lot_id:
        return
    inputs = _run_inputs(session, run.id)
    LotQualityService.inherit(
        session,
        source_lot_ids=[row.lot_id for row in inputs],
        child_lot_id=output.lot_id,
        transformation_type=run.action_type,
        actor=run.completed_by or run.created_by,
    )


def _propagate_cost(session: Session, output: PackageStudioOutput, run: PackageStudioRun) -> None:
    inputs = _run_inputs(session, run.id)
    if not inputs:
        return
    total_source_equivalent = sum(max(0.0, float(row.quantity or 0.0)) for row in inputs)
    if total_source_equivalent <= 0:
        return
    material_cost = 0.0
    for row in inputs:
        lot = session.get(InventoryLot, row.lot_id)
        product = session.get(Product, lot.product_id) if lot else None
        if product is not None:
            material_cost += float(row.quantity or 0.0) * max(0.0, float(product.unit_cost or 0.0))
    if material_cost <= 0:
        return
    source_share = max(0.0, float(output.source_equivalent_quantity or 0.0)) / total_source_equivalent
    output_units = max(0.0, float(output.inventory_quantity or 0.0))
    if source_share <= 0 or output_units <= 0:
        return
    calculated_unit_cost = round(material_cost * source_share / output_units, 6)
    product = session.get(Product, output.product_id)
    if product is None:
        return
    prior = float(product.unit_cost or 0.0)
    # A configured conversion/packaging cost remains additive; a zero-cost
    # Product Master item receives the full derived material cost automatically.
    product.unit_cost = round(prior + calculated_unit_cost, 6) if prior > 0 else calculated_unit_cost
    session.add(
        AuditEvent(
            organization_id=output.organization_id,
            facility_id=output.facility_id,
            entity_type="product",
            entity_id=product.id,
            action="derived_cogs_updated",
            actor=run.completed_by or run.created_by,
            changes_json=(
                '{"package_studio_run":"%s","prior_unit_cost":%.6f,"derived_material_cost":%.6f,"new_unit_cost":%.6f}'
                % (run.run_number, prior, calculated_unit_cost, float(product.unit_cost))
            ),
        )
    )


def _before_flush(session: Session, _flush_context, _instances) -> None:
    for output in [row for row in list(session.new) if isinstance(row, PackageStudioOutput)]:
        run = session.get(PackageStudioRun, output.run_id)
        if run is None:
            continue
        _inherit_quality(session, output, run)
        _propagate_cost(session, output, run)


def register_hardening_hooks() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    event.listen(Session, "before_flush", _before_flush)
    _REGISTERED = True


register_hardening_hooks()
