from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

# Import every new model module before create_all so shared metadata is complete.
from modules.benchmarks import BenchmarkObservation, BenchmarkService
from modules.coman.models import (
    Base,
    BomComponent,
    Facility,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
    ProductBom,
    ProductionOrder,
    TradePartner,
)
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance import CommercialFinanceService
from modules.design_partners import DEFAULT_SUCCESS_TARGETS, DesignPartnerService
from modules.doobie_actions import DoobieActionService
from modules.migration_center import MigrationCenterService, detect_source_system, normalize_import_row
from modules.production_erp import ProductionERPService


@pytest.fixture()
def market_env():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        org = Organization(name="Market Labs", slug="market-labs")
        session.add(org)
        session.flush()
        facility = Facility(organization_id=org.id, name="Main Lab", code="MAIN")
        session.add(facility)
        session.flush()
        product = Product(
            organization_id=org.id,
            sku="GMO-BULK",
            name="GMO Bulk",
            item_type="cannabis",
            base_unit="g",
            unit_cost=1.5,
            retail_price=5.0,
            upc="012345",
        )
        finished = Product(
            organization_id=org.id,
            sku="GMO-35",
            name="GMO 3.5g",
            item_type="finished_good",
            base_unit="unit",
            unit_cost=5.0,
            retail_price=25.0,
        )
        vendor = TradePartner(organization_id=org.id, name="Vendor One", partner_type="vendor")
        customer = TradePartner(organization_id=org.id, name="Customer One", partner_type="customer")
        session.add_all([product, finished, vendor, customer])
        session.flush()
        ids = {
            "org": org.id,
            "facility": facility.id,
            "bulk": product.id,
            "finished": finished.id,
            "vendor": vendor.id,
            "customer": customer.id,
        }
    return engine, sessions, ids


def test_source_detection_and_normalization_are_deterministic():
    assert detect_source_system(["Package Tag", "Item Name", "Unit of Measure", "License Number"]) == "metrc"
    row = normalize_import_row(
        {"Product Name": "GMO 3.5g", "SKU": "GMO-35", "Brand": "House", "Unit Cost": "$5.25", "Retail Price": "25.00"},
        "product",
    )
    assert row["name"] == "GMO 3.5g"
    assert row["sku"] == "GMO-35"
    assert row["unit_cost"] == 5.25
    assert row["retail_price"] == 25.0


def test_switch_center_auto_matches_only_exact_and_commits_inventory(market_env):
    engine, sessions, ids = market_env
    service = MigrationCenterService(engine)
    batch = service.stage_dataframe(
        organization_id=ids["org"],
        facility_id=ids["facility"],
        frame=pd.DataFrame([{"Product Name": "GMO Bulk", "SKU": "GMO-BULK", "Package Tag": "1A4PKG", "Quantity": 1000, "Unit": "g"}]),
        entity_type="inventory",
        actor="admin",
        source_system="metrc",
        filename="packages.csv",
    )
    records = service.records(ids["org"], ids["facility"], batch.id)
    assert len(records) == 1
    assert records[0].match_status == "auto_match"
    assert records[0].canonical_entity_id == ids["bulk"]
    result = service.commit_batch(organization_id=ids["org"], facility_id=ids["facility"], batch_id=batch.id, actor="admin")
    assert result["committed"] == 1
    with sessions() as session:
        lot = session.scalar(select(InventoryLot).where(InventoryLot.compliance_package_id == "1A4PKG"))
        assert lot is not None
        balance = sum(float(row.quantity_delta) for row in session.scalars(select(InventoryTransaction).where(InventoryTransaction.lot_id == lot.id)))
        assert balance == 1000.0

    fuzzy = service.stage_dataframe(
        organization_id=ids["org"],
        facility_id=ids["facility"],
        frame=pd.DataFrame([{"Product Name": "GMO Bulk Flower Maybe"}]),
        entity_type="product",
        actor="admin",
        source_system="spreadsheet",
        filename="products.csv",
    )
    fuzzy_record = service.records(ids["org"], ids["facility"], fuzzy.id)[0]
    assert fuzzy_record.match_status != "auto_match"
    assert fuzzy_record.decision_action == "pending"


