"""Durable, isolated Co-Man seed for the living demo company."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import sessionmaker

from modules.coman.db import create_coman_engine
from modules.coman.models import (
    AuditEvent,
    BomComponent,
    CrewAvailability,
    Customer,
    Facility,
    FacilityMachine,
    HandLaborArea,
    InventoryLot,
    InventoryTransaction,
    MachineModel,
    MaterialReservation,
    Organization,
    Product,
    ProductBom,
    ProductionActual,
    ProductionOrder,
)

DEMO_ORGANIZATION_SLUG = "doobielogic-demo-simulation"
DEMO_FACILITY_CODE = "DEMO-SOUTHCOAST"


def _frame(payload: dict[str, Any], key: str) -> pd.DataFrame:
    value = payload.get(key)
    return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame(value or [])


def _engine(database_url: str | None = None, engine: Engine | None = None) -> Engine:
    return engine or create_coman_engine(database_url)


def _clear_demo_children(session: Any, organization_id: str, facility_id: str) -> None:
    for model in (
        AuditEvent,
        InventoryTransaction,
        MaterialReservation,
        ProductionActual,
        ProductionOrder,
        BomComponent,
        ProductBom,
        InventoryLot,
        CrewAvailability,
        HandLaborArea,
        FacilityMachine,
        Product,
        Customer,
    ):
        column = getattr(model, "organization_id", None)
        if column is not None:
            session.execute(delete(model).where(column == organization_id))


def _ensure_org_and_facility(session: Any, company: dict[str, Any]) -> tuple[Organization, Facility]:
    organization = session.scalar(select(Organization).where(Organization.slug == DEMO_ORGANIZATION_SLUG))
    if organization is None:
        organization = Organization(
            name=str(company.get("company_name") or "DoobieLogic Demo Simulation"),
            slug=DEMO_ORGANIZATION_SLUG,
            active=True,
        )
        session.add(organization)
        session.flush()
    else:
        organization.name = str(company.get("company_name") or organization.name)
        organization.active = True
    facility = session.scalar(
        select(Facility).where(
            Facility.organization_id == organization.id,
            Facility.code == DEMO_FACILITY_CODE,
        )
    )
    if facility is None:
        facility = Facility(
            organization_id=organization.id,
            name=str(company.get("facility_name") or "South Coast Production Campus"),
            code=DEMO_FACILITY_CODE,
            timezone_name="America/New_York",
            active=True,
        )
        session.add(facility)
        session.flush()
    else:
        facility.name = str(company.get("facility_name") or facility.name)
        facility.active = True
    return organization, facility


def ensure_coman_demo_dataset(
    *,
    state: Any,
    actor: str,
    payload: dict[str, Any],
    force: bool = False,
    database_url: str | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    db_engine = _engine(database_url, engine)
    factory = sessionmaker(bind=db_engine, expire_on_commit=False, future=True)
    company = dict(payload.get("company_profile") or {})
    catalog = _frame(payload, "catalog")
    extraction_inventory = _frame(payload, "extraction_inventory")
    as_of = payload.get("as_of_date")
    if not isinstance(as_of, date):
        parsed = pd.to_datetime(as_of, errors="coerce")
        as_of = parsed.date() if pd.notna(parsed) else date.today()

    with factory.begin() as session:
        organization, facility = _ensure_org_and_facility(session, company)
        existing_count = session.scalar(
            select(Product.id).where(Product.organization_id == organization.id).limit(1)
        )
        if existing_count and not force:
            state["active_organization_id"] = organization.id
            state["active_facility_id"] = facility.id
            return {
                "seeded": False,
                "already_present": True,
                "organization_id": organization.id,
                "facility_id": facility.id,
            }
        if force:
            _clear_demo_children(session, organization.id, facility.id)
            session.flush()

        customers: list[Customer] = []
        for idx, name in enumerate(("Harbor Wellness", "Cape Select", "Berkshire Brands"), start=1):
            customer = Customer(
                organization_id=organization.id,
                name=name,
                license_or_registration=f"MR281{idx:03d}",
                contact_name=("Maya Chen", "Luis Pereira", "Jordan Reed")[idx - 1],
                contact_email=f"demo{idx}@example.invalid",
                active=True,
            )
            session.add(customer)
            customers.append(customer)
        session.flush()

        package_product = Product(
            organization_id=organization.id,
            sku="DEMO-PKG-POUCH",
            name="Demo compliant pouch, label, and seal kit",
            item_type="packaging",
            base_unit="unit",
            unit_cost=0.42,
            active=True,
        )
        session.add(package_product)
        session.flush()

        raw_products: list[Product] = []
        raw_lots: list[InventoryLot] = []
        raw_limit = {"small": 8, "medium": 24, "enterprise": 60}.get(str(payload.get("scale")), 24)
        for idx, row in extraction_inventory.head(raw_limit).reset_index(drop=True).iterrows():
            raw = Product(
                organization_id=organization.id,
                sku=f"DEMO-RAW-{idx + 1:04d}",
                name=str(row.get("material_name") or f"Demo cannabis input {idx + 1}"),
                item_type="cannabis",
                base_unit="g",
                unit_cost=float(row.get("cost_per_g") or 0.0),
                active=True,
            )
            session.add(raw)
            session.flush()
            lot = InventoryLot(
                organization_id=organization.id,
                facility_id=facility.id,
                product_id=raw.id,
                lot_code=str(row.get("batch_id_internal") or f"MAT-{idx + 1:04d}"),
                compliance_package_id=str(row.get("metrc_package_id") or ""),
                location_code=str(row.get("storage_location") or "DEMO-VAULT").upper(),
                status="quarantine" if str(row.get("status") or "").casefold() == "quarantine" else "available",
                received_at=datetime.combine(as_of - timedelta(days=10 + idx), datetime.min.time(), tzinfo=timezone.utc),
                notes="Synthetic demo input linked to extraction operations.",
            )
            session.add(lot)
            session.flush()
            session.add(
                InventoryTransaction(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    lot_id=lot.id,
                    transaction_type="receipt",
                    quantity_delta=float(row.get("current_weight_g") or 0.0),
                    unit="g",
                    actor=actor,
                    reason="Living demo opening receipt",
                    reference=str(row.get("metrc_package_id") or ""),
                )
            )
            raw_products.append(raw)
            raw_lots.append(lot)

        finished_products: dict[str, Product] = {}
        product_limit = {"small": 12, "medium": 42, "enterprise": 120}.get(str(payload.get("scale")), 42)
        for idx, row in catalog.head(product_limit).reset_index(drop=True).iterrows():
            sku = str(row.get("sku") or f"DEMO-FG-{idx + 1:04d}").upper()
            product = Product(
                organization_id=organization.id,
                sku=sku,
                name=str(row.get("product_name") or sku),
                item_type="finished_good",
                base_unit="unit",
                unit_cost=float(row.get("unit_cost") or 0.0),
                active=True,
            )
            session.add(product)
            session.flush()
            finished_products[sku] = product
            component = raw_products[idx % len(raw_products)] if raw_products else package_product
            unit_size = max(float(row.get("unit_size_g") or 1.0), 0.1)
            bom = ProductBom(
                organization_id=organization.id,
                output_product_id=product.id,
                version=1,
                output_quantity=1.0,
                expected_loss_pct=3.0,
                active=True,
                notes=f"Demo BOM linked to {row.get('source_extraction_batch') or 'synthetic extraction'}",
            )
            session.add(bom)
            session.flush()
            session.add_all(
                [
                    BomComponent(
                        organization_id=organization.id,
                        bom_id=bom.id,
                        input_product_id=component.id,
                        quantity=unit_size,
                        unit="g" if component.item_type == "cannabis" else component.base_unit,
                        scrap_pct=2.0,
                    ),
                    BomComponent(
                        organization_id=organization.id,
                        bom_id=bom.id,
                        input_product_id=package_product.id,
                        quantity=1.0,
                        unit="unit",
                        scrap_pct=0.5,
                    ),
                ]
            )

        order_rows: list[dict[str, Any]] = []
        if not catalog.empty:
            for _, group in catalog.head(product_limit).groupby("source_production_order", sort=True):
                order_rows.append(group.iloc[0].to_dict())
        statuses = ["complete", "scheduled", "in_progress", "on_hold", "draft"]
        problems = set(payload.get("problems") or [])
        for idx, row in enumerate(order_rows):
            sku = str(row.get("sku") or "").upper()
            product = finished_products.get(sku)
            if product is None:
                continue
            due_at = datetime.combine(as_of + timedelta(days=(idx - 2) * 2), datetime.min.time(), tzinfo=timezone.utc)
            status = statuses[idx % len(statuses)]
            if "machine_downtime" in problems and idx == 1:
                status = "on_hold"
            if "late_po" in problems and idx == 0:
                due_at = datetime.combine(as_of - timedelta(days=5), datetime.min.time(), tzinfo=timezone.utc)
                status = "scheduled"
            external = idx % 4 == 0
            requested = max(100, int(1600 / max(float(row.get("unit_size_g") or 1.0), 0.5)))
            order = ProductionOrder(
                organization_id=organization.id,
                facility_id=facility.id,
                customer_id=customers[idx % len(customers)].id if external else None,
                order_number=str(row.get("source_production_order") or f"DEMO-PO-{idx + 1:05d}"),
                work_type="external" if external else "internal",
                product_name=str(row.get("product_name") or sku),
                sku=sku,
                product_format=str(row.get("category") or "finished good"),
                requested_units=requested,
                due_at=due_at,
                priority="urgent" if due_at.date() < as_of else "normal",
                status=status,
                source_lot_reference=str(row.get("source_extraction_batch") or ""),
                material_owner="customer" if external else "internal",
                packaging_owner="internal",
                notes=json.dumps(
                    {
                        "package_id": row.get("package_id"),
                        "coa_id": row.get("coa_id"),
                        "source_extraction_batch": row.get("source_extraction_batch"),
                    },
                    default=str,
                ),
                created_by=actor,
                updated_by=actor,
            )
            session.add(order)
            session.flush()
            if raw_lots:
                lot = raw_lots[idx % len(raw_lots)]
                session.add(
                    MaterialReservation(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        production_order_id=order.id,
                        lot_id=lot.id,
                        quantity=min(float(requested), 500.0),
                        unit="g",
                        status="reserved" if status not in {"complete", "cancelled"} else "consumed",
                        reserved_by=actor,
                    )
                )
            if status == "complete":
                actual_units = int(requested * 0.97)
                session.add(
                    ProductionActual(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        production_order_id=order.id,
                        actual_units=actual_units,
                        scrap_units=max(1, int(requested * 0.018)),
                        rework_units=max(0, int(requested * 0.008)),
                        actual_machine_hours=round(requested / 720.0, 2),
                        actual_labor_hours=round(requested / 180.0, 2),
                        completed_at=datetime.combine(as_of - timedelta(days=idx + 1), datetime.min.time(), tzinfo=timezone.utc),
                        notes="Synthetic demo production actual.",
                        recorded_by=actor,
                    )
                )
                output_lot = InventoryLot(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    product_id=product.id,
                    lot_code=f"FG-{order.order_number}",
                    compliance_package_id=str(row.get("package_id") or ""),
                    location_code="FINISHED-GOODS",
                    status="available",
                    received_at=datetime.combine(as_of - timedelta(days=idx + 1), datetime.min.time(), tzinfo=timezone.utc),
                    notes=f"Output from {order.order_number}; COA {row.get('coa_id') or ''}",
                )
                session.add(output_lot)
                session.flush()
                session.add(
                    InventoryTransaction(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        lot_id=output_lot.id,
                        production_order_id=order.id,
                        transaction_type="production_output",
                        quantity_delta=actual_units,
                        unit="unit",
                        actor=actor,
                        reason="Living demo production completion",
                        reference=order.order_number,
                    )
                )

        machine_specs = [
            ("DemoWorks", "PouchPro 900", "Packaging", 900.0, 3, "PKG-01", "Pouch Line 1"),
            ("DemoWorks", "RollMaster 1200", "Pre-Roll", 1200.0, 4, "PR-01", "Pre-Roll Line 1"),
        ]
        for manufacturer, model_name, category, rate, crew, asset, display in machine_specs:
            model = session.scalar(
                select(MachineModel).where(
                    MachineModel.manufacturer == manufacturer,
                    MachineModel.model == model_name,
                )
            )
            if model is None:
                model = MachineModel(
                    manufacturer=manufacturer,
                    model=model_name,
                    category=category,
                    operations_json=json.dumps([category]),
                    published_max_rate=rate,
                    rate_unit="units/hour",
                    published_min_operators=crew,
                    published_max_operators=crew + 1,
                    planning_utilization_pct=72.0,
                    source_url="https://example.invalid/demo-machine",
                    active=True,
                )
                session.add(model)
                session.flush()
            session.add(
                FacilityMachine(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    machine_model_id=model.id,
                    asset_code=asset,
                    display_name=display,
                    effective_rate=rate * (0.35 if "machine_downtime" in problems and asset == "PKG-01" else 0.72),
                    rate_unit="units/hour",
                    preferred_crew_size=crew,
                    setup_minutes=30,
                    cleanup_minutes=25,
                    active=not ("machine_downtime" in problems and asset == "PKG-01"),
                )
            )

        session.add(
            HandLaborArea(
                organization_id=organization.id,
                facility_id=facility.id,
                name="Primary Hand Labor Area",
                default_crew_size=5,
                sticker_units_per_person_hour=180.0,
                case_pack_units_per_person_hour=120.0,
                final_cases_per_person_hour=24.0,
                setup_minutes=20,
                cleanup_minutes=15,
                active=True,
            )
        )
        for day_offset in range(14):
            session.add(
                CrewAvailability(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    work_date=as_of + timedelta(days=day_offset),
                    shift_name="Day",
                    available_people=3 if ("labor_shortage" in problems and day_offset < 4) else (3 if day_offset % 5 == 0 else 5),
                    shift_hours=8.0,
                    notes="Synthetic demo capacity plan",
                    updated_by=actor,
                )
            )
        session.add(
            AuditEvent(
                organization_id=organization.id,
                facility_id=facility.id,
                entity_type="demo_dataset",
                entity_id=organization.id,
                action="seeded",
                actor=actor,
                changes_json=json.dumps(
                    {
                        "version": "full-app-simulation-v2",
                        "scale": payload.get("scale"),
                        "as_of_date": as_of.isoformat(),
                        "problems": sorted(problems),
                    }
                ),
            )
        )

    state["active_organization_id"] = organization.id
    state["active_facility_id"] = facility.id
    return {
        "seeded": True,
        "already_present": False,
        "organization_id": organization.id,
        "facility_id": facility.id,
        "products": len(finished_products) + len(raw_products) + 1,
        "orders": len(order_rows),
        "customers": len(customers),
    }


def reset_coman_demo_dataset(
    *, database_url: str | None = None, engine: Engine | None = None
) -> dict[str, Any]:
    db_engine = _engine(database_url, engine)
    factory = sessionmaker(bind=db_engine, expire_on_commit=False, future=True)
    with factory.begin() as session:
        organization = session.scalar(select(Organization).where(Organization.slug == DEMO_ORGANIZATION_SLUG))
        if organization is None:
            return {"deleted": False, "reason": "not_found"}
        facility = session.scalar(
            select(Facility).where(
                Facility.organization_id == organization.id,
                Facility.code == DEMO_FACILITY_CODE,
            )
        )
        if facility is not None:
            _clear_demo_children(session, organization.id, facility.id)
            session.delete(facility)
        session.delete(organization)
    return {"deleted": True}
