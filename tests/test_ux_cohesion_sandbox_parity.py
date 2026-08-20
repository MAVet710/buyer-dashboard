from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from modules.benchmarks.models import BenchmarkSetting
from modules.coman.models import (
    Base,
    Facility,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
    ProductionOrder,
    TradePartner,
)
from modules.commercial.repository import CommercialRepository
from modules.extraction.low_click_runtime import quick_stage_transition
from modules.extraction.workflows import get_extraction_workflow
from modules.package_studio.models import PackageStudioInput, PackageStudioOutput, PackageStudioRun
from modules.product_master.ui import PRODUCT_MASTER_SURFACE
from services.sandbox_market_seed import (
    market_sandbox_readiness,
    reset_market_sandbox_dataset,
    seed_market_sandbox,
)
from services.ux_cohesion_runtime import product_master_secondary_choices


def _sandbox_env():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    # SQLite ignores foreign key constraints by default -- without this, a test
    # named "...fk_safe" can pass even when a real Postgres RESTRICT constraint
    # would reject the same deletes. This is what let the Package Studio gap in
    # reset_market_sandbox_dataset reach production undetected.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk_enforcement(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        org = Organization(name="DEV Sandbox", slug="dev-sandbox", active=True)
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Sandbox Facility",
            code="SANDBOX",
            timezone_name="America/New_York",
            active=True,
        )
        session.add(facility)
        session.flush()
        raw = Product(
            organization_id=org.id,
            sku="SBX-RAW",
            name="Sandbox GMO Bulk",
            item_type="cannabis",
            base_unit="g",
            unit_cost=1.25,
            retail_price=4.0,
            active=True,
        )
        finished = Product(
            organization_id=org.id,
            sku="SBX-FG",
            name="Sandbox GMO 3.5g",
            item_type="finished_good",
            base_unit="unit",
            unit_cost=5.0,
            retail_price=25.0,
            active=True,
        )
        vendor = TradePartner(
            organization_id=org.id,
            name="Sandbox Supply",
            partner_type="vendor",
            active=True,
        )
        customer = TradePartner(
            organization_id=org.id,
            name="Sandbox Retailer",
            partner_type="customer",
            active=True,
        )
        session.add_all([raw, finished, vendor, customer])
        session.flush()
        lot = InventoryLot(
            organization_id=org.id,
            facility_id=facility.id,
            product_id=raw.id,
            lot_code="SBX-RAW-LOT",
            compliance_package_id="1A4-SBX-RAW",
            location_code="VAULT",
            status="available",
        )
        session.add(lot)
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=org.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="receipt",
                quantity_delta=2000.0,
                unit="g",
                actor="sandbox",
                reason="sandbox fixture",
            )
        )
        order = ProductionOrder(
            organization_id=org.id,
            facility_id=facility.id,
            order_number="WO-SBX-001",
            work_type="internal",
            product_name=finished.name,
            sku=finished.sku,
            product_format="3.5g pouch",
            requested_units=100,
            status="scheduled",
            source_lot_reference="",
            material_owner="internal",
            packaging_owner="internal",
            due_at=datetime.now(timezone.utc) + timedelta(days=1),
            notes="",
            created_by="sandbox",
            updated_by="sandbox",
        )
        session.add(order)
        session.flush()
        ids = {
            "org": org.id,
            "facility": facility.id,
            "raw": raw.id,
            "finished": finished.id,
            "vendor": vendor.id,
            "customer": customer.id,
            "lot": lot.id,
        }

    commercial = CommercialRepository(engine)
    commercial.create_order(
        organization_id=ids["org"],
        facility_id=ids["facility"],
        partner_id=ids["customer"],
        order_number="SO-SBX-001",
        order_type="sales",
        order_date=date.today(),
        due_date=date.today() + timedelta(days=3),
        lines=[
            {
                "product_id": ids["finished"],
                "quantity": 12,
                "unit": "unit",
                "unit_price": 17.0,
            }
        ],
        actor="sandbox",
    )
    return engine, sessions, ids


