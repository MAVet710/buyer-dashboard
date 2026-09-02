from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.services.enterprise_control_fast import organization_facility_metrics
from modules.coman.models import (
    Base,
    CommercialOrder,
    Facility,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
    ProductionOrder,
    TradePartner,
)


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Facility.__table__,
            Product.__table__,
            ProductionOrder.__table__,
            InventoryLot.__table__,
            InventoryTransaction.__table__,
            TradePartner.__table__,
            CommercialOrder.__table__,
        ],
    )
    return engine


def _seed(engine):
    now = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)
    with Session(engine) as session:
        organization = Organization(name="Performance Org", slug="performance-org")
        first = Facility(organization=organization, name="Alpha", code="ALPHA")
        second = Facility(organization=organization, name="Bravo", code="BRAVO")
        product = Product(
            organization_id=organization.id,
            sku="FLOWER-1",
            name="Bulk Flower",
            item_type="cannabis",
            base_unit="g",
            unit_cost=2.5,
        )
        partner = TradePartner(
            organization_id=organization.id,
            name="Performance Partner",
            partner_type="both",
        )
        session.add_all([organization, first, second])
        session.flush()
        product.organization_id = organization.id
        partner.organization_id = organization.id
        session.add_all([product, partner])
        session.flush()

        first_lot = InventoryLot(
            organization_id=organization.id,
            facility_id=first.id,
            product_id=product.id,
            lot_code="ALPHA-LOT",
        )
        second_lot = InventoryLot(
            organization_id=organization.id,
            facility_id=second.id,
            product_id=product.id,
            lot_code="BRAVO-LOT",
        )
        session.add_all([first_lot, second_lot])
        session.flush()
        session.add_all(
            [
                InventoryTransaction(
                    organization_id=organization.id,
                    facility_id=first.id,
                    lot_id=first_lot.id,
                    transaction_type="receipt",
                    quantity_delta=100,
                    unit="g",
                    actor="test",
                ),
                InventoryTransaction(
                    organization_id=organization.id,
                    facility_id=first.id,
                    lot_id=first_lot.id,
                    transaction_type="production_consume",
                    quantity_delta=-20,
                    unit="g",
                    actor="test",
                ),
                InventoryTransaction(
                    organization_id=organization.id,
                    facility_id=second.id,
                    lot_id=second_lot.id,
                    transaction_type="receipt",
                    quantity_delta=40,
                    unit="g",
                    actor="test",
                ),
                CommercialOrder(
                    organization_id=organization.id,
                    facility_id=first.id,
                    partner_id=partner.id,
                    order_number="SO-1",
                    order_type="sales",
                    status="confirmed",
                    due_at=now - timedelta(days=1),
                    created_by="test",
                    updated_by="test",
                ),
                CommercialOrder(
                    organization_id=organization.id,
                    facility_id=first.id,
                    partner_id=partner.id,
                    order_number="PO-1",
                    order_type="purchase",
                    status="draft",
                    due_at=now + timedelta(days=1),
                    created_by="test",
                    updated_by="test",
                ),
                CommercialOrder(
                    organization_id=organization.id,
                    facility_id=second.id,
                    partner_id=partner.id,
                    order_number="SO-2",
                    order_type="sales",
                    status="draft",
                    created_by="test",
                    updated_by="test",
                ),
                ProductionOrder(
                    organization_id=organization.id,
                    facility_id=first.id,
                    order_number="RUN-1",
                    work_type="internal",
                    product_name="Alpha Run",
                    product_format="bulk",
                    requested_units=500,
                    status="in_progress",
                    created_by="test",
                    updated_by="test",
                ),
                ProductionOrder(
                    organization_id=organization.id,
                    facility_id=first.id,
                    order_number="RUN-DONE",
                    work_type="internal",
                    product_name="Completed Run",
                    product_format="bulk",
                    requested_units=999,
                    status="complete",
                    created_by="test",
                    updated_by="test",
                ),
                ProductionOrder(
                    organization_id=organization.id,
                    facility_id=second.id,
                    order_number="RUN-2",
                    work_type="internal",
                    product_name="Bravo Run",
                    product_format="bulk",
                    requested_units=250,
                    status="scheduled",
                    created_by="test",
                    updated_by="test",
                ),
            ]
        )
        session.commit()
        return organization.id, first.id, second.id, now


def test_enterprise_core_projection_stays_at_three_sql_reads_as_facilities_grow() -> None:
    engine = _engine()
    organization_id, first_id, second_id, now = _seed(engine)
    selects: list[str] = []

    def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", count_selects)
    try:
        metrics = organization_facility_metrics(engine, organization_id, now=now)
    finally:
        event.remove(engine, "before_cursor_execute", count_selects)

    assert len(selects) == 3
    assert metrics["inventory"][first_id] == {"positive_lots": 1, "value": 200.0}
    assert metrics["inventory"][second_id] == {"positive_lots": 1, "value": 100.0}
    assert metrics["orders"][first_id] == {"sales": 1, "purchase": 1, "overdue": 1}
    assert metrics["orders"][second_id] == {"sales": 1, "purchase": 0, "overdue": 0}
    assert metrics["production"][first_id] == {"open": 1, "units": 500}
    assert metrics["production"][second_id] == {"open": 1, "units": 250}


def test_enterprise_router_uses_batched_core_projection_not_per_facility_repositories() -> None:
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "backend/app/routers/enterprise_control.py"
    ).read_text(encoding="utf-8")

    assert "organization_facility_metrics" in source
    assert "list_inventory_lots" not in source
    assert "inventory_balance" not in source
    assert "list_orders" not in source
    assert "list_production_orders" not in source


def test_enterprise_router_batches_secondary_domains_instead_of_querying_each_facility() -> None:
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    router = (root / "backend/app/routers/enterprise_control.py").read_text(encoding="utf-8")
    read_model = (root / "backend/app/services/enterprise_control_fast.py").read_text(encoding="utf-8")

    assert "organization_secondary_metrics" in router
    assert "trace.summary(" not in router
    assert "list_deviations(" not in router
    assert "list_label_reviews(" not in router
    assert "ar_summary(" not in router
    assert "group_by(TraceabilityTransaction.facility_id, TraceabilityTransaction.status)" in read_model
    assert "group_by(SOPDeviation.facility_id)" in read_model
    assert "partition_by=LabelReview.facility_id" in read_model
    assert "ranked_labels.c.row_number <= 100" in read_model
    assert "group_by(CommercialInvoice.facility_id)" in read_model
