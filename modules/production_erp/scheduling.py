"""Capacity-aware production schedule previews and versioned placement commits."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import (
    CrewAvailability,
    FacilityMachine,
    MachineModel,
    MaterialReservation,
    ProductionOrder,
)
from modules.coman.repository import ComanRepository
from modules.production_erp.models import ProductionSchedulePlacement
from modules.production_erp.service import ProductionERPService


class ProductionScheduleService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.erp = ProductionERPService(engine)
        self.repo = ComanRepository(engine)

    def list_current(self, organization_id: str, facility_id: str) -> list[dict]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(ProductionSchedulePlacement, ProductionOrder)
                .join(ProductionOrder, ProductionOrder.id == ProductionSchedulePlacement.production_order_id)
                .where(
                    ProductionSchedulePlacement.organization_id == organization_id,
                    ProductionSchedulePlacement.facility_id == facility_id,
                    ProductionSchedulePlacement.active.is_(True),
                )
                .order_by(ProductionSchedulePlacement.scheduled_start_at.asc())
            ).all()
            return [self._placement_payload(placement, order) for placement, order in rows]

    def preview(
        self,
        *,
        organization_id: str,
        facility_id: str,
        order_id: str,
        scheduled_start_at: datetime,
        scheduled_end_at: datetime,
        machine_id: str | None,
        planned_people: int,
        reason: str,
    ) -> dict:
        if scheduled_end_at <= scheduled_start_at:
            raise ValueError("Scheduled end must be after scheduled start.")
        if planned_people < 0:
            raise ValueError("Planned people cannot be negative.")

        snapshot = self.erp.order_360(organization_id, facility_id, order_id)
        order = snapshot["order"]
        standard = snapshot.get("standard")
        variance = snapshot.get("variance") or {}
        warnings: list[dict] = []

        current = self._current_placement(organization_id, facility_id, order_id)
        machine = self._machine(organization_id, facility_id, machine_id) if machine_id else None
        if machine_id and machine is None:
            raise ValueError("Selected machine is not available in this facility.")

        resource_category = str(variance.get("resource_category") or getattr(standard, "resource_category", "") or "").strip()
        if resource_category:
            if machine is None:
                warnings.append(self._warning("machine_required", "Equipment", f"BOM standard calls for {resource_category}, but no machine is assigned."))
            else:
                category = self._machine_category(machine)
                if category and not self._category_matches(resource_category, category):
                    warnings.append(self._warning("machine_category", "Equipment", f"Assigned machine category {category} does not match the BOM standard {resource_category}."))

        if machine is not None:
            overlaps = self._machine_overlaps(
                organization_id=organization_id,
                facility_id=facility_id,
                machine_id=machine.id,
                order_id=order_id,
                start=scheduled_start_at,
                end=scheduled_end_at,
            )
            if overlaps:
                labels = ", ".join(row["order_number"] for row in overlaps[:3])
                warnings.append(self._warning("machine_overlap", "Equipment", f"Machine is already scheduled for {labels} during this window.", severity="blocker"))

        expected_cycle = float(variance.get("expected_cycle_hours") or 0.0)
        window_hours = (scheduled_end_at - scheduled_start_at).total_seconds() / 3600.0
        if expected_cycle > 0 and window_hours + 1e-9 < expected_cycle:
            warnings.append(self._warning("cycle_time", "Capacity", f"Scheduled window is {window_hours:.2f} hr, below the BOM standard of {expected_cycle:.2f} hr."))

        expected_labor = float(variance.get("expected_labor_hours") or 0.0)
        crew = self._crew_capacity(organization_id, facility_id, scheduled_start_at, scheduled_end_at)
        if planned_people == 0 and expected_labor > 0:
            suggested_people = max(1, math.ceil(expected_labor / max(window_hours, 0.01)))
            warnings.append(self._warning("crew_unassigned", "Labor", f"No crew is assigned. Based on {expected_labor:.2f} standard labor hours, consider at least {suggested_people} people for this window."))
        for day_label, available in crew.items():
            if planned_people > available:
                warnings.append(self._warning("crew_capacity", "Labor", f"{planned_people} people are planned on {day_label}, but only {available} are scheduled as available.", severity="blocker"))

        if order.due_at is not None and scheduled_end_at > self._compatible_datetime(order.due_at, scheduled_end_at):
            warnings.append(self._warning("due_date", "Due date", "The proposed schedule finishes after the production order due date."))

        warnings.extend(self._material_warnings(organization_id, facility_id, snapshot))

        qa_events = snapshot.get("qa_events") or []
        if qa_events:
            latest_qa = max(qa_events, key=lambda row: row.occurred_at)
            if latest_qa.event_type in {"hold", "fail"} or latest_qa.result == "failed":
                warnings.append(self._warning("qa_hold", "QA", "This run is currently under a QA hold/failure and should not be scheduled as release-ready.", severity="blocker"))

        if bool(variance.get("qa_required")) and not bool(variance.get("qa_ready")):
            warnings.append(self._warning("qa_required", "QA", "The BOM standard requires QA before finished output release."))
        checkpoint = str(variance.get("compliance_checkpoint") or "").strip()
        if checkpoint:
            warnings.append(self._warning("compliance_checkpoint", "Compliance", f"Required checkpoint: {checkpoint}", severity="info"))

        request = {
            "order_id": order_id,
            "scheduled_start_at": scheduled_start_at.isoformat(),
            "scheduled_end_at": scheduled_end_at.isoformat(),
            "machine_id": machine_id or "",
            "planned_people": int(planned_people),
            "reason": reason.strip(),
            "current_version": current.version if current is not None else 0,
        }
        preview_key = self._preview_key(request, warnings)
        blockers = sum(row["severity"] == "blocker" for row in warnings)
        return {
            "order": {
                "id": order.id,
                "order_number": order.order_number,
                "product_name": order.product_name,
                "due_at": order.due_at,
                "priority": order.priority,
                "status": order.status,
            },
            "current": None if current is None else self._placement_payload(current, order),
            "proposed": {
                "scheduled_start_at": scheduled_start_at,
                "scheduled_end_at": scheduled_end_at,
                "machine_id": machine_id,
                "machine_name": getattr(machine, "display_name", "") if machine is not None else "",
                "planned_people": planned_people,
                "window_hours": round(window_hours, 2),
                "reason": reason.strip(),
            },
            "warnings": warnings,
            "blocker_count": blockers,
            "warning_count": len([row for row in warnings if row["severity"] != "info"]),
            "preview_key": preview_key,
        }

    def commit(
        self,
        *,
        organization_id: str,
        facility_id: str,
        order_id: str,
        scheduled_start_at: datetime,
        scheduled_end_at: datetime,
        machine_id: str | None,
        planned_people: int,
        reason: str,
        preview_key: str,
        accept_warnings: bool,
        actor: str,
    ) -> dict:
        preview = self.preview(
            organization_id=organization_id,
            facility_id=facility_id,
            order_id=order_id,
            scheduled_start_at=scheduled_start_at,
            scheduled_end_at=scheduled_end_at,
            machine_id=machine_id,
            planned_people=planned_people,
            reason=reason,
        )
        if not preview_key or preview_key != preview["preview_key"]:
            raise ValueError("Schedule preview is stale. Review the conflicts again before committing this placement.")
        actionable = [row for row in preview["warnings"] if row["severity"] != "info"]
        if actionable and not accept_warnings:
            raise ValueError("Review and acknowledge the schedule warnings before committing this placement.")

        with Session(self.engine) as session:
            current_rows = session.scalars(
                select(ProductionSchedulePlacement).where(
                    ProductionSchedulePlacement.organization_id == organization_id,
                    ProductionSchedulePlacement.facility_id == facility_id,
                    ProductionSchedulePlacement.production_order_id == order_id,
                    ProductionSchedulePlacement.active.is_(True),
                )
            ).all()
            version = 1
            for current in current_rows:
                version = max(version, current.version + 1)
                current.active = False
            prior_max = session.scalar(
                select(ProductionSchedulePlacement.version)
                .where(ProductionSchedulePlacement.production_order_id == order_id)
                .order_by(ProductionSchedulePlacement.version.desc())
                .limit(1)
            )
            if prior_max:
                version = max(version, int(prior_max) + 1)
            row = ProductionSchedulePlacement(
                organization_id=organization_id,
                facility_id=facility_id,
                production_order_id=order_id,
                version=version,
                scheduled_start_at=scheduled_start_at,
                scheduled_end_at=scheduled_end_at,
                machine_id=machine_id or None,
                planned_people=planned_people,
                reason=reason.strip(),
                active=True,
                created_by=actor,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            order = session.get(ProductionOrder, order_id)
            return self._placement_payload(row, order)

    def _current_placement(self, organization_id: str, facility_id: str, order_id: str):
        with Session(self.engine) as session:
            return session.scalar(
                select(ProductionSchedulePlacement).where(
                    ProductionSchedulePlacement.organization_id == organization_id,
                    ProductionSchedulePlacement.facility_id == facility_id,
                    ProductionSchedulePlacement.production_order_id == order_id,
                    ProductionSchedulePlacement.active.is_(True),
                )
            )

    def _machine(self, organization_id: str, facility_id: str, machine_id: str):
        with Session(self.engine) as session:
            return session.scalar(
                select(FacilityMachine).where(
                    FacilityMachine.id == machine_id,
                    FacilityMachine.organization_id == organization_id,
                    FacilityMachine.facility_id == facility_id,
                    FacilityMachine.active.is_(True),
                )
            )

    def _machine_category(self, machine: FacilityMachine) -> str:
        with Session(self.engine) as session:
            model = session.get(MachineModel, machine.machine_model_id)
            return str(model.category or "") if model is not None else ""

    def _machine_overlaps(self, *, organization_id: str, facility_id: str, machine_id: str, order_id: str, start: datetime, end: datetime) -> list[dict]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(ProductionSchedulePlacement, ProductionOrder)
                .join(ProductionOrder, ProductionOrder.id == ProductionSchedulePlacement.production_order_id)
                .where(
                    ProductionSchedulePlacement.organization_id == organization_id,
                    ProductionSchedulePlacement.facility_id == facility_id,
                    ProductionSchedulePlacement.machine_id == machine_id,
                    ProductionSchedulePlacement.active.is_(True),
                    ProductionSchedulePlacement.production_order_id != order_id,
                    ProductionSchedulePlacement.scheduled_start_at < end,
                    ProductionSchedulePlacement.scheduled_end_at > start,
                )
            ).all()
            return [{"order_id": order.id, "order_number": order.order_number} for _, order in rows]

    def _crew_capacity(self, organization_id: str, facility_id: str, start: datetime, end: datetime) -> dict[str, int]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(CrewAvailability).where(
                    CrewAvailability.organization_id == organization_id,
                    CrewAvailability.facility_id == facility_id,
                    CrewAvailability.work_date >= start.date(),
                    CrewAvailability.work_date <= end.date(),
                )
            ).all()
        by_day: dict[str, int] = {}
        for row in rows:
            label = row.work_date.isoformat()
            by_day[label] = by_day.get(label, 0) + int(row.available_people or 0)
        if start.date() == end.date() and start.date().isoformat() not in by_day:
            by_day[start.date().isoformat()] = 0
        return by_day

    def _material_warnings(self, organization_id: str, facility_id: str, snapshot: dict) -> list[dict]:
        requirements = snapshot.get("requirements") or []
        if not requirements:
            return []
        lots = self.repo.list_inventory_lots(organization_id, facility_id)
        reservations = self.repo.list_material_reservations(organization_id, facility_id)
        reserved_by_lot: dict[str, float] = {}
        for reservation in reservations:
            if reservation.status == "reserved":
                reserved_by_lot[reservation.lot_id] = reserved_by_lot.get(reservation.lot_id, 0.0) + float(reservation.quantity or 0.0)

        warnings: list[dict] = []
        order_id = snapshot["order"].id
        for requirement in requirements:
            required = float(requirement.get("quantity") or 0.0)
            product_id = str(requirement.get("product_id") or "")
            current_reserved = sum(
                float(row.quantity or 0.0)
                for row in reservations
                if row.production_order_id == order_id and row.status == "reserved" and next((lot for lot in lots if lot.id == row.lot_id and lot.product_id == product_id), None) is not None
            )
            unreserved = 0.0
            for lot in lots:
                if lot.product_id != product_id or lot.status not in {"available", "released"}:
                    continue
                balance = float(self.repo.inventory_balance(organization_id, lot.id))
                unreserved += max(0.0, balance - reserved_by_lot.get(lot.id, 0.0))
            potential = current_reserved + unreserved
            if potential + 1e-9 < required:
                short = required - potential
                warnings.append(self._warning("material_shortage", "Materials", f"{requirement.get('product_name')}: {short:.2f} {requirement.get('unit')} short. Buyer review required; Production will not create a PO.", severity="blocker"))
            elif current_reserved + 1e-9 < required:
                warnings.append(self._warning("material_unreserved", "Materials", f"{requirement.get('product_name')}: material is available but still needs reservation before the run."))
        return warnings

    @staticmethod
    def _warning(code: str, category: str, message: str, *, severity: str = "warning") -> dict:
        return {"code": code, "category": category, "message": message, "severity": severity}

    @staticmethod
    def _category_matches(required: str, actual: str) -> bool:
        a = required.casefold().strip()
        b = actual.casefold().strip()
        return a in b or b in a

    @staticmethod
    def _preview_key(request: dict, warnings: list[dict]) -> str:
        body = json.dumps({"request": request, "warnings": warnings}, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    @staticmethod
    def _compatible_datetime(value: datetime, comparison: datetime) -> datetime:
        if value.tzinfo is None and comparison.tzinfo is not None:
            return value.replace(tzinfo=comparison.tzinfo)
        if value.tzinfo is not None and comparison.tzinfo is None:
            return value.replace(tzinfo=None)
        return value

    @staticmethod
    def _placement_payload(row: ProductionSchedulePlacement, order: ProductionOrder | None) -> dict:
        return {
            "id": row.id,
            "production_order_id": row.production_order_id,
            "order_number": getattr(order, "order_number", ""),
            "product_name": getattr(order, "product_name", ""),
            "due_at": getattr(order, "due_at", None),
            "priority": getattr(order, "priority", ""),
            "status": getattr(order, "status", ""),
            "version": row.version,
            "scheduled_start_at": row.scheduled_start_at,
            "scheduled_end_at": row.scheduled_end_at,
            "machine_id": row.machine_id,
            "planned_people": row.planned_people,
            "reason": row.reason,
            "active": row.active,
            "created_by": row.created_by,
            "created_at": row.created_at,
        }
