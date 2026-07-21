"""Transactional repository for Co-Man records."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    AuditEvent,
    Customer,
    Facility,
    FacilityMachine,
    HandLaborArea,
    MachineModel,
    Organization,
    ProductionOrder,
    ProductionActual,
    utc_now,
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).strip().casefold()).strip("-")
    if not slug:
        raise ValueError("A non-empty organization name is required.")
    return slug


class ComanRepository:
    def __init__(self, engine: Engine):
        self._session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def create_organization(self, name: str, slug: str | None = None) -> Organization:
        organization = Organization(name=str(name).strip(), slug=_slugify(slug or name))
        with self._session_factory.begin() as session:
            session.add(organization)
        return organization

    def create_facility(
        self,
        organization_id: str,
        name: str,
        code: str,
        timezone_name: str = "America/New_York",
    ) -> Facility:
        facility = Facility(
            organization_id=organization_id,
            name=str(name).strip(),
            code=str(code).strip().upper(),
            timezone_name=timezone_name,
        )
        with self._session_factory.begin() as session:
            self._require_organization(session, organization_id)
            session.add(facility)
        return facility

    def create_customer(self, organization_id: str, name: str, **details: Any) -> Customer:
        customer = Customer(
            organization_id=organization_id,
            name=str(name).strip(),
            license_or_registration=str(details.get("license_or_registration") or ""),
            contact_name=str(details.get("contact_name") or ""),
            contact_email=str(details.get("contact_email") or ""),
        )
        with self._session_factory.begin() as session:
            self._require_organization(session, organization_id)
            session.add(customer)
        return customer

    def list_customers(self, organization_id: str, active_only: bool = True) -> list[Customer]:
        with self._session_factory() as session:
            statement = select(Customer).where(Customer.organization_id == organization_id)
            if active_only:
                statement = statement.where(Customer.active.is_(True))
            return list(session.scalars(statement.order_by(Customer.name)))

    def list_machine_models(self, category: str | None = None) -> list[MachineModel]:
        with self._session_factory() as session:
            statement = select(MachineModel).where(MachineModel.active.is_(True))
            if category:
                statement = statement.where(MachineModel.category == category)
            return list(session.scalars(statement.order_by(MachineModel.manufacturer, MachineModel.model)))

    def create_facility_machine(
        self,
        *,
        organization_id: str,
        facility_id: str,
        machine_model_id: str,
        asset_code: str,
        display_name: str,
        effective_rate: float,
        preferred_crew_size: int,
        setup_minutes: int = 0,
        cleanup_minutes: int = 0,
        actor: str,
    ) -> FacilityMachine:
        if float(effective_rate) <= 0:
            raise ValueError("effective_rate must be greater than zero.")
        if int(preferred_crew_size) < 1:
            raise ValueError("preferred_crew_size must be at least one.")
        machine = FacilityMachine(
            organization_id=organization_id,
            facility_id=facility_id,
            machine_model_id=machine_model_id,
            asset_code=str(asset_code).strip().upper(),
            display_name=str(display_name).strip(),
            effective_rate=float(effective_rate),
            rate_unit="units/hour",
            preferred_crew_size=int(preferred_crew_size),
            setup_minutes=max(0, int(setup_minutes)),
            cleanup_minutes=max(0, int(cleanup_minutes)),
        )
        with self._session_factory.begin() as session:
            facility = session.get(Facility, facility_id)
            if not facility or facility.organization_id != organization_id:
                raise ValueError("Facility does not belong to the organization.")
            if not session.get(MachineModel, machine_model_id):
                raise ValueError("Machine model was not found.")
            session.add(machine)
            session.flush()
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="facility_machine",
                    entity_id=machine.id,
                    action="created",
                    actor=actor,
                    changes_json=json.dumps(
                        {
                            "effective_rate": machine.effective_rate,
                            "rate_unit": machine.rate_unit,
                            "preferred_crew_size": machine.preferred_crew_size,
                        }
                    ),
                )
            )
        return machine

    def list_facility_machines(
        self, organization_id: str, facility_id: str, active_only: bool = True
    ) -> list[FacilityMachine]:
        with self._session_factory() as session:
            statement = select(FacilityMachine).where(
                FacilityMachine.organization_id == organization_id,
                FacilityMachine.facility_id == facility_id,
            )
            if active_only:
                statement = statement.where(FacilityMachine.active.is_(True))
            return list(session.scalars(statement.order_by(FacilityMachine.display_name)))

    def ensure_primary_hand_labor_area(self, organization_id: str, facility_id: str) -> HandLaborArea:
        with self._session_factory.begin() as session:
            facility = session.get(Facility, facility_id)
            if not facility or facility.organization_id != organization_id:
                raise ValueError("Facility does not belong to the organization.")
            area = session.scalar(select(HandLaborArea).where(HandLaborArea.organization_id == organization_id, HandLaborArea.facility_id == facility_id, HandLaborArea.name == "Primary Hand Labor Area"))
            if area is None:
                area = HandLaborArea(organization_id=organization_id, facility_id=facility_id, name="Primary Hand Labor Area")
                session.add(area)
                session.flush()
            return area

    def update_hand_labor_area(self, area_id: str, *, organization_id: str, facility_id: str, default_crew_size: int, sticker_units_per_person_hour: float, case_pack_units_per_person_hour: float, final_cases_per_person_hour: float, setup_minutes: int, cleanup_minutes: int, actor: str) -> HandLaborArea:
        rates = [float(sticker_units_per_person_hour), float(case_pack_units_per_person_hour), float(final_cases_per_person_hour)]
        if any(rate <= 0 for rate in rates):
            raise ValueError("All hand-labor rates must be greater than zero.")
        with self._session_factory.begin() as session:
            area = session.get(HandLaborArea, area_id)
            if not area or area.organization_id != organization_id or area.facility_id != facility_id:
                raise ValueError("Hand labor area was not found in this facility.")
            area.default_crew_size = max(1, int(default_crew_size))
            area.sticker_units_per_person_hour, area.case_pack_units_per_person_hour, area.final_cases_per_person_hour = rates
            area.setup_minutes, area.cleanup_minutes = max(0, int(setup_minutes)), max(0, int(cleanup_minutes))
            session.add(AuditEvent(organization_id=organization_id, facility_id=facility_id, entity_type="hand_labor_area", entity_id=area.id, action="rates_updated", actor=actor, changes_json=json.dumps({"crew": area.default_crew_size, "rates": rates})))
            return area

    def create_production_order(
        self,
        *,
        organization_id: str,
        facility_id: str,
        order_number: str,
        work_type: str,
        product_name: str,
        product_format: str,
        requested_units: int,
        actor: str,
        customer_id: str | None = None,
        due_at: datetime | None = None,
        **details: Any,
    ) -> ProductionOrder:
        if work_type not in {"internal", "external"}:
            raise ValueError("work_type must be 'internal' or 'external'.")
        if work_type == "external" and not customer_id:
            raise ValueError("External production orders require a customer.")
        if int(requested_units) < 0:
            raise ValueError("requested_units cannot be negative.")

        order = ProductionOrder(
            organization_id=organization_id,
            facility_id=facility_id,
            customer_id=customer_id,
            order_number=str(order_number).strip(),
            work_type=work_type,
            product_name=str(product_name).strip(),
            sku=str(details.get("sku") or ""),
            product_format=str(product_format).strip(),
            requested_units=int(requested_units),
            due_at=due_at,
            priority=str(details.get("priority") or "normal"),
            status="draft",
            source_lot_reference=str(details.get("source_lot_reference") or ""),
            material_owner=str(details.get("material_owner") or "internal"),
            packaging_owner=str(details.get("packaging_owner") or "internal"),
            notes=str(details.get("notes") or ""),
            created_by=actor,
            updated_by=actor,
        )
        with self._session_factory.begin() as session:
            facility = session.get(Facility, facility_id)
            if not facility or facility.organization_id != organization_id:
                raise ValueError("Facility does not belong to the organization.")
            if customer_id:
                customer = session.get(Customer, customer_id)
                if not customer or customer.organization_id != organization_id:
                    raise ValueError("Customer does not belong to the organization.")
            session.add(order)
            session.flush()
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    facility_id=facility_id,
                    entity_type="production_order",
                    entity_id=order.id,
                    action="created",
                    actor=actor,
                    changes_json=json.dumps({"status": "draft", "requested_units": requested_units}),
                )
            )
        return order

    def list_production_orders(
        self, organization_id: str, facility_id: str | None = None
    ) -> list[ProductionOrder]:
        with self._session_factory() as session:
            statement = select(ProductionOrder).where(
                ProductionOrder.organization_id == organization_id
            )
            if facility_id:
                statement = statement.where(ProductionOrder.facility_id == facility_id)
            return list(session.scalars(statement.order_by(ProductionOrder.created_at.desc())))

    def update_production_order_status(self, order_id: str, *, organization_id: str, facility_id: str, status: str, actor: str) -> ProductionOrder:
        allowed = {"draft", "scheduled", "in_progress", "on_hold", "complete", "cancelled"}
        normalized = str(status).strip().lower()
        if normalized not in allowed:
            raise ValueError("Unsupported production-order status.")
        with self._session_factory.begin() as session:
            order = session.get(ProductionOrder, order_id)
            if not order or order.organization_id != organization_id or order.facility_id != facility_id:
                raise ValueError("Production order was not found in this facility.")
            previous = order.status
            order.status = normalized
            order.updated_by = actor
            session.add(AuditEvent(organization_id=organization_id, facility_id=facility_id, entity_type="production_order", entity_id=order.id, action="status_changed", actor=actor, changes_json=json.dumps({"from": previous, "to": normalized})))
            return order

    def duplicate_production_order(self, order_id: str, *, organization_id: str, facility_id: str, new_order_number: str, actor: str) -> ProductionOrder:
        with self._session_factory() as session:
            source = session.get(ProductionOrder, order_id)
            if not source or source.organization_id != organization_id or source.facility_id != facility_id:
                raise ValueError("Production order was not found in this facility.")
            values = {"customer_id": source.customer_id, "due_at": source.due_at, "sku": source.sku, "priority": source.priority, "source_lot_reference": source.source_lot_reference, "material_owner": source.material_owner, "packaging_owner": source.packaging_owner, "notes": source.notes}
            work_type, product_name, product_format, requested_units = source.work_type, source.product_name, source.product_format, source.requested_units
        return self.create_production_order(organization_id=organization_id, facility_id=facility_id, order_number=new_order_number, work_type=work_type, product_name=product_name, product_format=product_format, requested_units=requested_units, actor=actor, **values)

    def record_production_actual(self, order_id: str, *, organization_id: str, facility_id: str, actual_units: int, scrap_units: int, rework_units: int, actual_machine_hours: float, actual_labor_hours: float, actor: str, completed_at: datetime | None = None, notes: str = "") -> ProductionActual:
        numeric = [int(actual_units), int(scrap_units), int(rework_units)]
        if any(value < 0 for value in numeric) or float(actual_machine_hours) < 0 or float(actual_labor_hours) < 0:
            raise ValueError("Actual production values cannot be negative.")
        with self._session_factory.begin() as session:
            order = session.get(ProductionOrder, order_id)
            if not order or order.organization_id != organization_id or order.facility_id != facility_id:
                raise ValueError("Production order was not found in this facility.")
            actual = session.scalar(select(ProductionActual).where(ProductionActual.production_order_id == order_id))
            if actual is None:
                actual = ProductionActual(organization_id=organization_id, facility_id=facility_id, production_order_id=order_id, recorded_by=actor)
                session.add(actual)
            actual.actual_units, actual.scrap_units, actual.rework_units = numeric
            actual.actual_machine_hours = float(actual_machine_hours)
            actual.actual_labor_hours = float(actual_labor_hours)
            actual.completed_at = completed_at or utc_now()
            actual.notes = str(notes or "")
            actual.recorded_by = actor
            order.status = "complete"
            order.updated_by = actor
            session.flush()
            session.add(AuditEvent(organization_id=organization_id, facility_id=facility_id, entity_type="production_actual", entity_id=actual.id, action="recorded", actor=actor, changes_json=json.dumps({"actual_units": actual.actual_units, "scrap_units": actual.scrap_units, "rework_units": actual.rework_units, "machine_hours": actual.actual_machine_hours, "labor_hours": actual.actual_labor_hours})))
            return actual

    def list_production_actuals(self, organization_id: str, facility_id: str) -> list[ProductionActual]:
        with self._session_factory() as session:
            statement = select(ProductionActual).where(ProductionActual.organization_id == organization_id, ProductionActual.facility_id == facility_id)
            return list(session.scalars(statement.order_by(ProductionActual.completed_at.desc())))

    @staticmethod
    def _require_organization(session: Session, organization_id: str) -> Organization:
        organization = session.get(Organization, organization_id)
        if not organization:
            raise ValueError("Organization was not found.")
        return organization
