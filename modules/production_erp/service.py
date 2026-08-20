"""Production ERP execution service over existing Co-Man planning primitives."""

from __future__ import annotations

from collections import defaultdict
import json
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import (
    AuditEvent,
    BomComponent,
    InventoryLot,
    InventoryTransaction,
    MaterialReservation,
    Product,
    ProductBom,
    ProductionActual,
    ProductionOrder,
    utc_now,
)

from .models import ProductionCostEvent, ProductionQAEvent, ProductionRunEvent, ProductionRunOutput


class ProductionERPService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _require_order(session, organization_id: str, facility_id: str, order_id: str) -> ProductionOrder:
        order = session.get(ProductionOrder, order_id)
        if not order or order.organization_id != organization_id or order.facility_id != facility_id:
            raise ValueError("Production order was not found in the active facility.")
        return order

    def list_orders(self, organization_id: str, facility_id: str) -> list[ProductionOrder]:
        with self._sessions() as session:
            return list(session.scalars(select(ProductionOrder).where(ProductionOrder.organization_id == organization_id, ProductionOrder.facility_id == facility_id).order_by(ProductionOrder.due_at.asc().nullslast(), ProductionOrder.created_at.desc())))

    def order_360(self, organization_id: str, facility_id: str, order_id: str) -> dict[str, Any]:
        with self._sessions() as session:
            order = self._require_order(session, organization_id, facility_id, order_id)
            actual = session.scalar(select(ProductionActual).where(ProductionActual.production_order_id == order.id))
            reservations = list(session.scalars(select(MaterialReservation).where(MaterialReservation.production_order_id == order.id)))
            outputs = list(session.scalars(select(ProductionRunOutput).where(ProductionRunOutput.production_order_id == order.id).order_by(ProductionRunOutput.position)))
            events = list(session.scalars(select(ProductionRunEvent).where(ProductionRunEvent.production_order_id == order.id).order_by(ProductionRunEvent.occurred_at)))
            costs = list(session.scalars(select(ProductionCostEvent).where(ProductionCostEvent.production_order_id == order.id).order_by(ProductionCostEvent.occurred_at)))
            qa = list(session.scalars(select(ProductionQAEvent).where(ProductionQAEvent.production_order_id == order.id).order_by(ProductionQAEvent.occurred_at)))
            product = self._resolve_output_product(session, organization_id, order)
            bom = self._active_bom(session, organization_id, product.id) if product else None
            requirements = self._bom_requirements(session, bom, order.requested_units) if bom else []
            cogs = defaultdict(float)
            for row in costs:
                cogs[row.category] += float(row.amount_usd or 0)
            cogs["total"] = sum(cogs.values())
            planned_output = sum(float(row.planned_quantity or 0) for row in outputs) or float(order.requested_units or 0)
            actual_output = sum(float(row.actual_quantity or 0) for row in outputs) or float(getattr(actual, "actual_units", 0) or 0)
            return {
                "order": order,
                "actual": actual,
                "product": product,
                "bom": bom,
                "requirements": requirements,
                "reservations": reservations,
                "outputs": outputs,
                "events": events,
                "cost_events": costs,
                "qa_events": qa,
                "cogs": dict(cogs),
                "planned_output": planned_output,
                "actual_output": actual_output,
                "attainment_pct": actual_output / planned_output * 100 if planned_output > 0 else 0.0,
            }

    @staticmethod
    def _resolve_output_product(session, organization_id: str, order: ProductionOrder) -> Product | None:
        if order.sku:
            product = session.scalar(select(Product).where(Product.organization_id == organization_id, func.lower(Product.sku) == order.sku.casefold(), Product.active.is_(True)))
            if product:
                return product
        return session.scalar(select(Product).where(Product.organization_id == organization_id, func.lower(Product.name) == order.product_name.casefold(), Product.active.is_(True)))

    @staticmethod
    def _active_bom(session, organization_id: str, product_id: str) -> ProductBom | None:
        return session.scalar(select(ProductBom).where(ProductBom.organization_id == organization_id, ProductBom.output_product_id == product_id, ProductBom.active.is_(True)).order_by(ProductBom.version.desc()).limit(1))

    @staticmethod
    def _bom_requirements(session, bom: ProductBom, requested_units: float) -> list[dict[str, Any]]:
        components = list(session.scalars(select(BomComponent).where(BomComponent.bom_id == bom.id)))
        scale = float(requested_units or 0) / float(bom.output_quantity or 1)
        rows = []
        for component in components:
            product = session.get(Product, component.input_product_id)
            needed = float(component.quantity or 0) * scale * (1 + float(component.scrap_pct or 0) / 100.0)
            rows.append({"product_id": component.input_product_id, "product_name": product.name if product else component.input_product_id, "quantity": needed, "unit": component.unit, "scrap_pct": float(component.scrap_pct or 0)})
        return rows

    def reserve_bom_materials(self, *, organization_id: str, facility_id: str, order_id: str, actor: str) -> dict[str, Any]:
        """Allocate canonical lots FIFO for the order's active BOM; never over-reserve."""
        result = {"reserved": 0, "shortages": []}
        with self._sessions.begin() as session:
            order = self._require_order(session, organization_id, facility_id, order_id)
            product = self._resolve_output_product(session, organization_id, order)
            if not product:
                raise ValueError("Link this production order to a canonical Product Master item first.")
            bom = self._active_bom(session, organization_id, product.id)
            if not bom:
                raise ValueError("No active BOM exists for this product.")
            requirements = self._bom_requirements(session, bom, order.requested_units)
            existing = list(session.scalars(select(MaterialReservation).where(MaterialReservation.production_order_id == order.id, MaterialReservation.status == "reserved")))
            existing_by_lot = {row.lot_id: float(row.quantity or 0) for row in existing}
            for requirement in requirements:
                needed = float(requirement["quantity"])
                lots = list(session.scalars(select(InventoryLot).where(InventoryLot.organization_id == organization_id, InventoryLot.facility_id == facility_id, InventoryLot.product_id == requirement["product_id"], InventoryLot.status.in_(("available", "released"))).order_by(InventoryLot.received_at.asc().nullsfirst(), InventoryLot.created_at.asc())))
                for lot in lots:
                    if needed <= 1e-9:
                        break
                    balance = float(session.scalar(select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(InventoryTransaction.lot_id == lot.id)) or 0.0)
                    other_reserved = float(session.scalar(select(func.coalesce(func.sum(MaterialReservation.quantity), 0.0)).where(MaterialReservation.lot_id == lot.id, MaterialReservation.status == "reserved", MaterialReservation.production_order_id != order.id)) or 0.0)
                    available = max(0.0, balance - other_reserved - existing_by_lot.get(lot.id, 0.0))
                    take = min(needed, available)
                    if take <= 0:
                        continue
                    reservation = session.scalar(select(MaterialReservation).where(MaterialReservation.production_order_id == order.id, MaterialReservation.lot_id == lot.id))
                    if reservation is None:
                        reservation = MaterialReservation(organization_id=organization_id, facility_id=facility_id, production_order_id=order.id, lot_id=lot.id, quantity=take, unit=requirement["unit"], status="reserved", reserved_by=actor)
                        session.add(reservation)
                    else:
                        reservation.quantity = float(reservation.quantity or 0) + take
                        reservation.status = "reserved"
                        reservation.reserved_by = actor
                    existing_by_lot[lot.id] = existing_by_lot.get(lot.id, 0.0) + take
                    needed -= take
                    result["reserved"] += 1
                if needed > 1e-9:
                    result["shortages"].append({"product": requirement["product_name"], "short": needed, "unit": requirement["unit"]})
            session.add(AuditEvent(organization_id=organization_id, facility_id=facility_id, entity_type="production_order", entity_id=order.id, action="bom_materials_reserved", actor=actor, changes_json=json.dumps(result, sort_keys=True)))
        return result

    def record_event(self, *, organization_id: str, facility_id: str, order_id: str, event_type: str, actor: str, stage_key: str = "execution", quantity: float | None = None, unit: str = "unit", waste_quantity: float | None = None, labor_hours: float | None = None, machine_hours: float | None = None, machine_id: str | None = None, notes: str = "") -> ProductionRunEvent:
        with self._sessions.begin() as session:
            order = self._require_order(session, organization_id, facility_id, order_id)
            event = ProductionRunEvent(organization_id=organization_id, facility_id=facility_id, production_order_id=order.id, stage_key=stage_key, event_type=event_type, quantity=quantity, unit=unit, waste_quantity=waste_quantity, labor_hours=labor_hours, machine_hours=machine_hours, machine_id=machine_id, notes=notes, actor=actor)
            session.add(event)
            if event_type == "started" and order.status in {"draft", "scheduled"}:
                order.status = "in_progress"
            elif event_type == "hold":
                order.status = "on_hold"
            elif event_type == "completed":
                order.status = "complete"
            session.flush(); return event

    def add_output(self, *, organization_id: str, facility_id: str, order_id: str, product_id: str, planned_quantity: float, actor: str, label: str = "", unit: str = "unit") -> ProductionRunOutput:
        if planned_quantity < 0:
            raise ValueError("Planned output cannot be negative.")
        with self._sessions.begin() as session:
            order = self._require_order(session, organization_id, facility_id, order_id)
            product = session.get(Product, product_id)
            if not product or product.organization_id != organization_id:
                raise ValueError("Output product was not found in this organization.")
            position = int(session.scalar(select(func.coalesce(func.max(ProductionRunOutput.position), 0)).where(ProductionRunOutput.production_order_id == order.id)) or 0) + 1
            output = ProductionRunOutput(organization_id=organization_id, facility_id=facility_id, production_order_id=order.id, product_id=product.id, position=position, label=label or product.name, planned_quantity=planned_quantity, actual_quantity=0.0, unit=unit or product.base_unit, status="planned", created_by=actor)
            session.add(output); session.flush(); return output

    def record_output_actual(self, *, organization_id: str, facility_id: str, output_id: str, actual_quantity: float, actor: str, lot_code: str = "") -> ProductionRunOutput:
        if actual_quantity < 0:
            raise ValueError("Actual output cannot be negative.")
        with self._sessions.begin() as session:
            output = session.get(ProductionRunOutput, output_id)
            if not output or output.organization_id != organization_id or output.facility_id != facility_id:
                raise ValueError("Production output was not found in the active facility.")
            output.actual_quantity = actual_quantity
            output.status = "quarantine"
            if lot_code and not output.lot_id:
                lot = InventoryLot(organization_id=organization_id, facility_id=facility_id, product_id=output.product_id, lot_code=lot_code, location_code="QA-HOLD", status="quarantine", notes=f"Production output {output.id}")
                session.add(lot); session.flush(); output.lot_id = lot.id
                if actual_quantity > 0:
                    session.add(InventoryTransaction(organization_id=organization_id, facility_id=facility_id, lot_id=lot.id, transaction_type="production_output", quantity_delta=actual_quantity, unit=output.unit, production_order_id=output.production_order_id, commercial_order_id=None, commercial_order_line_id=None, reason="Production output pending QA release", reference=output.id, actor=actor))
            return output

    def record_qa(self, *, organization_id: str, facility_id: str, order_id: str, event_type: str, result: str, actor: str, output_id: str | None = None, document_reference: str = "", notes: str = "") -> ProductionQAEvent:
        with self._sessions.begin() as session:
            order = self._require_order(session, organization_id, facility_id, order_id)
            if output_id:
                output = session.get(ProductionRunOutput, output_id)
                if not output or output.production_order_id != order.id:
                    raise ValueError("QA output is not part of this production order.")
            event = ProductionQAEvent(organization_id=organization_id, facility_id=facility_id, production_order_id=order.id, output_id=output_id, event_type=event_type, result=result, document_reference=document_reference, notes=notes, actor=actor)
            session.add(event)
            if event_type == "hold" or result == "failed":
                order.status = "on_hold"
            if event_type == "release" and result == "passed":
                targets = list(session.scalars(select(ProductionRunOutput).where(ProductionRunOutput.production_order_id == order.id, ProductionRunOutput.status == "quarantine")))
                if output_id:
                    targets = [row for row in targets if row.id == output_id]
                for output in targets:
                    output.status = "released"
                    if output.lot_id:
                        lot = session.get(InventoryLot, output.lot_id)
                        if lot:
                            lot.status = "available"; lot.location_code = "UNASSIGNED" if lot.location_code == "QA-HOLD" else lot.location_code
            return event

    def add_cost(self, *, organization_id: str, facility_id: str, order_id: str, category: str, amount_usd: float, actor: str, quantity: float | None = None, unit: str = "", source_type: str = "manual", source_id: str = "", notes: str = "") -> ProductionCostEvent:
        if amount_usd < 0:
            raise ValueError("Cost cannot be negative.")
        with self._sessions.begin() as session:
            order = self._require_order(session, organization_id, facility_id, order_id)
            event = ProductionCostEvent(organization_id=organization_id, facility_id=facility_id, production_order_id=order.id, category=category, amount_usd=amount_usd, quantity=quantity, unit=unit, source_type=source_type, source_id=source_id, notes=notes, actor=actor)
            session.add(event); session.flush(); return event

    def queue_summary(self, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
        rows = []
        for order in self.list_orders(organization_id, facility_id):
            snapshot = self.order_360(organization_id, facility_id, order.id)
            cogs = float(snapshot["cogs"].get("total", 0) or 0)
            actual = float(snapshot["actual_output"] or 0)
            qa_blocked = any(event.event_type in {"hold", "fail"} and event.result != "passed" for event in snapshot["qa_events"])
            rows.append({"order_id": order.id, "Order": order.order_number, "Product": order.product_name, "Status": order.status.replace("_", " ").title(), "Planned": order.requested_units, "Actual": actual, "Attainment %": snapshot["attainment_pct"], "COGS": cogs, "Cost / Unit": cogs / actual if actual > 0 else 0.0, "Reservations": len(snapshot["reservations"]), "QA": "HOLD" if qa_blocked else "Ready", "Attention": "QA HOLD" if qa_blocked else ("Material shortage" if snapshot["requirements"] and not snapshot["reservations"] else "Normal")})
        return rows
