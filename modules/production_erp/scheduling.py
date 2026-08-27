"""Capacity-aware production schedule previews and versioned placement commits."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import CrewAvailability, FacilityMachine, MachineModel, ProductionOrder
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

        resource_category = str(
            variance.get("resource_category")
            or getattr(standard, "resource_category", "")
            or ""
        ).strip()
        machine_category = self._machine_category(machine) if machine is not None else ""
        if resource_category:
            if machine is None:
                warnings.append(
                    self._warning(
                        "machine_required",
                        "Equipment",
                        f"BOM standard calls for {resource_category}, but no machine is assigned.",
                    )
                )
            elif machine_category and not self._category_matches(resource_category, machine_category):
                warnings.append(
                    self._warning(
                        "machine_category",
                        "Equipment",
                        f"Assigned machine category {machine_category} does not match the BOM standard {resource_category}.",
                    )
                )

        overlaps: list[dict] = []
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
                warnings.append(
                    self._warning(
                        "machine_overlap",
                        "Equipment",
                        f"Machine is already scheduled for {labels} during this window.",
                        severity="blocker",
                    )
                )

        expected_cycle = float(variance.get("expected_cycle_hours") or 0.0)
        window_hours = (scheduled_end_at - scheduled_start_at).total_seconds() / 3600.0
        if expected_cycle > 0 and window_hours + 1e-9 < expected_cycle:
            warnings.append(
                self._warning(
                    "cycle_time",
                    "Capacity",
                    f"Scheduled window is {window_hours:.2f} hr, below the BOM standard of {expected_cycle:.2f} hr.",
                )
            )

        expected_labor = float(variance.get("expected_labor_hours") or 0.0)
        crew = self._crew_capacity(organization_id, facility_id, scheduled_start_at, scheduled_end_at)
        window_by_day = self._window_hours_by_day(scheduled_start_at, scheduled_end_at)
        planned_labor_capacity = planned_people * window_hours
        available_labor_capacity = sum(
            float(crew.get(day, {}).get("person_hours") or 0.0) for day in window_by_day
        )

        if planned_people == 0 and expected_labor > 0:
            suggested_people = max(1, math.ceil(expected_labor / max(window_hours, 0.01)))
            warnings.append(
                self._warning(
                    "crew_unassigned",
                    "Labor",
                    f"No crew is assigned. Based on {expected_labor:.2f} standard labor hours, consider at least {suggested_people} people for this window.",
                )
            )
        elif expected_labor > planned_labor_capacity + 1e-9:
            warnings.append(
                self._warning(
                    "crew_underplanned",
                    "Labor",
                    f"The assigned crew provides {planned_labor_capacity:.2f} person-hours, below the BOM standard of {expected_labor:.2f}.",
                )
            )

        for day_label, scheduled_hours in window_by_day.items():
            required_person_hours = planned_people * scheduled_hours
            available_person_hours = float(crew.get(day_label, {}).get("person_hours") or 0.0)
            if planned_people > 0 and required_person_hours > available_person_hours + 1e-9:
                warnings.append(
                    self._warning(
                        "crew_capacity",
                        "Labor",
                        f"{day_label} needs {required_person_hours:.2f} planned person-hours, but only {available_person_hours:.2f} are scheduled as available.",
                        severity="blocker",
                    )
                )

        if expected_labor > 0 and available_labor_capacity + 1e-9 < min(
            expected_labor, planned_labor_capacity or expected_labor
        ):
            warnings.append(
                self._warning(
                    "facility_labor_capacity",
                    "Labor",
                    f"Scheduled crew availability provides {available_labor_capacity:.2f} person-hours across this window versus {expected_labor:.2f} standard labor hours.",
                    severity="blocker",
                )
            )

        if order.due_at is not None and scheduled_end_at > self._compatible_datetime(
            order.due_at, scheduled_end_at
        ):
            warnings.append(
                self._warning(
                    "due_date",
                    "Due date",
                    "The proposed schedule finishes after the production order due date.",
                )
            )

        material_warnings, material_state = self._material_assessment(
            organization_id, facility_id, snapshot
        )
        warnings.extend(material_warnings)

        qa_events = snapshot.get("qa_events") or []
        latest_qa = max(qa_events, key=lambda row: row.occurred_at) if qa_events else None
        if latest_qa is not None:
            if latest_qa.event_type in {"hold", "fail"} or latest_qa.result == "failed":
                warnings.append(
                    self._warning(
                        "qa_hold",
                        "QA",
                        "This run is currently under a QA hold/failure and should not be scheduled as release-ready.",
                        severity="blocker",
                    )
                )

        if bool(variance.get("qa_required")) and not bool(variance.get("qa_ready")):
            warnings.append(
                self._warning(
                    "qa_required",
                    "QA",
                    "The BOM standard requires QA before finished output release.",
                )
            )
        checkpoint = str(variance.get("compliance_checkpoint") or "").strip()
        if checkpoint:
            warnings.append(
                self._warning(
                    "compliance_checkpoint",
                    "Compliance",
                    f"Required checkpoint: {checkpoint}",
                    severity="info",
                )
            )

        run_events = snapshot.get("events") or []
        latest_run_event = max(run_events, key=lambda row: row.occurred_at) if run_events else None
        operational_state = {
            "order": {
                "status": order.status,
                "priority": order.priority,
                "due_at": order.due_at,
                "updated_at": getattr(order, "updated_at", None),
                "actual_output": snapshot.get("actual_output"),
                "attainment_pct": snapshot.get("attainment_pct"),
            },
            "current_placement": None
            if current is None
            else {
                "id": current.id,
                "version": current.version,
                "start": current.scheduled_start_at,
                "end": current.scheduled_end_at,
                "machine_id": current.machine_id,
                "planned_people": current.planned_people,
            },
            "standard": {
                "expected_cycle_hours": expected_cycle,
                "expected_labor_hours": expected_labor,
                "expected_machine_hours": float(variance.get("expected_machine_hours") or 0.0),
                "resource_category": resource_category,
                "qa_required": bool(variance.get("qa_required")),
                "qa_ready": bool(variance.get("qa_ready")),
                "compliance_checkpoint": checkpoint,
                "standard_configured": bool(variance.get("standard_configured")),
            },
            "machine": None
            if machine is None
            else {
                "id": machine.id,
                "machine_model_id": machine.machine_model_id,
                "category": machine_category,
                "effective_rate": machine.effective_rate,
                "preferred_crew_size": machine.preferred_crew_size,
                "active": machine.active,
                "updated_at": getattr(machine, "updated_at", None),
            },
            "machine_overlaps": overlaps,
            "crew": crew,
            "materials": material_state,
            "latest_qa": None
            if latest_qa is None
            else {
                "id": latest_qa.id,
                "event_type": latest_qa.event_type,
                "result": latest_qa.result,
                "occurred_at": latest_qa.occurred_at,
            },
            "latest_run_event": None
            if latest_run_event is None
            else {
                "id": latest_run_event.id,
                "event_type": latest_run_event.event_type,
                "occurred_at": latest_run_event.occurred_at,
            },
        }
        state_fingerprint = self._state_fingerprint(operational_state)

        request = {
            "order_id": order_id,
            "scheduled_start_at": scheduled_start_at.isoformat(),
            "scheduled_end_at": scheduled_end_at.isoformat(),
            "machine_id": machine_id or "",
            "planned_people": int(planned_people),
            "reason": reason.strip(),
            "current_version": current.version if current is not None else 0,
            "state_fingerprint": state_fingerprint,
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
        # Serialize schedule mutations for the same run before re-running preflight.
        # This closes the race where two planners could otherwise commit the same preview.
        with Session(self.engine) as session:
            locked_order = session.scalar(
                select(ProductionOrder)
                .where(
                    ProductionOrder.id == order_id,
                    ProductionOrder.organization_id == organization_id,
                    ProductionOrder.facility_id == facility_id,
                )
                .with_for_update()
            )
            if locked_order is None:
                raise ValueError("Production order was not found in this facility.")

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
                raise ValueError(
                    "Schedule preview is stale. Review the conflicts again before committing this placement."
                )
            actionable = [row for row in preview["warnings"] if row["severity"] != "info"]
            if actionable and not accept_warnings:
                raise ValueError(
                    "Review and acknowledge the schedule warnings before committing this placement."
                )

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
                .where(
                    ProductionSchedulePlacement.organization_id == organization_id,
                    ProductionSchedulePlacement.facility_id == facility_id,
                    ProductionSchedulePlacement.production_order_id == order_id,
                )
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
            return self._placement_payload(row, locked_order)

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

    def _machine_overlaps(
        self,
        *,
        organization_id: str,
        facility_id: str,
        machine_id: str,
        order_id: str,
        start: datetime,
        end: datetime,
    ) -> list[dict]:
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
                .order_by(ProductionSchedulePlacement.scheduled_start_at.asc())
            ).all()
            return [
                {
                    "placement_id": placement.id,
                    "version": placement.version,
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "scheduled_start_at": placement.scheduled_start_at,
                    "scheduled_end_at": placement.scheduled_end_at,
                }
                for placement, order in rows
            ]

    def _crew_capacity(
        self, organization_id: str, facility_id: str, start: datetime, end: datetime
    ) -> dict[str, dict]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(CrewAvailability).where(
                    CrewAvailability.organization_id == organization_id,
                    CrewAvailability.facility_id == facility_id,
                    CrewAvailability.work_date >= start.date(),
                    CrewAvailability.work_date <= (end - timedelta(microseconds=1)).date(),
                )
            ).all()

        by_day: dict[str, dict] = {}
        for row in rows:
            label = row.work_date.isoformat()
            state = by_day.setdefault(
                label, {"people": 0, "person_hours": 0.0, "shifts": []}
            )
            state["people"] += int(row.available_people or 0)
            state["person_hours"] += float(row.available_people or 0) * float(row.shift_hours or 0.0)
            state["shifts"].append(
                {
                    "id": row.id,
                    "name": row.shift_name,
                    "people": int(row.available_people or 0),
                    "hours": float(row.shift_hours or 0.0),
                    "updated_at": getattr(row, "updated_at", None),
                }
            )

        for day_label in self._window_hours_by_day(start, end):
            by_day.setdefault(day_label, {"people": 0, "person_hours": 0.0, "shifts": []})
        return by_day

    @staticmethod
    def _window_hours_by_day(start: datetime, end: datetime) -> dict[str, float]:
        by_day: dict[str, float] = {}
        cursor = start
        while cursor < end:
            next_day = (cursor + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            segment_end = min(end, next_day)
            by_day[cursor.date().isoformat()] = (
                segment_end - cursor
            ).total_seconds() / 3600.0
            cursor = segment_end
        return by_day

    def _material_assessment(
        self, organization_id: str, facility_id: str, snapshot: dict
    ) -> tuple[list[dict], list[dict]]:
        requirements = snapshot.get("requirements") or []
        if not requirements:
            return [], []

        lots = self.repo.list_inventory_lots(organization_id, facility_id)
        reservations = self.repo.list_material_reservations(organization_id, facility_id)
        relevant_product_ids = {
            str(requirement.get("product_id") or "") for requirement in requirements
        }
        relevant_lots = [lot for lot in lots if lot.product_id in relevant_product_ids]
        lot_by_id = {lot.id: lot for lot in relevant_lots}

        reserved_by_lot: dict[str, float] = {}
        for reservation in reservations:
            if reservation.status == "reserved" and reservation.lot_id in lot_by_id:
                reserved_by_lot[reservation.lot_id] = (
                    reserved_by_lot.get(reservation.lot_id, 0.0)
                    + float(reservation.quantity or 0.0)
                )

        balances = {
            lot.id: float(self.repo.inventory_balance(organization_id, lot.id))
            for lot in relevant_lots
        }
        warnings: list[dict] = []
        state_rows: list[dict] = []
        order_id = snapshot["order"].id

        for requirement in requirements:
            required = float(requirement.get("quantity") or 0.0)
            product_id = str(requirement.get("product_id") or "")
            product_lots = [lot for lot in relevant_lots if lot.product_id == product_id]
            product_lot_ids = {lot.id for lot in product_lots}
            current_reserved = sum(
                float(row.quantity or 0.0)
                for row in reservations
                if row.production_order_id == order_id
                and row.status == "reserved"
                and row.lot_id in product_lot_ids
            )
            unreserved = sum(
                max(0.0, balances.get(lot.id, 0.0) - reserved_by_lot.get(lot.id, 0.0))
                for lot in product_lots
                if lot.status in {"available", "released"}
            )
            potential = current_reserved + unreserved

            lot_state = [
                {
                    "id": lot.id,
                    "status": lot.status,
                    "balance": round(balances.get(lot.id, 0.0), 6),
                    "reserved": round(reserved_by_lot.get(lot.id, 0.0), 6),
                }
                for lot in sorted(product_lots, key=lambda item: item.id)
            ]
            state_rows.append(
                {
                    "product_id": product_id,
                    "required": round(required, 6),
                    "current_reserved": round(current_reserved, 6),
                    "available_unreserved": round(unreserved, 6),
                    "potential": round(potential, 6),
                    "lots": lot_state,
                }
            )

            if potential + 1e-9 < required:
                short = required - potential
                warnings.append(
                    self._warning(
                        "material_shortage",
                        "Materials",
                        f"{requirement.get('product_name')}: {short:.2f} {requirement.get('unit')} short. Buyer review required; Production will not create a PO.",
                        severity="blocker",
                    )
                )
            elif current_reserved + 1e-9 < required:
                warnings.append(
                    self._warning(
                        "material_unreserved",
                        "Materials",
                        f"{requirement.get('product_name')}: material is available but still needs reservation before the run.",
                    )
                )

        return warnings, sorted(state_rows, key=lambda row: row["product_id"])

    @staticmethod
    def _warning(
        code: str, category: str, message: str, *, severity: str = "warning"
    ) -> dict:
        return {
            "code": code,
            "category": category,
            "message": message,
            "severity": severity,
        }

    @staticmethod
    def _category_matches(required: str, actual: str) -> bool:
        a = required.casefold().strip()
        b = actual.casefold().strip()
        return a in b or b in a

    @staticmethod
    def _state_fingerprint(state: dict) -> str:
        body = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    @staticmethod
    def _preview_key(request: dict, warnings: list[dict]) -> str:
        body = json.dumps(
            {"request": request, "warnings": warnings},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    @staticmethod
    def _compatible_datetime(value: datetime, comparison: datetime) -> datetime:
        if value.tzinfo is None and comparison.tzinfo is not None:
            return value.replace(tzinfo=comparison.tzinfo)
        if value.tzinfo is not None and comparison.tzinfo is None:
            return value.replace(tzinfo=None)
        return value

    @staticmethod
    def _placement_payload(
        row: ProductionSchedulePlacement, order: ProductionOrder | None
    ) -> dict:
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