def test_products_is_a_first_class_inventory_destination_in_both_operation_modes():
    base = [
        ("Inventory", "section", "inventory_dashboard"),
        ("Inventory Audits", "section", "inventory_counts"),
    ]
    for operation_mode in ("Retail Ops", "Production Ops"):
        choices = product_master_secondary_choices(
            base,
            category="Inventory",
            operation_mode=operation_mode,
        )
        assert choices[1] == ("Products", "virtual", PRODUCT_MASTER_SURFACE)
        assert sum(value == PRODUCT_MASTER_SURFACE for _, _, value in choices) == 1


def test_extraction_routine_stage_update_has_one_deterministic_next_step():
    workflow = get_extraction_workflow("bho_cured")
    current = workflow.first_stage
    current_label, next_key, next_label = quick_stage_transition(workflow, current)
    assert current_label == workflow.stage_label(current)
    assert next_key == workflow.next_stage(current)
    assert next_key
    assert next_label == workflow.stage_label(next_key)


def test_market_sandbox_populates_every_new_durable_surface_and_is_idempotent():
    engine, sessions, ids = _sandbox_env()
    first = seed_market_sandbox(
        engine,
        ids["org"],
        ids["facility"],
        actor="sandbox",
        state={},
    )
    assert first["ready"] is True
    assert first["missing"] == []
    assert set(first["counts"]) == {
        "products",
        "switch_center",
        "production",
        "wholesale_finance",
        "doobie_actions",
        "benchmarks",
        "design_partner",
        "extraction",
        "traceability",
    }
    assert all(value > 0 for value in first["counts"].values())

    second = seed_market_sandbox(
        engine,
        ids["org"],
        ids["facility"],
        actor="sandbox",
        state={},
    )
    assert second["ready"] is True
    assert second["counts"] == first["counts"]

    with sessions() as session:
        setting = session.scalar(
            select(BenchmarkSetting).where(BenchmarkSetting.organization_id == ids["org"])
        )
        assert setting is not None
        assert setting.share_anonymized_aggregates is False


def test_market_sandbox_refuses_to_seed_a_real_tenant():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        org = Organization(name="Real Customer", slug="real-customer")
        session.add(org)
        session.flush()
        facility = Facility(organization_id=org.id, name="Main", code="MAIN")
        session.add(facility)
        session.flush()
        org_id, facility_id = org.id, facility.id

    with pytest.raises(ValueError, match="refused"):
        seed_market_sandbox(engine, org_id, facility_id, actor="sandbox", state={})


def test_market_extension_cleanup_makes_canonical_sandbox_reset_fk_safe():
    engine, sessions, ids = _sandbox_env()
    readiness = seed_market_sandbox(engine, ids["org"], ids["facility"], actor="sandbox", state={})
    assert readiness["ready"] is True

    # A real Package Studio action (breakdown/build_run/etc.) creates rows that
    # hold RESTRICT foreign keys straight to coman_products and
    # coman_inventory_lots -- exactly the tables the canonical sandbox reset
    # deletes from below. seed_market_sandbox itself never creates these, so
    # without this fixture the test cannot exercise the scenario that broke
    # reset_market_sandbox_dataset in production.
    with sessions.begin() as session:
        run = PackageStudioRun(
            organization_id=ids["org"],
            facility_id=ids["facility"],
            run_number="PS-SBX-001",
            action_type="pack_down",
            status="committed",
            source_quantity=100.0,
            source_unit="g",
            created_by="sandbox",
        )
        session.add(run)
        session.flush()
        session.add(
            PackageStudioInput(
                organization_id=ids["org"],
                facility_id=ids["facility"],
                run_id=run.id,
                lot_id=ids["lot"],
                position=1,
                quantity=50.0,
                unit="g",
            )
        )
        session.add(
            PackageStudioOutput(
                organization_id=ids["org"],
                facility_id=ids["facility"],
                run_id=run.id,
                product_id=ids["finished"],
                position=1,
                lot_code="PS-SBX-OUT-001",
                inventory_quantity=10.0,
                inventory_unit="unit",
            )
        )

    result = reset_market_sandbox_dataset(engine=engine)
    assert result["deleted"] is True
    after = market_sandbox_readiness(engine, ids["org"], ids["facility"])
    assert after["ready"] is False
    assert after["missing"]

    # The legacy sandbox owns the base organization/facility/products. Once
    # extension rows are gone, its canonical reset can delete those FK targets.
    from modules.coman.demo_data import reset_coman_demo_dataset

    canonical = reset_coman_demo_dataset(engine=engine)
    assert canonical["deleted"] is True