def test_production_erp_reserves_bom_posts_output_and_requires_qa_release(market_env):
    engine, sessions, ids = market_env
    with sessions.begin() as session:
        lot = InventoryLot(organization_id=ids["org"], facility_id=ids["facility"], product_id=ids["bulk"], lot_code="BULK-1", status="available", location_code="VAULT")
        order = ProductionOrder(
            organization_id=ids["org"], facility_id=ids["facility"], order_number="WO-1", work_type="internal",
            product_name="GMO 3.5g", sku="GMO-35", product_format="Pouched flower — 3.5 g", requested_units=100,
            status="draft", source_lot_reference="", material_owner="internal", packaging_owner="internal", notes="", created_by="planner", updated_by="planner",
        )
        bom = ProductBom(organization_id=ids["org"], output_product_id=ids["finished"], version=1, output_quantity=100, expected_loss_pct=0, active=True, notes="")
        session.add_all([lot, order, bom])
        session.flush()
        session.add(InventoryTransaction(organization_id=ids["org"], facility_id=ids["facility"], lot_id=lot.id, transaction_type="receipt", quantity_delta=500, unit="g", actor="receiver", reason="test"))
        session.add(BomComponent(organization_id=ids["org"], bom_id=bom.id, input_product_id=ids["bulk"], quantity=350, unit="g", scrap_pct=0))
        order_id = order.id

    service = ProductionERPService(engine)
    reservation = service.reserve_bom_materials(organization_id=ids["org"], facility_id=ids["facility"], order_id=order_id, actor="planner")
    assert reservation["shortages"] == []
    output = service.add_output(organization_id=ids["org"], facility_id=ids["facility"], order_id=order_id, product_id=ids["finished"], planned_quantity=100, actor="operator")
    output = service.record_output_actual(organization_id=ids["org"], facility_id=ids["facility"], output_id=output.id, actual_quantity=96, actor="operator", lot_code="WO-1-OUT")
    assert output.status == "quarantine"
    service.record_qa(organization_id=ids["org"], facility_id=ids["facility"], order_id=order_id, output_id=output.id, event_type="release", result="passed", actor="qa")
    snapshot = service.order_360(ids["org"], ids["facility"], order_id)
    assert snapshot["outputs"][0].status == "released"
    with sessions() as session:
        assert session.get(InventoryLot, snapshot["outputs"][0].lot_id).status == "available"


def test_wholesale_invoice_payment_and_ar(market_env):
    engine, _sessions, ids = market_env
    commercial = CommercialRepository(engine)
    order = commercial.create_order(
        organization_id=ids["org"], facility_id=ids["facility"], partner_id=ids["customer"], order_number="SO-100", order_type="sales",
        order_date=date.today(), due_date=date.today() + timedelta(days=3),
        lines=[{"product_id": ids["finished"], "quantity": 10, "unit": "unit", "unit_price": 20}], actor="sales",
    )
    finance = CommercialFinanceService(engine)
    invoice = finance.create_invoice_from_order(organization_id=ids["org"], facility_id=ids["facility"], order_id=order.id, invoice_number="INV-100", actor="sales", due_days=30)
    assert invoice.total_usd == 200.0
    finance.send_invoice(organization_id=ids["org"], facility_id=ids["facility"], invoice_id=invoice.id)
    payment = finance.record_payment(organization_id=ids["org"], facility_id=ids["facility"], invoice_id=invoice.id, amount_usd=75, actor="ar", method="ach")
    assert payment.amount_usd == 75
    ar = finance.ar_summary(ids["org"], ids["facility"])
    assert ar["total_ar"] == 125.0
    with pytest.raises(ValueError, match="exceeds"):
        finance.record_payment(organization_id=ids["org"], facility_id=ids["facility"], invoice_id=invoice.id, amount_usd=126, actor="ar")


