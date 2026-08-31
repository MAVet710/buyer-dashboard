"""Production Run 360 mutation semantics layered on the generic preview engine."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from modules.coman.models import (
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    Product,
    ProductionOrder,
)
from modules.inventory_availability.service import InventoryAvailabilityService
from modules.material_lineage.models import MaterialTransformationInput
from modules.material_lineage.service import MaterialLineageService
from modules.production_erp.models import ProductionQAEvent, ProductionRunEvent, ProductionRunOutput
from modules.production_erp.mutations import MUTATION_ACTIONS, ProductionMutationService


MUTATION_ACTIONS.add("consume_materials")


class ProductionRun360MutationService(ProductionMutationService):
    """Keep production state, physical inventory and genealogy on one governed flow.

    Reservation remains planning. ``consume_materials`` is the physical source-ledger
    event. Realized outputs attach to the same canonical material transformation so
    a finished lot can trace back to every actual source lot.
    """

    @staticmethod
    def _realized_output(output: ProductionRunOutput) -> bool:
        return bool(
            float(output.actual_quantity or 0) > 0
            or output.lot_id
            or output.status != "planned"
        )

    @staticmethod
    def _unit_token(value: str) -> str:
        token = str(value or "").strip().casefold()
        return {
            "gram": "g",
            "grams": "g",
            "unit": "unit",
            "units": "unit",
            "each": "unit",
            "ea": "unit",
        }.get(token, token)

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
        if str(action_type or "").strip() != "consume_materials":
            return super()._build_preview(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                order=order,
                action_type=action_type,
                payload=payload,
                lock=lock,
            )
        preview = self._preview_material_consumption(
            session,
            organization_id=organization_id,
            facility_id=facility_id,
            order=order,
            payload=dict(payload or {}),
            lock=lock,
        )
        key_material = {
            "action_type": "consume_materials",
            "order_id": order.id,
            "payload": self._normalized(payload),
            "state": preview.pop("_state"),
        }
        preview["action_type"] = "consume_materials"
        preview["preview_key"] = self._fingerprint(key_material)
        preview["blocker_count"] = sum(
            1 for row in preview.get("warnings", []) if row.get("severity") == "blocker"
        )
        return preview

    def _preview_material_consumption(
        self,
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        payload: dict[str, Any],
        lock: bool,
    ) -> dict[str, Any]:
        raw_materials = list(payload.get("materials") or [])
        if not raw_materials:
            raise ValueError("Add at least one actual source lot to consume.")

        product = self.erp._resolve_output_product(session, organization_id, order)
        bom = self.erp._active_bom(session, organization_id, product.id) if product else None
        requirements = self.erp._bom_requirements(session, bom, order.requested_units) if bom else []
        expected_by_product: dict[str, float] = defaultdict(float)
        for row in requirements:
            expected_by_product[str(row["product_id"])] += float(row["quantity"] or 0)

        consumed_before_by_product: dict[str, float] = defaultdict(float)
        for product_id, consumed in session.execute(
            select(
                InventoryLot.product_id,
                func.coalesce(func.sum(-InventoryTransaction.quantity_delta), 0.0),
            )
            .join(InventoryTransaction, InventoryTransaction.lot_id == InventoryLot.id)
            .where(
                InventoryTransaction.organization_id == organization_id,
                InventoryTransaction.facility_id == facility_id,
                InventoryTransaction.production_order_id == order.id,
                InventoryTransaction.transaction_type == "production_consume",
                InventoryTransaction.quantity_delta < 0,
            )
            .group_by(InventoryLot.product_id)
        ):
            consumed_before_by_product[str(product_id)] = float(consumed or 0)

        availability = InventoryAvailabilityService.build(session, organization_id, facility_id)
        normalized: list[dict[str, Any]] = []
        warnings: list[dict[str, str]] = []
        consequences: list[dict[str, str]] = []
        requested_by_product: dict[str, float] = defaultdict(float)
        lot_state: list[dict[str, Any]] = []
        seen_lots: set[str] = set()

        for raw in raw_materials:
            lot_id = str(raw.get("lot_id") or "").strip()
            quantity = float(raw.get("quantity") or 0)
            requested_unit = self._unit_token(str(raw.get("unit") or ""))
            purpose = str(raw.get("purpose") or "source_material").strip() or "source_material"
            if not lot_id or quantity <= 0:
                raise ValueError("Every actual material row requires a source lot and positive quantity.")
            if lot_id in seen_lots:
                raise ValueError("Combine duplicate source-lot rows before previewing actual consumption.")
            seen_lots.add(lot_id)

            query = select(InventoryLot).where(
                InventoryLot.id == lot_id,
                InventoryLot.organization_id == organization_id,
                InventoryLot.facility_id == facility_id,
            )
            if lock:
                query = query.with_for_update()
            lot = session.scalar(query)
            if lot is None:
                raise ValueError("An actual source lot was not found in the active facility.")
            if lot.status not in {"available", "released"}:
                warnings.append({
                    "severity": "blocker",
                    "message": f"Source lot {lot.lot_code} is {lot.status} and cannot be consumed into production.",
                })
            source_product = session.get(Product, lot.product_id)
            if source_product is None or source_product.organization_id != organization_id:
                raise ValueError("Source-lot Product Master data is unavailable in this organization.")
            canonical_unit = self._unit_token(source_product.base_unit)
            unit = requested_unit or canonical_unit
            if canonical_unit and unit != canonical_unit:
                raise ValueError(
                    f"Source lot {lot.lot_code} uses {source_product.base_unit}; convert the actual quantity before consumption."
                )

            reservation_query = select(MaterialReservation).where(
                MaterialReservation.organization_id == organization_id,
                MaterialReservation.facility_id == facility_id,
                MaterialReservation.production_order_id == order.id,
                MaterialReservation.lot_id == lot.id,
                MaterialReservation.status == "reserved",
            )
            if lock:
                reservation_query = reservation_query.with_for_update()
            reservation = session.scalar(reservation_query)
            own_reserved = float(reservation.quantity or 0) if reservation else 0.0
            snapshot = availability["by_lot"].get(lot.id, {})
            on_hand = max(0.0, float(snapshot.get("on_hand", 0.0) or 0.0))
            available = max(0.0, float(snapshot.get("available", 0.0) or 0.0))
            allowed = available + own_reserved
            if quantity > allowed + 1e-9:
                warnings.append({
                    "severity": "blocker",
                    "message": (
                        f"Source lot {lot.lot_code} can supply only {allowed:g} {unit} after other active "
                        "Production and Wholesale commitments."
                    ),
                })
            elif quantity > own_reserved + 1e-9:
                warnings.append({
                    "severity": "warning",
                    "message": (
                        f"Actual use of {lot.lot_code} exceeds this run's reservation by "
                        f"{quantity - own_reserved:g} {unit}; the excess is allowed only from currently uncommitted stock."
                    ),
                })

            normalized.append({
                "lot_id": lot.id,
                "lot_code": lot.lot_code,
                "product_id": lot.product_id,
                "product_name": source_product.name,
                "quantity": quantity,
                "unit": unit,
                "purpose": purpose,
                "reserved_before": own_reserved,
                "on_hand_before": on_hand,
                "available_to_run": allowed,
            })
            requested_by_product[lot.product_id] += quantity
            consequences.append({
                "label": f"Consume {source_product.name}",
                "before": f"{on_hand:g} {unit} physical on hand in {lot.lot_code}",
                "after": f"{max(0.0, on_hand - quantity):g} {unit} physical on hand; {quantity:g} {unit} actual run use",
            })
            lot_state.append({
                "lot_id": lot.id,
                "lot_code": lot.lot_code,
                "status": lot.status,
                "updated_at": getattr(lot, "updated_at", None),
                "on_hand": on_hand,
                "available": available,
                "own_reserved": own_reserved,
            })

        variances: list[dict[str, Any]] = []
        all_product_ids = set(expected_by_product) | set(consumed_before_by_product) | set(requested_by_product)
        for product_id in sorted(all_product_ids):
            source_product = session.get(Product, product_id)
            expected = float(expected_by_product.get(product_id, 0.0))
            before = float(consumed_before_by_product.get(product_id, 0.0))
            requested = float(requested_by_product.get(product_id, 0.0))
            after = before + requested
            variances.append({
                "product_id": product_id,
                "product_name": source_product.name if source_product else product_id,
                "expected": expected,
                "consumed_before": before,
                "requested_now": requested,
                "consumed_after": after,
                "variance": after - expected,
                "variance_pct": ((after - expected) / expected * 100.0) if expected > 0 else None,
                "unit": source_product.base_unit if source_product else "",
            })

        return {
            "title": "Consume actual production materials",
            "summary": f"Post {len(normalized)} source-lot consumption event(s) to the physical inventory ledger.",
            "consequences": consequences,
            "warnings": warnings,
            "details": {"materials": normalized, "material_variance": variances},
            "_state": {
                "order_status": order.status,
                "order_updated_at": getattr(order, "updated_at", None),
                "requirements": requirements,
                "consumed_before_by_product": dict(consumed_before_by_product),
                "lots": lot_state,
            },
        }

    def _preview_run_event(self, session: Session, order: ProductionOrder, payload: dict[str, Any]) -> dict[str, Any]:
        preview = super()._preview_run_event(session, order, payload)
        if str(payload.get("event_type") or "").strip() != "completed":
            return preview
        product = self.erp._resolve_output_product(session, order.organization_id, order)
        bom = self.erp._active_bom(session, order.organization_id, product.id) if product else None
        requirements = self.erp._bom_requirements(session, bom, order.requested_units) if bom else []
        if not requirements:
            return preview
        consumed_by_product: dict[str, float] = defaultdict(float)
        for product_id, consumed in session.execute(
            select(
                InventoryLot.product_id,
                func.coalesce(func.sum(-InventoryTransaction.quantity_delta), 0.0),
            )
            .join(InventoryTransaction, InventoryTransaction.lot_id == InventoryLot.id)
            .where(
                InventoryTransaction.production_order_id == order.id,
                InventoryTransaction.transaction_type == "production_consume",
                InventoryTransaction.quantity_delta < 0,
            )
            .group_by(InventoryLot.product_id)
        ):
            consumed_by_product[str(product_id)] = float(consumed or 0)
        closeout: list[dict[str, Any]] = []
        for requirement in requirements:
            expected = float(requirement["quantity"] or 0)
            actual = float(consumed_by_product.get(str(requirement["product_id"]), 0.0))
            closeout.append({
                "product_id": requirement["product_id"],
                "product": requirement["product_name"],
                "expected": expected,
                "actual_consumed": actual,
                "variance": actual - expected,
                "unit": requirement["unit"],
            })
            if expected > 0 and actual <= 1e-9:
                preview["warnings"].append({
                    "severity": "blocker",
                    "message": f"Record actual consumption for {requirement['product_name']} before completing this run.",
                })
            elif expected > 0 and abs(actual - expected) > 1e-9:
                preview["warnings"].append({
                    "severity": "warning",
                    "message": (
                        f"{requirement['product_name']} actual use is {actual:g} {requirement['unit']} versus "
                        f"{expected:g} {requirement['unit']} BOM expectation; closeout will retain this variance."
                    ),
                })
        preview.setdefault("details", {})["material_closeout"] = closeout
        return preview

    def _preview_qa(
        self,
        session: Session,
        order: ProductionOrder,
        payload: dict[str, Any],
        *,
        lock: bool,
    ) -> dict[str, Any]:
        preview = super()._preview_qa(session, order, payload, lock=lock)
        output_id = str(payload.get("output_id") or "").strip() or None
        event_type = str(payload.get("event_type") or "").strip()
        result = str(payload.get("result") or "pending").strip()

        query = select(ProductionRunOutput).where(ProductionRunOutput.production_order_id == order.id)
        if output_id:
            query = query.where(ProductionRunOutput.id == output_id)
        outputs = list(session.scalars(query))
        realized = [row for row in outputs if self._realized_output(row)]

        if event_type == "hold" or result == "failed":
            non_output_consequences = [
                row
                for row in preview["consequences"]
                if row.get("after") != "Quarantine / unavailable"
            ]
            preview["consequences"] = non_output_consequences + [
                {
                    "label": row.label,
                    "before": str(row.status).replace("_", " ").title(),
                    "after": "Quarantine / unavailable",
                }
                for row in realized
                if row.status not in {"waste", "destroyed"}
            ]
            preview["details"]["target_output_ids"] = sorted(row.id for row in realized)
        elif event_type == "release" and result == "passed":
            product = self.erp._resolve_output_product(session, order.organization_id, order)
            bom = self.erp._active_bom(session, order.organization_id, product.id) if product else None
            requirements = self.erp._bom_requirements(session, bom, order.requested_units) if bom else []
            if requirements:
                consumed_products = {
                    str(product_id)
                    for product_id in session.scalars(
                        select(InventoryLot.product_id)
                        .join(InventoryTransaction, InventoryTransaction.lot_id == InventoryLot.id)
                        .where(
                            InventoryTransaction.production_order_id == order.id,
                            InventoryTransaction.transaction_type == "production_consume",
                            InventoryTransaction.quantity_delta < 0,
                        )
                        .distinct()
                    )
                }
                missing = [row["product_name"] for row in requirements if str(row["product_id"]) not in consumed_products]
                if missing:
                    preview["warnings"].append({
                        "severity": "blocker",
                        "message": "Finished output cannot be released before actual source consumption is recorded for: " + ", ".join(missing[:5]),
                    })
            releasable = [row for row in realized if row.status in {"quarantine", "rework"}]
            preview["details"]["target_output_ids"] = sorted(row.id for row in releasable)
            if not releasable:
                preview["warnings"] = [
                    row
                    for row in preview["warnings"]
                    if "no production output rows" not in str(row.get("message") or "").casefold()
                ]
                preview["warnings"].append(
                    {
                        "severity": "warning",
                        "message": "There are no realized quarantined/rework outputs to release; this will only record the QA decision.",
                    }
                )
        return preview

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
        if action_type != "consume_materials":
            return super()._apply(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                order=order,
                action_type=action_type,
                payload=payload,
                preview=preview,
                actor=actor,
            )
        transformation = MaterialLineageService.production_transformation(
            session,
            organization_id=organization_id,
            facility_id=facility_id,
            order=order,
            actor=actor,
        )
        consumed: list[dict[str, Any]] = []
        for row in preview.get("details", {}).get("materials", []):
            quantity = float(row["quantity"])
            session.add(
                InventoryTransaction(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    lot_id=row["lot_id"],
                    transaction_type="production_consume",
                    quantity_delta=-quantity,
                    unit=row["unit"],
                    production_order_id=order.id,
                    commercial_order_id=None,
                    commercial_order_line_id=None,
                    reason="Actual material consumed by Production Run 360",
                    reference=order.order_number,
                    actor=actor,
                )
            )
            reservation = session.scalar(
                select(MaterialReservation).where(
                    MaterialReservation.organization_id == organization_id,
                    MaterialReservation.facility_id == facility_id,
                    MaterialReservation.production_order_id == order.id,
                    MaterialReservation.lot_id == row["lot_id"],
                    MaterialReservation.status == "reserved",
                ).with_for_update()
            )
            if reservation:
                remaining = max(0.0, float(reservation.quantity or 0) - quantity)
                reservation.quantity = remaining
                if remaining <= 1e-9:
                    reservation.status = "consumed"
            MaterialLineageService.add_input(
                session,
                transformation,
                entity_type="lot",
                entity_id=row["lot_id"],
                lot_id=row["lot_id"],
                product_id=row["product_id"],
                quantity=quantity,
                unit=row["unit"],
                purpose=row.get("purpose") or "source_material",
                accumulate=True,
            )
            consumed.append({
                "lot_id": row["lot_id"],
                "lot_code": row["lot_code"],
                "quantity": quantity,
                "unit": row["unit"],
                "reservation_remaining": float(reservation.quantity or 0) if reservation else 0.0,
            })
        attached = MaterialLineageService.attach_production_outputs(session, transformation, order)
        transformation.status = "committed"
        session.flush()
        return {
            "transformation_id": transformation.id,
            "consumed": consumed,
            "material_variance": preview.get("details", {}).get("material_variance", []),
            "attached_output_lot_ids": attached,
        }

    def _apply_output_actual(
        self,
        session: Session,
        organization_id: str,
        facility_id: str,
        order: ProductionOrder,
        payload: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        result = super()._apply_output_actual(
            session,
            organization_id,
            facility_id,
            order,
            payload,
            actor,
        )
        transformation = MaterialLineageService.production_transformation(
            session,
            organization_id=organization_id,
            facility_id=facility_id,
            order=order,
            actor=actor,
        )
        attached = MaterialLineageService.attach_production_outputs(session, transformation, order)
        transformation.status = "committed"
        result["transformation_id"] = transformation.id
        result["lineage_output_lot_ids"] = attached
        return result

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
        outputs = [
            row
            for row in session.scalars(outputs_query)
            if ProductionRun360MutationService._realized_output(row)
        ]
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
            "affected_output_ids": [row.id for row in outputs],
        }
