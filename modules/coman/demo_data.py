"""Durable, isolated Co-Man seed for the living demo company."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.db import create_coman_engine
from modules.coman.models import (
    AuditEvent,
    BomComponent,
    CommercialOrder,
    CommercialOrderLine,
    CrewAvailability,
    Customer,
    Facility,
    FacilityMachine,
    HandLaborArea,
    InventoryLot,
    InventoryAudit,
    InventoryAuditLine,
    InventoryAuditScan,
    InventoryTransaction,
    MachineModel,
    MaterialReservation,
    Organization,
    OrderLotAllocation,
    Product,
    ProductBom,
    ProductionActual,
    ProductionOrder,
    TradePartner,
)

DEMO_ORGANIZATION_SLUG = "doobielogic-demo-simulation"
DEMO_FACILITY_CODE = "DEMO-SOUTHCOAST"
DEMO_DATA_VERSION = "full-app-simulation-v4-inventory-audits"


def _frame(payload: dict[str, Any], key: str) -> pd.DataFrame:
    value = payload.get(key)
    return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame(value or [])


def _engine(database_url: str | None = None, engine: Engine | None = None) -> Engine:
    return engine or create_coman_engine(database_url)


def _clear_demo_children(session: Any, organization_id: str, facility_id: str) -> None:
    for model in (
        AuditEvent,
        InventoryAuditScan,
        InventoryAuditLine,
        InventoryAudit,
        InventoryTransaction,
        OrderLotAllocation,
        CommercialOrderLine,
        CommercialOrder,
        TradePartner,
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
        existing_seed_event = session.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.organization_id == organization.id,
                AuditEvent.entity_type == "demo_dataset",
                AuditEvent.action == "seeded",
            )
            .order_by(AuditEvent.occurred_at.desc())
        )
        existing_version = ""
        if existing_seed_event is not None:
            try:
                existing_version = str(
                    json.loads(existing_seed_event.changes_json or "{}").get("version")
                    or ""
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                existing_version = ""
        if existing_count and not force and existing_version == DEMO_DATA_VERSION:
            state["active_organization_id"] = organization.id
            state["active_facility_id"] = facility.id
            return {
                "seeded": False,
                "already_present": True,
                "organization_id": organization.id,
                "facility_id": facility.id,
            }
        if existing_count:
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
                external_inventory_id=f"DEMO-DUTCHIE-RAW-{idx + 1:05d}",
                barcode_value=str(row.get("metrc_package_id") or f"DEMO-RAW-QR-{idx + 1:05d}"),
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
        catalog_by_sku: dict[str, dict[str, Any]] = {}
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
                retail_price=round(
                    max(
                        float(row.get("unit_cost") or 0.0) * 2.8,
                        float(row.get("wholesale_price") or 0.0) * 1.9,
                        5.0,
                    ),
                    2,
                ),
                upc=f"8500710{idx + 1:05d}",
                external_product_id=f"DEMO-DUTCHIE-PRODUCT-{idx + 1:05d}",
                active=True,
            )
            session.add(product)
            session.flush()
            finished_products[sku] = product
            catalog_by_sku[sku] = row.to_dict()
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
        finished_lots: dict[str, InventoryLot] = {}
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
                    external_inventory_id=f"DEMO-DUTCHIE-INVENTORY-{idx + 1:05d}",
                    barcode_value=str(row.get("package_id") or f"DEMO-FG-QR-{idx + 1:05d}"),
                    location_code="FINISHED-GOODS",
                    status="available",
                    received_at=datetime.combine(as_of - timedelta(days=idx + 1), datetime.min.time(), tzinfo=timezone.utc),
                    notes=f"Output from {order.order_number}; COA {row.get('coa_id') or ''}",
                )
                session.add(output_lot)
                session.flush()
                finished_lots[product.id] = output_lot
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

        trade_partners: list[TradePartner] = []
        partner_specs = [
            ("Harbor Wellness", "customer", "MR281101", "Maya Chen", "Net 30"),
            ("Cape Select", "customer", "MR281102", "Luis Pereira", "Net 15"),
            ("Berkshire Brands", "customer", "MR281103", "Jordan Reed", "Net 30"),
            ("Atlantic Cultivation", "vendor", "MC281201", "Avery Brooks", "Net 30"),
            ("Pioneer Valley Packaging", "vendor", "SUP-281202", "Sam Rivera", "Net 45"),
        ]
        for idx, (name, partner_type, license_number, contact, terms) in enumerate(
            partner_specs,
            start=1,
        ):
            partner = TradePartner(
                organization_id=organization.id,
                name=name,
                partner_type=partner_type,
                license_or_registration=license_number,
                contact_name=contact,
                contact_email=f"commercial{idx}@example.invalid",
                contact_phone=f"508-555-{1200 + idx:04d}",
                payment_terms=terms,
                active=True,
            )
            session.add(partner)
            trade_partners.append(partner)
        session.flush()

        sales_customers = [
            partner for partner in trade_partners if partner.partner_type == "customer"
        ]
        vendors = [
            partner for partner in trade_partners if partner.partner_type == "vendor"
        ]
        sellable = [
            (product, finished_lots.get(product.id))
            for product in finished_products.values()
            if finished_lots.get(product.id) is not None
        ]
        commercial_order_count = 0
        commercial_transaction_count = 0
        sales_statuses = [
            ("confirmed", "sent", 0.0),
            ("allocated", "sent", 0.0),
            ("partially_fulfilled", "partial", 0.5),
            ("fulfilled", "paid", 1.0),
        ]
        for idx, (status, payment_status, fulfillment_ratio) in enumerate(
            sales_statuses
        ):
            if not sellable:
                break
            product, lot = sellable[idx % len(sellable)]
            catalog_row = catalog_by_sku.get(product.sku, {})
            unit_cost = float(product.unit_cost or 0.0)
            wholesale_price = float(catalog_row.get("wholesale_price") or 0.0)
            unit_price = round(max(unit_cost * 1.60, wholesale_price), 2)
            quantity = float(12 + idx * 3)
            due_date = as_of + timedelta(days=idx - 1)
            order = CommercialOrder(
                organization_id=organization.id,
                facility_id=facility.id,
                partner_id=sales_customers[idx % len(sales_customers)].id,
                order_number=f"SO-DEMO-{idx + 1:04d}",
                order_type="sales",
                order_date=as_of - timedelta(days=idx + 2),
                due_at=datetime.combine(
                    due_date,
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                ),
                status=status,
                payment_status=payment_status,
                currency="USD",
                external_reference=f"CUSTOMER-PO-{7100 + idx}",
                notes=json.dumps(
                    {
                        "synthetic_demo": True,
                        "unit_cost": unit_cost,
                        "gross_margin_pct": round(
                            (unit_price - unit_cost) / unit_price * 100.0,
                            2,
                        )
                        if unit_price
                        else 0.0,
                    }
                ),
                created_by=actor,
                updated_by=actor,
            )
            session.add(order)
            session.flush()
            fulfilled_quantity = round(quantity * fulfillment_ratio, 2)
            line = CommercialOrderLine(
                organization_id=organization.id,
                commercial_order_id=order.id,
                product_id=product.id,
                position=1,
                description=product.name,
                sku_snapshot=product.sku,
                quantity=quantity,
                unit="unit",
                unit_price=unit_price,
                fulfilled_quantity=fulfilled_quantity,
                notes="Profitable synthetic wholesale line.",
            )
            session.add(line)
            session.flush()
            if status in {"allocated", "partially_fulfilled", "fulfilled"}:
                allocation = OrderLotAllocation(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    commercial_order_id=order.id,
                    commercial_order_line_id=line.id,
                    lot_id=lot.id,
                    quantity=quantity,
                    fulfilled_quantity=fulfilled_quantity,
                    status=(
                        "fulfilled"
                        if status == "fulfilled"
                        else ("partial" if status == "partially_fulfilled" else "reserved")
                    ),
                    reserved_by=actor,
                )
                session.add(allocation)
            if fulfilled_quantity > 0:
                session.add(
                    InventoryTransaction(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        lot_id=lot.id,
                        transaction_type="shipment",
                        quantity_delta=-fulfilled_quantity,
                        unit="unit",
                        commercial_order_id=order.id,
                        commercial_order_line_id=line.id,
                        actor=actor,
                        reason="Living demo sales fulfillment",
                        reference=order.order_number,
                    )
                )
                commercial_transaction_count += 1
            commercial_order_count += 1

        packaging_receipt_lot: InventoryLot | None = None
        for idx, vendor in enumerate(vendors):
            status = "confirmed" if idx == 0 else "partially_fulfilled"
            received_quantity = 0.0 if idx == 0 else 600.0
            order = CommercialOrder(
                organization_id=organization.id,
                facility_id=facility.id,
                partner_id=vendor.id,
                order_number=f"PO-DEMO-{idx + 1:04d}",
                order_type="purchase",
                order_date=as_of - timedelta(days=4 + idx),
                due_at=datetime.combine(
                    as_of + timedelta(days=2 + idx),
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                ),
                status=status,
                payment_status="sent",
                currency="USD",
                external_reference=f"VENDOR-ACK-{8200 + idx}",
                notes="Synthetic packaging replenishment with complete landed-cost fields.",
                created_by=actor,
                updated_by=actor,
            )
            session.add(order)
            session.flush()
            line = CommercialOrderLine(
                organization_id=organization.id,
                commercial_order_id=order.id,
                product_id=package_product.id,
                position=1,
                description=package_product.name,
                sku_snapshot=package_product.sku,
                quantity=2400.0,
                unit="unit",
                unit_price=float(package_product.unit_cost or 0.0),
                fulfilled_quantity=received_quantity,
                notes="Pouch, label, seal, and compliance-sticker kit.",
            )
            session.add(line)
            session.flush()
            if received_quantity > 0:
                packaging_receipt_lot = InventoryLot(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    product_id=package_product.id,
                    lot_code=f"PKG-RECEIPT-{idx + 1:04d}",
                    compliance_package_id="",
                    location_code="PACKAGING-CAGE",
                    status="available",
                    received_at=datetime.combine(
                        as_of - timedelta(days=1),
                        datetime.min.time(),
                        tzinfo=timezone.utc,
                    ),
                    expiration_at=None,
                    notes="Synthetic commercial purchase receipt.",
                )
                session.add(packaging_receipt_lot)
                session.flush()
                session.add(
                    InventoryTransaction(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        lot_id=packaging_receipt_lot.id,
                        transaction_type="receipt",
                        quantity_delta=received_quantity,
                        unit="unit",
                        commercial_order_id=order.id,
                        commercial_order_line_id=line.id,
                        actor=actor,
                        reason="Living demo purchase receipt",
                        reference=order.order_number,
                    )
                )
                commercial_transaction_count += 1
            commercial_order_count += 1

        machine_specs = [
            ("IMA", "Pre-roll line facility benchmark", "Pre-Roll", 720.0, 4, "PR-IMA-01", "IMA Pre-Roll Line"),
            ("Massman", "Flower pouch facility benchmark", "Packaging", 650.0, 3, "PKG-MASS-01", "Massman Flower Pouch Line"),
            ("Ishida", "Multihead weigh-pack benchmark", "Secondary Packaging", 900.0, 3, "PKG-ISH-01", "Ishida Pre-Roll Pack Line"),
            ("Vape-Jet", "Cartridge filling benchmark", "Vape Filling", 540.0, 2, "VAPE-JET-01", "Vape-Jet Filling Line"),
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
                    effective_rate=rate * (0.35 if "machine_downtime" in problems and asset == "PKG-MASS-01" else 0.72),
                    rate_unit="units/hour",
                    preferred_crew_size=crew,
                    setup_minutes=30,
                    cleanup_minutes=25,
                    active=not ("machine_downtime" in problems and asset == "PKG-MASS-01"),
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

        audit_count = 0
        if sellable:
            retail_product, retail_lot = sellable[0]
            expected = float(
                session.scalar(
                    select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                        InventoryTransaction.lot_id == retail_lot.id
                    )
                )
                or 0.0
            )
            retail_audit = InventoryAudit(
                organization_id=organization.id,
                facility_id=facility.id,
                audit_number="RTL-DEMO-COMPLETE",
                status="completed",
                operation_type="retail",
                blind_count=True,
                recount_tolerance=0.0,
                scope_label="Sales floor and secure backstock",
                started_at=datetime.combine(as_of - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc),
                completed_at=datetime.combine(as_of - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=2),
                created_by="demo.retail.counter",
                completed_by="demo.inventory.manager",
                notes="Synthetic profitable retail count with a resolved first-pass variance.",
            )
            session.add(retail_audit)
            session.flush()
            retail_line = InventoryAuditLine(
                organization_id=organization.id,
                facility_id=facility.id,
                audit_id=retail_audit.id,
                lot_id=retail_lot.id,
                expected_quantity=expected,
                first_count_quantity=max(0.0, expected - 1.0),
                recount_quantity=expected,
                counted_quantity=expected,
                variance_quantity=0.0,
                recount_required=False,
                unit="unit",
                reason="First count entry correction",
                notes="Recount confirmed the ledger quantity.",
                counted_by="demo.retail.recounter",
                counted_at=retail_audit.completed_at,
            )
            session.add(retail_line)
            session.flush()
            scan_code = retail_lot.barcode_value or retail_lot.compliance_package_id or retail_product.upc
            session.add_all(
                [
                    InventoryAuditScan(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        audit_id=retail_audit.id,
                        audit_line_id=retail_line.id,
                        raw_code=scan_code,
                        normalized_code=scan_code.upper(),
                        match_status="matched",
                        scan_stage="first_count",
                        scanned_by="demo.retail.counter",
                        scanned_at=retail_audit.started_at + timedelta(minutes=12),
                    ),
                    InventoryAuditScan(
                        organization_id=organization.id,
                        facility_id=facility.id,
                        audit_id=retail_audit.id,
                        audit_line_id=retail_line.id,
                        raw_code=scan_code,
                        normalized_code=scan_code.upper(),
                        match_status="matched",
                        scan_stage="recount",
                        scanned_by="demo.retail.recounter",
                        scanned_at=retail_audit.completed_at - timedelta(minutes=18),
                    ),
                ]
            )
            audit_count += 1
        if raw_lots:
            production_lot = raw_lots[0]
            production_expected = float(
                session.scalar(
                    select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                        InventoryTransaction.lot_id == production_lot.id
                    )
                )
                or 0.0
            )
            production_audit = InventoryAudit(
                organization_id=organization.id,
                facility_id=facility.id,
                audit_number="PROD-DEMO-ACTIVE",
                status="in_progress",
                operation_type="production",
                blind_count=True,
                recount_tolerance=0.5,
                scope_label="Bulk vault cycle count",
                created_by="demo.production.counter",
                notes="Active synthetic bulk-weight count ready for phone scanning.",
            )
            session.add(production_audit)
            session.flush()
            session.add(
                InventoryAuditLine(
                    organization_id=organization.id,
                    facility_id=facility.id,
                    audit_id=production_audit.id,
                    lot_id=production_lot.id,
                    expected_quantity=max(0.0, production_expected),
                    unit="g",
                )
            )
            audit_count += 1
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
                        "version": DEMO_DATA_VERSION,
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
        "trade_partners": len(trade_partners),
        "commercial_orders": commercial_order_count,
        "commercial_transactions": commercial_transaction_count,
        "inventory_audits": audit_count,
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