def test_doobie_requires_approval_and_executes_registered_handler_once(market_env):
    engine, _sessions, ids = market_env
    actions = DoobieActionService(engine)
    proposal = actions.propose(
        organization_id=ids["org"], facility_id=ids["facility"], action_type="create_production_order",
        title="Build 100 GMO eighths", rationale="Demand exceeds available stock.",
        payload={"order_number": "DOOBIE-WO-1", "product_name": "GMO 3.5g", "product_format": "Pouched flower — 3.5 g", "requested_units": 100, "sku": "GMO-35"},
        preview={"creates": "one production order", "units": 100}, actor="doobie", idempotency_key="test:doobie:wo1", financial_impact_usd=2000,
    )
    with pytest.raises(ValueError, match="Approve"):
        actions.execute(organization_id=ids["org"], facility_id=ids["facility"], proposal_id=proposal.id, actor="admin")
    actions.approve(organization_id=ids["org"], facility_id=ids["facility"], proposal_id=proposal.id, actor="admin")
    result = actions.execute(organization_id=ids["org"], facility_id=ids["facility"], proposal_id=proposal.id, actor="admin")
    assert result["action"] == "production_order_created"
    repeated = actions.execute(organization_id=ids["org"], facility_id=ids["facility"], proposal_id=proposal.id, actor="admin")
    assert repeated["production_order_id"] == result["production_order_id"]


def test_benchmark_network_is_opt_in_and_cohort_suppressed(market_env):
    engine, sessions, ids = market_env
    benchmark = BenchmarkService(engine)
    benchmark.set_opt_in(organization_id=ids["org"], share=True, actor="admin", minimum_cohort_size=3)
    with sessions.begin() as session:
        from modules.benchmarks.models import BenchmarkSetting
        for index, value in enumerate((80.0, 90.0), start=2):
            org = Organization(name=f"Peer {index}", slug=f"peer-{index}")
            session.add(org)
            session.flush()
            fac = Facility(organization_id=org.id, name="Lab", code=f"P{index}")
            session.add(fac)
            session.flush()
            session.add(BenchmarkSetting(organization_id=org.id, share_anonymized_aggregates=True, minimum_cohort_size=3, updated_by="peer"))
            session.add(BenchmarkObservation(organization_id=org.id, facility_id=fac.id, metric_key="production_attainment_pct", cohort_key="production:all", value=value, unit="pct", sample_count=10, period_start=date.today()-timedelta(days=30), period_end=date.today()))
        session.add(BenchmarkObservation(organization_id=ids["org"], facility_id=ids["facility"], metric_key="production_attainment_pct", cohort_key="production:all", value=95.0, unit="pct", sample_count=10, period_start=date.today()-timedelta(days=30), period_end=date.today()))
    result = benchmark.network_summary(organization_id=ids["org"], facility_id=ids["facility"], metric_key="production_attainment_pct", cohort_key="production:all")
    assert result["available"] is True
    assert result["cohort_organizations"] == 3
    assert "organizations" not in result
    assert result["percentile"] is not None


def test_design_partner_scorecard_turns_pilot_into_case_study_proof(market_env):
    engine, _sessions, ids = market_env
    service = DesignPartnerService(engine)
    account = service.enroll(organization_id=ids["org"], actor="admin", champion_name="Ops Lead", pain_profile="Too many spreadsheets", success_targets=DEFAULT_SUCCESS_TARGETS)
    assert account.status == "pilot"
    service.upsert_metric(organization_id=ids["org"], metric_key="hours_saved_per_week", baseline_value=0, current_value=7, unit="hours", actor="admin")
    service.upsert_metric(organization_id=ids["org"], metric_key="inventory_accuracy_pct", baseline_value=90, current_value=99, unit="%", actor="admin")
    service.upsert_metric(organization_id=ids["org"], metric_key="cogs_coverage_pct", baseline_value=20, current_value=95, unit="%", actor="admin")
    snapshot = service.snapshot(ids["org"])
    assert snapshot["readiness"]["ready"] is True
    assert len(snapshot["readiness"]["wins"]) >= 2
