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
                        status="reserved" if status not in {"complete", "cancelled"} else "consÛžú¶‰žËkºwµçqå}™Õ±™¥±±•ˆ•±Í”€‰É•Í•ÉÙ•ˆ¤(€€€€€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€€€€€É•Í•ÉÙ•‘}‰äõ…Ñ½È°(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡…±±½…Ñ¥½¸¤(€€€€€€€€€€€¥˜™Õ±™¥±±•‘}ÅÕ…¹Ñ¥Ñä€ø€Àè(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘ (€€€€€€€€€€€€€€€€€€€%¹Ù•¹Ñ½ÉåQÉ…¹Í…Ñ¥½¸ (€€€€€€€€€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°(€€€€€€€€€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°(€€€€€€€€€€€€€€€€€€€€€€€±½Ñ}¥õ±½Ð¹¥°(€€€€€€€€€€€€€€€€€€€€€€€ÑÉ…¹Í…Ñ¥½¹}ÑåÁ”ô‰Í¡¥Áµ•¹Ðˆ°(€€€€€€€€€€€€€€€€€€€€€€€ÅÕ…¹Ñ¥Ñå}‘•±Ñ„ôµ™Õ±™¥±±•‘}ÅÕ…¹Ñ¥Ñä°(€€€€€€€€€€€€€€€€€€€€€€€Õ¹¥Ðô‰Õ¹¥Ðˆ°(€€€€€€€€€€€€€€€€€€€€€€€½µµ•É¥…±}½É‘•É}¥õ½É‘•È¹¥°(€€€€€€€€€€€€€€€€€€€€€€€½µµ•É¥…±}½É‘•É}±¥¹•}¥õ±¥¹”¹¥°(€€€€€€€€€€€€€€€€€€€€€€€…Ñ½Èõ…Ñ½È°(€€€€€€€€€€€€€€€€€€€€€€€É•…Í½¸ô‰1¥Ù¥¹œ‘•µ¼Í…±•Ì™Õ±™¥±±µ•¹Ðˆ°(€€€€€€€€€€€€€€€€€€€€€€€É•™•É•¹”õ½É‘•È¹½É‘•É}¹Õµ‰•È°(€€€€€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€½µµ•É¥…±}ÑÉ…¹Í…Ñ¥½¹}½Õ¹Ð€¬ô€Ä(€€€€€€€€€€€½µµ•É¥…±}½É‘•É}½Õ¹Ð€¬ô€Ä((€€€€€€€Á…­…¥¹}É••¥ÁÑ}±½Ðè%¹Ù•¹Ñ½Éå1½Ðð9½¹”€ô9½¹”(€€€€€€€™½È¥‘à°Ù•¹‘½È¥¸•¹Õµ•É…Ñ”¡Ù•¹‘½ÉÌ¤è(€€€€€€€€€€€ÍÑ…ÑÕÌ€ô€‰½¹™¥Éµ•ˆ¥˜¥‘à€ôô€À•±Í”€‰Á…ÉÑ¥…±±å}™Õ±™¥±±•ˆ(€€€€€€€€€€€É••¥Ù•‘}ÅÕ…¹Ñ¥Ñä€ô€À¸À¥˜¥‘à€ôô€À•±Í”€ØÀÀ¸À(€€€€€€€€€€€½É‘•È€ô½µµ•É¥…±=É‘•È (€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°(€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°(€€€€€€€€€€€€€€€Á…ÉÑ¹•É}¥õÙ•¹‘½È¹¥°(€€€€€€€€€€€€€€€½É‘•É}¹Õµ‰•Èõ˜‰A<µ5<µí¥‘à€¬€ÄèÀÑ‘ôˆ°(€€€€€€€€€€€€€€€½É‘•É}ÑåÁ”ô‰ÁÕÉ¡…Í”ˆ°(€€€€€€€€€€€€€€€½É‘•É}‘…Ñ”õ…Í}½˜€´Ñ¥µ•‘•±Ñ„¡‘…åÌôÐ€¬¥‘à¤°(€€€€€€€€€€€€€€€‘Õ•}…Ðõ‘…Ñ•Ñ¥µ”¹½µ‰¥¹” (€€€€€€€€€€€€€€€€€€€…Í}½˜€¬Ñ¥µ•‘•±Ñ„¡‘…åÌôÈ€¬¥‘à¤°(€€€€€€€€€€€€€€€€€€€‘…Ñ•Ñ¥µ”¹µ¥¸¹Ñ¥µ” ¤°(€€€€€€€€€€€€€€€€€€€Ñé¥¹™¼õÑ¥µ•é½¹”¹ÕÑŒ°(€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€ÍÑ…ÑÕÌõÍÑ…ÑÕÌ°(€€€€€€€€€€€€€€€Á…åµ•¹Ñ}ÍÑ…ÑÕÌô‰Í•¹Ðˆ°(€€€€€€€€€€€€€€€ÕÉÉ•¹äô‰UMˆ°(€€€€€€€€€€€€€€€•áÑ•É¹…±}É•™•É•¹”õ˜‰Y9=Hµ,µìàÈÀÀ€¬¥‘áôˆ°(€€€€€€€€€€€€€€€¹½Ñ•Ìô‰Må¹Ñ¡•Ñ¥ŒÁ…­…¥¹œÉ•Á±•¹¥Í¡µ•¹ÐÝ¥Ñ ½µÁ±•Ñ”±…¹‘•µ½ÍÐ™¥•±‘Ì¸ˆ°(€€€€€€€€€€€€€€€É•…Ñ•‘}‰äõ…Ñ½È°(€€€€€€€€€€€€€€€ÕÁ‘…Ñ•‘}‰äõ…Ñ½È°(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡½É‘•È¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹™±ÕÍ  ¤(€€€€€€€€€€€±¥¹”€ô½µµ•É¥…±=É‘•É1¥¹” (€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°(€€€€€€€€€€€€€€€½µµ•É¥…±}½É‘•É}¥õ½É‘•È¹¥°(€€€€€€€€€€€€€€€ÁÉ½‘ÕÑ}¥õÁ…­…•}ÁÉ½‘ÕÐ¹¥°(€€€€€€€€€€€€€€€Á½Í¥Ñ¥½¸ôÄ°(€€€€€€€€€€€€€€€‘•ÍÉ¥ÁÑ¥½¸õÁ…­…•}ÁÉ½‘ÕÐ¹¹…µ”°(€€€€€€€€€€€€€€€Í­Õ}Í¹…ÁÍ¡½ÐõÁ…­…•}ÁÉ½‘ÕÐ¹Í­Ô°(€€€€€€€€€€€€€€€ÅÕ…¹Ñ¥ÑäôÈÐÀÀ¸À°(€€€€€€€€€€€€€€€Õ¹¥Ðô‰Õ¹¥Ðˆ°(€€€€€€€€€€€€€€€Õ¹¥Ñ}ÁÉ¥”õ™±½…Ð¡Á…­…•}ÁÉ½‘ÕÐ¹Õ¹¥Ñ}½ÍÐ½È€À¸À¤°(€€€€€€€€€€€€€€€™Õ±™¥±±•‘}ÅÕ…¹Ñ¥ÑäõÉ••¥Ù•‘}ÅÕ…¹Ñ¥Ñä°(€€€€€€€€€€€€€€€¹½Ñ•Ìô‰A½Õ °±…‰•°°Í•…°°…¹½µÁ±¥…¹”µÍÑ¥­•È­¥Ð¸ˆ°(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡±¥¹”¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹™±ÕÍ  ¤(€€€€€€€€€€€¥˜É••¥Ù•‘}ÅÕ…¹Ñ¥Ñä€ø€Àè(€€€€€€€€€€€€€€€Á…­…¥¹}É••¥ÁÑ}±½Ð€ô%¹Ù•¹Ñ½Éå1½Ð (€€€€€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°(€€€€€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°(€€€€€€€€€€€€€€€€€€€ÁÉ½‘ÕÑ}¥õÁ…­…•}ÁÉ½‘ÕÐ¹¥°(€€€€€€€€€€€€€€€€€€€±½Ñ}½‘”õ˜‰A-µI%APµí¥‘à€¬€ÄèÀÑ‘ôˆ°(€€€€€€€€€€€€€€€€€€€½µÁ±¥…¹•}Á…­…•}¥ôˆˆ°(€€€€€€€€€€€€€€€€€€€±½…Ñ¥½¹}½‘”ô‰A-%9µˆ°(€€€€€€€€€€€€€€€€€€€ÍÑ…ÑÕÌô‰…Ù…¥±…‰±”ˆ°(€€€€€€€€€€€€€€€€€€€É••¥Ù•‘}…Ðõ‘…Ñ•Ñ¥µ”¹½µ‰¥¹” (€€€€€€€€€€€€€€€€€€€€€€€…Í}½˜€´Ñ¥µ•‘•±Ñ„¡‘…åÌôÄ¤°(€€€€€€€€€€€€€€€€€€€€€€€‘…Ñ•Ñ¥µ”¹µ¥¸¹Ñ¥µ” ¤°(€€€€€€€€€€€€€€€€€€€€€€€Ñé¥¹™¼õÑ¥µ•é½¹”¹ÕÑŒ°(€€€€€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€€€€€•áÁ¥É…Ñ¥½¹}…Ðõ9½¹”°(€€€€€€€€€€€€€€€€€€€¹½Ñ•Ìô‰Må¹Ñ¡•Ñ¥Œ½µµ•É¥…°ÁÕÉ¡…Í”É••¥ÁÐ¸ˆ°(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡Á…­…¥¹}É••¥ÁÑ}±½Ð¤(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹™±ÕÍ  ¤(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘ (€€€€€€€€€€€€€€€€€€€%¹Ù•¹Ñ½ÉåQÉ…¹Í…Ñ¥½¸ (€€€€€€€€€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°(€€€€€€€€€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°(€€€€€€€€€€€€€€€€€€€€€€€±½Ñ}¥õÁ…­…¥¹}É••¥ÁÑ}±½Ð¹¥°(€€€€€€€€€€€€€€€€€€€€€€€ÑÉ…¹Í…Ñ¥½¹}ÑåÁ”ô‰É••¥ÁÐˆ°(€€€€€€€€€€€€€€€€€€€€€€€ÅÕ…¹Ñ¥Ñå}‘•±Ñ„õÉ••¥Ù•‘}ÅÕ…¹Ñ¥Ñä°(€€€€€€€€€€€€€€€€€€€€€€€Õ¹¥Ðô‰Õ¹¥Ðˆ°(€€€€€€€€€€€€€€€€€€€€€€€½µµ•É¥…±}½É‘•É}¥õ½É‘•È¹¥°(€€€€€€€€€€€€€€€€€€€€€€€½µµ•É¥…±}½É‘•É}±¥¹•}¥õ±¥¹”¹¥°(€€€€€€€€€€€€€€€€€€€€€€€…Ñ½Èõ…Ñ½È°(€€€€€€€€€€€€€€€€€€€€€€€É•…Í½¸ô‰1¥Ù¥¹œ‘•µ¼ÁÕÉ¡…Í”É••¥ÁÐˆ°(€€€€€€€€€€€€€€€€€€€€€€€É•™•É•¹”õ½É‘•È¹½É‘•É}¹Õµ‰•È°(€€€€€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€½µµ•É¥…±}ÑÉ…¹Í…Ñ¥½¹}½Õ¹Ð€¬ô€Ä(€€€€€€€€€€€½µµ•É¥…±}½É‘•É}½Õ¹Ð€¬ô€Ä(4(€€€€€€€µ…¡¥¹•}ÍÁ•Ì€ôl(€€€€€€€€€€€€ ‰%5ˆ°€‰AÉ”µÉ½±°±¥¹”™…¥±¥Ñä‰•¹¡µ…É¬ˆ°€‰AÉ”µI½±°ˆ°€ÜÈÀ¸À°€Ð°€‰AHµ%5´ÀÄˆ°€‰%5AÉ”µI½±°1¥¹”ˆ¤°(€€€€€€€€€€€€ ‰5…ÍÍµ…¸ˆ°€‰±½Ý•ÈÁ½Õ ™…¥±¥Ñä‰•¹¡µ…É¬ˆ°€‰A…­…¥¹œˆ°€ØÔÀ¸À°€Ì°€‰A-µ5ML´ÀÄˆ°€‰5…ÍÍµ…¸±½Ý•ÈA½Õ 1¥¹”ˆ¤°(€€€€€€€€€€€€ ‰%Í¡¥‘„ˆ°€‰5Õ±Ñ¥¡•…Ý•¥ µÁ…¬‰•¹¡µ…É¬ˆ°€‰M•½¹‘…ÉäA…­…¥¹œˆ°€äÀÀ¸À°€Ì°€‰A-µ%M ´ÀÄˆ°€‰%Í¡¥‘„AÉ”µI½±°A…¬1¥¹”ˆ¤°(€€€€€€€€€€€€ ‰Y…Á”µ)•Ðˆ°€‰…ÉÑÉ¥‘”™¥±±¥¹œ‰•¹¡µ…É¬ˆ°€‰Y…Á”¥±±¥¹œˆ°€ÔÐÀ¸À°€È°€‰YAµ)P´ÀÄˆ°€‰Y…Á”µ)•Ð¥±±¥¹œ1¥¹”ˆ¤°(€€€€€€€t(€€€€€€€™½Èµ…¹Õ™…ÑÕÉ•È°µ½‘•±}¹…µ”°…Ñ•½Éä°É…Ñ”°É•Ü°…ÍÍ•Ð°‘¥ÍÁ±…ä¥¸µ…¡¥¹•}ÍÁ•Ìè4(€€€€€€€€€€€µ½‘•°€ôÍ•ÍÍ¥½¸¹Í…±…È 4(€€€€€€€€€€€€€€€Í•±•Ð¡5…¡¥¹•5½‘•°¤¹Ý¡•É” 4(€€€€€€€€€€€€€€€€€€€5…¡¥¹•5½‘•°¹µ…¹Õ™…ÑÕÉ•È€ôôµ…¹Õ™…ÑÕÉ•È°4(€€€€€€€€€€€€€€€€€€€5…¡¥¹•5½‘•°¹µ½‘•°€ôôµ½‘•±}¹…µ”°4(€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€€¤4(€€€€€€€€€€€¥˜µ½‘•°¥Ì9½¹”è4(€€€€€€€€€€€€€€€µ½‘•°€ô5…¡¥¹•5½‘•° 4(€€€€€€€€€€€€€€€€€€€µ…¹Õ™…ÑÕÉ•Èõµ…¹Õ™…ÑÕÉ•È°4(€€€€€€€€€€€€€€€€€€€µ½‘•°õµ½‘•±}¹…µ”°4(€€€€€€€€€€€€€€€€€€€…Ñ•½Éäõ…Ñ•½Éä°4(€€€€€€€€€€€€€€€€€€€½Á•É…Ñ¥½¹Í}©Í½¸õ©Í½¸¹‘ÕµÁÌ¡m…Ñ•½Éåt¤°4(€€€€€€€€€€€€€€€€€€€ÁÕ‰±¥Í¡•‘}µ…á}É…Ñ”õÉ…Ñ”°4(€€€€€€€€€€€€€€€€€€€É…Ñ•}Õ¹¥Ðô‰Õ¹¥ÑÌ½¡½ÕÈˆ°4(€€€€€€€€€€€€€€€€€€€ÁÕ‰±¥Í¡•‘}µ¥¹}½Á•É…Ñ½ÉÌõÉ•Ü°4(€€€€€€€€€€€€€€€€€€€ÁÕ‰±¥Í¡•‘}µ…á}½Á•É…Ñ½ÉÌõÉ•Ü€¬€Ä°4(€€€€€€€€€€€€€€€€€€€Á±…¹¹¥¹}ÕÑ¥±¥é…Ñ¥½¹}ÁÐôÜÈ¸À°4(€€€€€€€€€€€€€€€€€€€Í½ÕÉ•}ÕÉ°ô‰¡ÑÑÁÌè¼½•á…µÁ±”¹¥¹Ù…±¥½‘•µ¼µµ…¡¥¹”ˆ°4(€€€€€€€€€€€€€€€€€€€…Ñ¥Ù”õQÉÕ”°4(€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡µ½‘•°¤4(€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹™±ÕÍ  ¤4(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘ 4(€€€€€€€€€€€€€€€…¥±¥Ñå5…¡¥¹” 4(€€€€€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°4(€€€€€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°4(€€€€€€€€€€€€€€€€€€€µ…¡¥¹•}µ½‘•±}¥õµ½‘•°¹¥°4(€€€€€€€€€€€€€€€€€€€…ÍÍ•Ñ}½‘”õ…ÍÍ•Ð°4(€€€€€€€€€€€€€€€€€€€‘¥ÍÁ±…å}¹…µ”õ‘¥ÍÁ±…ä°4(€€€€€€€€€€€€€€€€€€€•™™•Ñ¥Ù•}É…Ñ”õÉ…Ñ”€¨€ À¸ÌÔ¥˜€‰µ…¡¥¹•}‘½Ý¹Ñ¥µ”ˆ¥¸ÁÉ½‰±•µÌ…¹…ÍÍ•Ð€ôô€‰A-µ5ML´ÀÄˆ•±Í”€À¸ÜÈ¤°(€€€€€€€€€€€€€€€€€€€É…Ñ•}Õ¹¥Ðô‰Õ¹¥ÑÌ½¡½ÕÈˆ°4(€€€€€€€€€€€€€€€€€€€ÁÉ•™•ÉÉ•‘}É•Ý}Í¥é”õÉ•Ü°4(€€€€€€€€€€€€€€€€€€€Í•ÑÕÁ}µ¥¹ÕÑ•ÌôÌÀ°4(€€€€€€€€€€€€€€€€€€€±•…¹ÕÁ}µ¥¹ÕÑ•ÌôÈÔ°4(€€€€€€€€€€€€€€€€€€€…Ñ¥Ù”õ¹½Ð€ ‰µ…¡¥¹•}‘½Ý¹Ñ¥µ”ˆ¥¸ÁÉ½‰±•µÌ…¹…ÍÍ•Ð€ôô€‰A-µ5ML´ÀÄˆ¤°(€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€€¤4(4(€€€€€€€Í•ÍÍ¥½¸¹…‘ 4(€€€€€€€€€€€!…¹‘1…‰½ÉÉ•„ 4(€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°4(€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°4(€€€€€€€€€€€€€€€¹…µ”ô‰AÉ¥µ…Éä!…¹1…‰½ÈÉ•„ˆ°4(€€€€€€€€€€€€€€€‘•™…Õ±Ñ}É•Ý}Í¥é”ôÔ°4(€€€€€€€€€€€€€€€ÍÑ¥­•É}Õ¹¥ÑÍ}Á•É}Á•ÉÍ½¹}¡½ÕÈôÄàÀ¸À°4(€€€€€€€€€€€€€€€…Í•}Á…­}Õ¹¥ÑÍ}Á•É}Á•ÉÍ½¹}¡½ÕÈôÄÈÀ¸À°4(€€€€€€€€€€€€€€€™¥¹…±}…Í•Í}Á•É}Á•ÉÍ½¹}¡½ÕÈôÈÐ¸À°4(€€€€€€€€€€€€€€€Í•ÑÕÁ}µ¥¹ÕÑ•ÌôÈÀ°4(€€€€€€€€€€€€€€€±•…¹ÕÁ}µ¥¹ÕÑ•ÌôÄÔ°4(€€€€€€€€€€€€€€€…Ñ¥Ù”õQÉÕ”°4(€€€€€€€€€€€€¤4(€€€€€€€€¤4(€€€€€€€™½È‘…å}½™™Í•Ð¥¸É…¹” ÄÐ¤è(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘ 4(€€€€€€€€€€€€€€€É•ÝÙ…¥±…‰¥±¥Ñä 4(€€€€€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°4(€€€€€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°4(€€€€€€€€€€€€€€€€€€€Ý½É­}‘…Ñ”õ…Í}½˜€¬Ñ¥µ•‘•±Ñ„¡‘…åÌõ‘…å}½™™Í•Ð¤°4(€€€€€€€€€€€€€€€€€€€Í¡¥™Ñ}¹…µ”ô‰…äˆ°4(€€€€€€€€€€€€€€€€€€€…Ù…¥±…‰±•}Á•½Á±”ôÌ¥˜€ ‰±…‰½É}Í¡½ÉÑ…”ˆ¥¸ÁÉ½‰±•µÌ…¹‘…å}½™™Í•Ð€ð€Ð¤•±Í”€ Ì¥˜‘…å}½™™Í•Ð€”€Ô€ôô€À•±Í”€Ô¤°4(€€€€€€€€€€€€€€€€€€€Í¡¥™Ñ}¡½ÕÉÌôà¸À°4(€€€€€€€€€€€€€€€€€€€¹½Ñ•Ìô‰Må¹Ñ¡•Ñ¥Œ‘•µ¼…Á…¥ÑäÁ±…¸ˆ°4(€€€€€€€€€€€€€€€€€€€ÕÁ‘…Ñ•‘}‰äõ…Ñ½È°4(€€€€€€€€€€€€€€€€¤4(€€€€€€€€€€€€¤((€€€€€€€…Õ‘¥Ñ}½Õ¹Ð€ô€À(€€€€€€€¥˜Í•±±…‰±”è(€€€€€€€€€€€É•Ñ…¥±}ÁÉ½‘ÕÐ°É•Ñ…¥±}±½Ð€ôÍ•±±…‰±•lÁt(€€€€€€€€€€€•áÁ•Ñ•€ô™±½…Ð (€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹Í…±…È (€€€€€€€€€€€€€€€€€€€Í•±•Ð¡™Õ¹Œ¹½…±•Í”¡™Õ¹Œ¹ÍÕ´¡%¹Ù•¹Ñ½ÉåQÉ…¹Í…Ñ¥½¸¹ÅÕ…¹Ñ¥Ñå}‘•±Ñ„¤°€À¸À¤¤¹Ý¡•É” (€€€€€€€€€€€€€€€€€€€€€€€%¹Ù•¹Ñ½ÉåQÉ…¹Í…Ñ¥½¸¹±½Ñ}¥€ôôÉ•Ñ…¥±}±½Ð¹¥(€€€€€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€½È€À¸À(€€€€€€€€€€€€¤(€€€€€€€€€€€É•Ñ…¥±}…Õ‘¥Ð€ô%¹Ù•¹Ñ½ÉåÕ‘¥Ð (€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°(€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°(€€€€€€€€€€€€€€€…Õ‘¥Ñ}¹Õµ‰•Èô‰IQ0µ5<µ=5A1Qˆ°(€€€€€€€€€€€€€€€ÍÑ…ÑÕÌô‰½µÁ±•Ñ•ˆ°(€€€€€€€€€€€€€€€½Á•É…Ñ¥½¹}ÑåÁ”ô‰É•Ñ…¥°ˆ°(€€€€€€€€€€€€€€€‰±¥¹‘}½Õ¹ÐõQÉÕ”°(€€€€€€€€€€€€€€€É•½Õ¹Ñ}Ñ½±•É…¹”ôÀ¸À°(€€€€€€€€€€€€€€€Í½Á•}±…‰•°ô‰M…±•Ì™±½½È…¹Í•ÕÉ”‰…­ÍÑ½¬ˆ°(€€€€€€€€€€€€€€€ÍÑ…ÉÑ•‘}…Ðõ‘…Ñ•Ñ¥µ”¹½µ‰¥¹”¡…Í}½˜€´Ñ¥µ•‘•±Ñ„¡‘…åÌôÄ¤°‘…Ñ•Ñ¥µ”¹µ¥¸¹Ñ¥µ” ¤°Ñé¥¹™¼õÑ¥µ•é½¹”¹ÕÑŒ¤°(€€€€€€€€€€€€€€€½µÁ±•Ñ•‘}…Ðõ‘…Ñ•Ñ¥µ”¹½µ‰¥¹”¡…Í}½˜€´Ñ¥µ•‘•±Ñ„¡‘…åÌôÄ¤°‘…Ñ•Ñ¥µ”¹µ¥¸¹Ñ¥µ” ¤°Ñé¥¹™¼õÑ¥µ•é½¹”¹ÕÑŒ¤€¬Ñ¥µ•‘•±Ñ„¡¡½ÕÉÌôÈ¤°(€€€€€€€€€€€€€€€É•…Ñ•‘}‰äô‰‘•µ¼¹É•Ñ…¥°¹½Õ¹Ñ•Èˆ°(€€€€€€€€€€€€€€€½µÁ±•Ñ•‘}‰äô‰‘•µ¼¹¥¹Ù•¹Ñ½Éä¹µ…¹…•Èˆ°(€€€€€€€€€€€€€€€¹½Ñ•Ìô‰Må¹Ñ¡•Ñ¥ŒÁÉ½™¥Ñ…‰±”É•Ñ…¥°½Õ¹ÐÝ¥Ñ „É•Í½±Ù•™¥ÉÍÐµÁ…ÍÌÙ…É¥…¹”¸ˆ°(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡É•Ñ…¥±}…Õ‘¥Ð¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹™±ÕÍ  ¤(€€€€€€€€€€€É•Ñ…¥±}±¥¹”€ô%¹Ù•¹Ñ½ÉåÕ‘¥Ñ1¥¹” (€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°(€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°(€€€€€€€€€€€€€€€…Õ‘¥Ñ}¥õÉ•Ñ…¥±}…Õ‘¥Ð¹¥°(€€€€€€€€€€€€€€€±½Ñ}¥õÉ•Ñ…¥±}±½Ð¹¥°(€€€€€€€€€€€€€€€•áÁ•Ñ•‘}ÅÕ…¹Ñ¥Ñäõ•áÁ•Ñ•°(€€€€€€€€€€€€€€€™¥ÉÍÑ}½Õ¹Ñ}ÅÕ…¹Ñ¥Ñäõµ…à À¸À°•áÁ•Ñ•€´€Ä¸À¤°(€€€€€€€€€€€€€€€É•½Õ¹Ñ}ÅÕ…¹Ñ¥Ñäõ•áÁ•Ñ•°(€€€€€€€€€€€€€€€½Õ¹Ñ•‘}ÅÕ…¹Ñ¥Ñäõ•áÁ•Ñ•°(€€€€€€€€€€€€€€€Ù…É¥…¹•}ÅÕ…¹Ñ¥ÑäôÀ¸À°(€€€€€€€€€€€€€€€É•½Õ¹Ñ}É•ÅÕ¥É•õ…±Í”°(€€€€€€€€€€€€€€€Õ¹¥Ðô‰Õ¹¥Ðˆ°(€€€€€€€€€€€€€€€É•…Í½¸ô‰¥ÉÍÐ½Õ¹Ð•¹ÑÉä½ÉÉ•Ñ¥½¸ˆ°(€€€€€€€€€€€€€€€¹½Ñ•Ìô‰I•½Õ¹Ð½¹™¥Éµ•Ñ¡”±•‘•ÈÅÕ…¹Ñ¥Ñä¸ˆ°(€€€€€€€€€€€€€€€½Õ¹Ñ•‘}‰äô‰‘•µ¼¹É•Ñ…¥°¹É•½Õ¹Ñ•Èˆ°(€€€€€€€€€€€€€€€½Õ¹Ñ•‘}…ÐõÉ•Ñ…¥±}…Õ‘¥Ð¹½µÁ±•Ñ•‘}…Ð°(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡É•Ñ…¥±}±¥¹”¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹™±ÕÍ  ¤(€€€€€€€€€€€Í…¹}½‘”€ôÉ•Ñ…¥±}±½Ð¹‰…É½‘•}Ù…±Õ”½ÈÉ•Ñ…¥±}±½Ð¹½µÁ±¥…¹•}Á…­…•}¥½ÈÉ•Ñ…¥±}ÁÉ½‘ÕÐ¹ÕÁŒ(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘‘}…±° (€€€€€€€€€€€€€€€l(€€€€€€€€€€€€€€€€€€€%¹Ù•¹Ñ½ÉåÕ‘¥ÑM…¸ (€€€€€€€€€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°(€€€€€€€€€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°(€€€€€€€€€€€€€€€€€€€€€€€…Õ‘¥Ñ}¥õÉ•Ñ…¥±}…Õ‘¥Ð¹¥°(€€€€€€€€€€€€€€€€€€€€€€€…Õ‘¥Ñ}±¥¹•}¥õÉ•Ñ…¥±}±¥¹”¹¥°(€€€€€€€€€€€€€€€€€€€€€€€É…Ý}½‘”õÍ…¹}½‘”°(€€€€€€€€€€€€€€€€€€€€€€€¹½Éµ…±¥é•‘}½‘”õÍ…¹}½‘”¹ÕÁÁ•È ¤°(€€€€€€€€€€€€€€€€€€€€€€€µ…Ñ¡}ÍÑ…ÑÕÌô‰µ…Ñ¡•ˆ°(€€€€€€€€€€€€€€€€€€€€€€€Í…¹}ÍÑ…”ô‰™¥ÉÍÑ}½Õ¹Ðˆ°(€€€€€€€€€€€€€€€€€€€€€€€Í…¹¹•‘}‰äô‰‘•µ¼¹É•Ñ…¥°¹½Õ¹Ñ•Èˆ°(€€€€€€€€€€€€€€€€€€€€€€€Í…¹¹•‘}…ÐõÉ•Ñ…¥±}…Õ‘¥Ð¹ÍÑ…ÉÑ•‘}…Ð€¬Ñ¥µ•‘•±Ñ„¡µ¥¹ÕÑ•ÌôÄÈ¤°(€€€€€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€€€€€%¹Ù•¹Ñ½ÉåÕ‘¥ÑM…¸ (€€€€€€€€€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°(€€€€€€€€€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°(€€€€€€€€€€€€€€€€€€€€€€€…Õ‘¥Ñ}¥õÉ•Ñ…¥±}…Õ‘¥Ð¹¥°(€€€€€€€€€€€€€€€€€€€€€€€…Õ‘¥Ñ}±¥¹•}¥õÉ•Ñ…¥±}±¥¹”¹¥°(€€€€€€€€€€€€€€€€€€€€€€€É…Ý}½‘”õÍ…¹}½‘”°(€€€€€€€€€€€€€€€€€€€€€€€¹½Éµ…±¥é•‘}½‘”õÍ…¹}½‘”¹ÕÁÁ•È ¤°(€€€€€€€€€€€€€€€€€€€€€€€µ…Ñ¡}ÍÑ…ÑÕÌô‰µ…Ñ¡•ˆ°(€€€€€€€€€€€€€€€€€€€€€€€Í…¹}ÍÑ…”ô‰É•½Õ¹Ðˆ°(€€€€€€€€€€€€€€€€€€€€€€€Í…¹¹•‘}‰äô‰‘•µ¼¹É•Ñ…¥°¹É•½Õ¹Ñ•Èˆ°(€€€€€€€€€€€€€€€€€€€€€€€Í…¹¹•‘}…ÐõÉ•Ñ…¥±}…Õ‘¥Ð¹½µÁ±•Ñ•‘}…Ð€´Ñ¥µ•‘•±Ñ„¡µ¥¹ÕÑ•ÌôÄà¤°(€€€€€€€€€€€€€€€€€€€€¤°(€€€€€€€€€€€€€€€t(€€€€€€€€€€€€¤(€€€€€€€€€€€…Õ‘¥Ñ}½Õ¹Ð€¬ô€Ä(€€€€€€€¥˜É…Ý}±½ÑÌè(€€€€€€€€€€€ÁÉ½‘ÕÑ¥½¹}±½Ð€ôÉ…Ý}±½ÑÍlÁt(€€€€€€€€€€€ÁÉ½‘ÕÑ¥½¹}•áÁ•Ñ•€ô™±½…Ð (€€€€€€€€€€€€€€€Í•ÍÍ¥½¸¹Í…±…È (€€€€€€€€€€€€€€€€€€€Í•±•Ð¡™Õ¹Œ¹½…±•Í”¡™Õ¹Œ¹ÍÕ´¡%¹Ù•¹Ñ½ÉåQÉ…¹Í…Ñ¥½¸¹ÅÕ…¹Ñ¥Ñå}‘•±Ñ„¤°€À¸À¤¤¹Ý¡•É” (€€€€€€€€€€€€€€€€€€€€€€€%¹Ù•¹Ñ½ÉåQÉ…¹Í…Ñ¥½¸¹±½Ñ}¥€ôôÁÉ½‘ÕÑ¥½¹}±½Ð¹¥(€€€€€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€€€€½È€À¸À(€€€€€€€€€€€€¤(€€€€€€€€€€€ÁÉ½‘ÕÑ¥½¹}…Õ‘¥Ð€ô%¹Ù•¹Ñ½ÉåÕ‘¥Ð (€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°(€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°(€€€€€€€€€€€€€€€…Õ‘¥Ñ}¹Õµ‰•Èô‰AI=µ5<µQ%Yˆ°(€€€€€€€€€€€€€€€ÍÑ…ÑÕÌô‰¥¹}ÁÉ½É•ÍÌˆ°(€€€€€€€€€€€€€€€½Á•É…Ñ¥½¹}ÑåÁ”ô‰ÁÉ½‘ÕÑ¥½¸ˆ°(€€€€€€€€€€€€€€€‰±¥¹‘}½Õ¹ÐõQÉÕ”°(€€€€€€€€€€€€€€€É•½Õ¹Ñ}Ñ½±•É…¹”ôÀ¸Ô°(€€€€€€€€€€€€€€€Í½Á•}±…‰•°ô‰	Õ±¬Ù…Õ±Ðå±”½Õ¹Ðˆ°(€€€€€€€€€€€€€€€É•…Ñ•‘}‰äô‰‘•µ¼¹ÁÉ½‘ÕÑ¥½¸¹½Õ¹Ñ•Èˆ°(€€€€€€€€€€€€€€€¹½Ñ•Ìô‰Ñ¥Ù”Íå¹Ñ¡•Ñ¥Œ‰Õ±¬µÝ•¥¡Ð½Õ¹ÐÉ•…‘ä™½ÈÁ¡½¹”Í…¹¹¥¹œ¸ˆ°(€€€€€€€€€€€€¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘¡ÁÉ½‘ÕÑ¥½¹}…Õ‘¥Ð¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹™±ÕÍ  ¤(€€€€€€€€€€€Í•ÍÍ¥½¸¹…‘ (€€€€€€€€€€€€€€€%¹Ù•¹Ñ½ÉåÕ‘¥Ñ1¥¹” (€€€€€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°(€€€€€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°(€€€€€€€€€€€€€€€€€€€…Õ‘¥Ñ}¥õÁÉ½‘ÕÑ¥½¹}…Õ‘¥Ð¹¥°(€€€€€€€€€€€€€€€€€€€±½Ñ}¥õÁÉ½‘ÕÑ¥½¹}±½Ð¹¥°(€€€€€€€€€€€€€€€€€€€•áÁ•Ñ•‘}ÅÕ…¹Ñ¥Ñäõµ…à À¸À°ÁÉ½‘ÕÑ¥½¹}•áÁ•Ñ•¤°(€€€€€€€€€€€€€€€€€€€Õ¹¥Ðô‰œˆ°(€€€€€€€€€€€€€€€€¤(€€€€€€€€€€€€¤(€€€€€€€€€€€…Õ‘¥Ñ}½Õ¹Ð€¬ô€Ä(€€€€€€€Í•ÍÍ¥½¸¹…‘ (€€€€€€€€€€€Õ‘¥ÑÙ•¹Ð 4(€€€€€€€€€€€€€€€½É…¹¥é…Ñ¥½¹}¥õ½É…¹¥é…Ñ¥½¸¹¥°4(€€€€€€€€€€€€€€€™…¥±¥Ñå}¥õ™…¥±¥Ñä¹¥°4(€€€€€€€€€€€€€€€•¹Ñ¥Ñå}ÑåÁ”ô‰‘•µ½}‘…Ñ…Í•Ðˆ°4(€€€€€€€€€€€€€€€•¹Ñ¥Ñå}¥õ½É…¹¥é…Ñ¥½¸¹¥°4(€€€€€€€€€€€€€€€…Ñ¥½¸ô‰Í••‘•ˆ°4(€€€€€€€€€€€€€€€…Ñ½Èõ…Ñ½È°4(€€€€€€€€€€€€€€€¡…¹•Í}©Í½¸õ©Í½¸¹‘ÕµÁÌ 4(€€€€€€€€€€€€€€€€€€€ì4(€€€€€€€€€€€€€€€€€€€€€€€€‰Ù•ÉÍ¥½¸ˆè5=}Q}YIM%=8°(€€€€€€€€€€€€€€€€€€€€€€€€‰Í…±”ˆèÁ…å±½…¹•Ð ‰Í…±”ˆ¤°4(€€€€€€€€€€€€€€€€€€€€€€€€‰…Í}½™}‘…Ñ”ˆè…Í}½˜¹¥Í½™½Éµ…Ð ¤°4(€€€€€€€€€€€€€€€€€€€€€€€€‰ÁÉ½‰±•µÌˆèÍ½ÉÑ•¡ÁÉ½‰±•µÌ¤°4(€€€€€€€€€€€€€€€€€€€ô4(€€€€€€€€€€€€€€€€¤°4(€€€€€€€€€€€€¤4(€€€€€€€€¤4(4(€€€ÍÑ…Ñ•l‰…Ñ¥Ù•}½É…¹¥é…Ñ¥½¹}¥‰t€ô½É…¹¥é…Ñ¥½¸¹¥4(€€€ÍÑ…Ñ•l‰…Ñ¥Ù•}™…¥±¥Ñå}¥‰t€ô™…¥±¥Ñä¹¥4(€€€É•ÑÕÉ¸ì4(€€€€€€€€‰Í••‘•ˆèQÉÕ”°4(€€€€€€€€‰…±É•…‘å}ÁÉ•Í•¹Ðˆè…±Í”°4(€€€€€€€€‰½É…¹¥é…Ñ¥½¹}¥ˆè½É…¹¥é…Ñ¥½¸¹¥°4(€€€€€€€€‰™…¥±¥Ñå}¥ˆè™…¥±¥Ñä¹¥°4(€€€€€€€€‰ÁÉ½‘ÕÑÌˆè±•¸¡™¥¹¥Í¡•‘}ÁÉ½‘ÕÑÌ¤€¬±•¸¡É…Ý}ÁÉ½‘ÕÑÌ¤€¬€Ä°4(€€€€€€€€‰½É‘•ÉÌˆè±•¸¡½É‘•É}É½ÝÌ¤°4(€€€€€€€€‰ÕÍÑ½µ•ÉÌˆè±•¸¡ÕÍÑ½µ•ÉÌ¤°(€€€€€€€€‰ÑÉ…‘•}Á…ÉÑ¹•ÉÌˆè±•¸¡ÑÉ…‘•}Á…ÉÑ¹•ÉÌ¤°(€€€€€€€€‰½µµ•É¥…±}½É‘•ÉÌˆè½µµ•É¥…±}½É‘•É}½Õ¹Ð°(€€€€€€€€‰½µµ•É¥…±}ÑÉ…¹Í…Ñ¥½¹Ìˆè½µµ•É¥…±}ÑÉ…¹Í…Ñ¥½¹}½Õ¹Ð°(€€€€€€€€‰¥¹Ù•¹Ñ½Éå}…Õ‘¥ÑÌˆè…Õ‘¥Ñ}½Õ¹Ð°(€€€ô(4(4)‘•˜É•Í•Ñ}½µ…¹}‘•µ½}‘…Ñ…Í•Ð 4(€€€€¨°‘…Ñ…‰…Í•}ÕÉ°èÍÑÈð9½¹”€ô9½¹”°•¹¥¹”è¹¥¹”ð9½¹”€ô9½¹”4(¤€´ø‘¥ÑmÍÑÈ°¹åtè4(€€€‘‰}•¹¥¹”€ô}•¹¥¹”¡‘…Ñ…‰…Í•}ÕÉ°°•¹¥¹”¤4(€€€™…Ñ½Éä€ôÍ•ÍÍ¥½¹µ…­•È¡‰¥¹õ‘‰}•¹¥¹”°•áÁ¥É•}½¹}½µµ¥Ðõ…±Í”°™ÕÑÕÉ”õQÉÕ”¤4(€€€Ý¥Ñ ™…Ñ½Éä¹‰•¥¸ ¤…ÌÍ•ÍÍ¥½¸è4(€€€€€€€½É…¹¥é…Ñ¥½¸€ôÍ•ÍÍ¥½¸¹Í…±…È¡Í•±•Ð¡=É…¹¥é…Ñ¥½¸¤¹Ý¡•É”¡=É…¹¥é…Ñ¥½¸¹Í±Õœ€ôô5=}=I9%iQ%=9}M1U¤¤4(€€€€€€€¥˜½É…¹¥é…Ñ¥½¸¥Ì9½¹”è4(€€€€€€€€€€€É•ÑÕÉ¸ì‰‘•±•Ñ•ˆè…±Í”°€‰É•…Í½¸ˆè€‰¹½Ñ}™½Õ¹‰ô4(€€€€€€€™…¥±¥Ñä€ôÍ•ÍÍ¥½¸¹Í…±…È 4(€€€€€€€€€€€Í•±•Ð¡…¥±¥Ñä¤¹Ý¡•É” 4(€€€€€€€€€€€€€€€…¥±¥Ñä¹½É…¹¥é…Ñ¥½¹}¥€ôô½É…¹¥é…Ñ¥½¸¹¥°4(€€€€€€€€€€€€€€€…¥±¥Ñä¹½‘”€ôô5=}%1%Qe}=°4(€€€€€€€€€€€€¤4(€€€€€€€€¤4(€€€€€€€¥˜™…¥±¥Ñä¥Ì¹½Ð9½¹”è4(€€€€€€€€€€€}±•…É}‘•µ½}¡¥±‘É•¸¡Í•ÍÍ¥½¸°½É…¹¥é…Ñ¥½¸¹¥°™…¥±¥Ñä¹¥¤4(€€€€€€€€€€€Í•ÍÍ¥½¸¹‘•±•Ñ”¡™…¥±¥Ñä¤4(€€€€€€€Í•ÍÍ¥½¸¹‘•±•Ñ”¡½É…¹¥é…Ñ¥½¸¤4(€€€É•ÑÕÉ¸ì‰‘•±•Ñ•ˆèQÉÕ•ô4(