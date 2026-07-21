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
    MachineModel,
    Organization,
    ProductionOrder,
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

    @staticmethod
    def _require_organization(session: Session, organization_id: str) -> Organization:
        organization = session.get(Organization, organization_id)
        if not organization:
            raise ValueError("Organization was not found.")
        return organization
