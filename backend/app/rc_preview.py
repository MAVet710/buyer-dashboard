"""Test-only ASGI entry point for the isolated DoobieLogic release candidate.

This module is intentionally used only by the RC Cloud Run workflow. It creates
an ephemeral SQLite workspace with synthetic data so product/UI workflows can be
exercised without production credentials, production traffic, or customer data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.coman.models import (
    Base,
    Facility,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
    ProductionOrder,
    RetailSale,
)

from .database import get_engine
from .main import app

ORG_ID = "rc-preview-org"
FACILITY_ID = "rc-preview-facility"
PRODUCT_ID = "rc-preview-product"
LOT_ID = "rc-preview-lot"


def _seed_preview() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        if session.get(Organization, ORG_ID) is None:
            session.add(Organization(id=ORG_ID, name="DoobieLogic RC Sandbox", slug="doobielogic-rc", active=True))
        if session.get(Facility, FACILITY_ID) is None:
            session.add(
                Facility(
                    id=FACILITY_ID,
                    organization_id=ORG_ID,
                    name="RC Sandbox Facility",
                    code="RC-SANDBOX",
                    timezone_name="America/New_York",
                    license_number="TEST-ONLY",
                    license_type="Synthetic RC Sandbox",
                    retail_enabled=True,
                    production_enabled=True,
                    cultivation_enabled=True,
                    commercial_enabled=True,
                    active=True,
                )
            )
        if session.get(Product, PRODUCT_ID) is None:
            session.add(
                Product(
                    id=PRODUCT_ID,
                    organization_id=ORG_ID,
                    sku="RC-FLOWER-35",
                    name="RC Blue Dream Flower 3.5g",
                    item_type="cannabis",
                    base_unit="g",
                    unit_cost=8.0,
                    retail_price=25.0,
                    upc="000000000001",
                    active=True,
                )
            )
        if session.get(InventoryLot, LOT_ID) is None:
            session.add(
                InventoryLot(
                    id=LOT_ID,
                    organization_id=ORG_ID,
                    facility_id=FACILITY_ID,
                    product_id=PRODUCT_ID,
                    lot_code="RC-LOT-001",
                    compliance_package_id="1A4RC0000000000000000001",
                    barcode_value="RC-LOT-001",
                    location_code="RC Vault",
                    status="available",
                    received_at=now - timedelta(days=21),
                    expiration_at=now + timedelta(days=120),
                    notes='{"source_name":"RC Test Vendor"}',
                )
            )
        session.flush()
        if session.scalar(select(InventoryTransaction).where(InventoryTransaction.lot_id == LOT_ID)) is None:
            session.add(
                InventoryTransaction(
                    organization_id=ORG_ID,
                    facility_id=FACILITY_ID,
                    lot_id=LOT_ID,
                    transaction_type="receive",
                    quantity_delta=140.0,
                    unit="g",
                    reason="Synthetic RC opening balance",
                    reference="RC-RECEIPT-001",
                    actor="rc-preview-seed",
                    occurred_at=now - timedelta(days=21),
                )
            )
        if session.scalar(select(RetailSale).where(RetailSale.source_record_id == "rc-sale-001")) is None:
            session.add(
                RetailSale(
                    organization_id=ORG_ID,
                    facility_id=FACILITY_ID,
                    product_id=PRODUCT_ID,
                    source_system="rc-preview",
                    source_record_id="rc-sale-001",
                    import_batch_id="rc-preview-seed",
                    sku="RC-FLOWER-35",
                    product_name="RC Blue Dream Flower 3.5g",
                    quantity=24.0,
                    net_sales=480.0,
                    sold_at=now - timedelta(days=2),
                    imported_by="rc-preview-seed",
                )
            )
        if session.scalar(select(ProductionOrder).where(ProductionOrder.order_number == "RC-PO-001")) is None:
            session.add(
                ProductionOrder(
                    organization_id=ORG_ID,
                    facility_id=FACILITY_ID,
                    order_number="RC-PO-001",
                    work_type="internal",
                    product_name="RC Blue Dream Bulk Extract",
                    sku="RC-EXTRACT",
                    product_format="bulk extract",
                    requested_units=10,
                    due_at=now + timedelta(days=7),
                    priority="normal",
                    status="scheduled",
                    notes="Synthetic release-candidate production order",
                    created_by="rc-preview-seed",
                    updated_by="rc-preview-seed",
                )
            )


_seed_preview()
