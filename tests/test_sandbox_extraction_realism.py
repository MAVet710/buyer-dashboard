from __future__ import annotations

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from backend.app.services.sandbox_extraction import (
    SANDBOX_EXTRACTION_VERSION,
    ensure_rich_extraction_sandbox,
)
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.extraction.models import (
    ExtractionCostEvent,
    ExtractionQAEvent,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionRunOutput,
    ExtractionTollJob,
)
from modules.extraction.performance_models import ExtractionResourceEvent
from modules.traceability.models import TraceabilityTransaction


def _sandbox_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sessions.begin() as session:
        sandbox = Organization(name="DEV Sandbox", slug="dev-sandbox", active=True)
        real = Organization(name="Real Customer", slug="real-customer", active=True)
        session.add_all([sandbox, real])
        session.flush()
        sandbox_facility = Facility(
            organization_id=sandbox.id,
            name="Sandbox Facility",
            code="SANDBOX",
            timezone_name="America/New_York",
            production_enabled=True,
            active=True,
        )
        real_facility = Facility(
            organization_id=real.id,
            name="Real Production",
            code="PROD",
            timezone_name="America/New_York",
            production_enabled=True,
            active=True,
        )
        session.add_all([sandbox_facility, real_facility])
        session.flush()
        ids = {
            "sandbox_org": sandbox.id,
            "sandbox_facility": sandbox_facility.id,
            "real_org": real.id,
            "real_facility": real_facility.id,
        }
    return engine, sessions, ids


def _count(session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_rich_extraction_sandbox_populates_realistic_linked_operation_and_is_idempotent():
    engine, sessions, ids = _sandbox_engine()

    first = ensure_rich_extraction_sandbox(engine)
    assert first["seeded"] is True
    assert first["version"] == SANDBOX_EXTRACTION_VERSION
    assert first["production_writes_enabled"] is False
    assert first["runs"] >= 10
    assert first["inventory_lots"] >= 10
    assert first["qa_events"] >= 5
    assert first["methods"] >= 7

    with sessions() as session:
        runs = list(
            session.scalars(
                select(ExtractionRun)
                .where(
                    ExtractionRun.organization_id == ids["sandbox_org"],
                    ExtractionRun.facility_id == ids["sandbox_facility"],
                    ExtractionRun.batch_number.like("SANDBOX-EXT-%"),
                )
                .order_by(ExtractionRun.batch_number)
            )
        )
        assert len(runs) >= 10
        assert {run.status for run in runs} >= {"active", "hold", "qa", "complete", "queued"}
        assert {run.method for run in runs} >= {"BHO", "Ethanol", "Distillation", "Solventless", "Rosin", "Dry Sift", "CO2"}
        assert all(run.jurisdiction == "MA" for run in runs)
        assert all(run.facility_license_name == "DEV Sandbox Extraction Facility" for run in runs)
        assert all("no operating recipe or process setpoints" in run.notes for run in runs)
        assert any(run.toll_processing for run in runs)
        assert any(run.manual_qa_hold for run in runs)
        assert any(run.manual_coa_status == "failed" for run in runs)
        assert any(run.manual_coa_status == "pending" for run in runs)
        assert any(run.manual_coa_status == "passed" for run in runs)
        assert any(run.estimated_revenue_usd > 0 for run in runs)
        assert any(run.machine_line for run in runs)

        products = list(
            session.scalars(
                select(Product).where(
                    Product.organization_id == ids["sandbox_org"],
                    Product.sku.like("SBX-EXT-%"),
                )
            )
        )
        assert len(products) >= 12
        assert {product.item_type for product in products} >= {"cannabis", "wip"}

        lots = list(
            session.scalars(
                select(InventoryLot).where(
                    InventoryLot.organization_id == ids["sandbox_org"],
                    InventoryLot.facility_id == ids["sandbox_facility"],
                    InventoryLot.notes.like(f"%{SANDBOX_EXTRACTION_VERSION}%"),
                )
            )
        )
        assert len(lots) >= 10
        assert {lot.location_code for lot in lots} >= {"FREEZER-A1", "VAULT-BULK-01", "WIP-EXTRACTION", "RELEASED-BULK"}
        assert all(lot.compliance_package_id.startswith("1A406030000SBX") for lot in lots)

        consumption = list(
            session.scalars(
                select(InventoryTransaction).where(
                    InventoryTransaction.organization_id == ids["sandbox_org"],
                    InventoryTransaction.facility_id == ids["sandbox_facility"],
                    InventoryTransaction.reference.like(f"{SANDBOX_EXTRACTION_VERSION}:consume:%"),
                )
            )
        )
        assert len(consumption) >= 9
        assert all(row.quantity_delta < 0 for row in consumption)

        by_batch = {run.batch_number: run for run in runs}
        crude_output = session.scalar(
            select(ExtractionRunOutput).where(ExtractionRunOutput.run_id == by_batch["SANDBOX-EXT-003"].id)
        )
        distillate_input = session.scalar(
            select(ExtractionRunInput).where(ExtractionRunInput.run_id == by_batch["SANDBOX-EXT-004"].id)
        )
        assert crude_output is not None and crude_output.lot_id
        assert distillate_input is not None
        assert distillate_input.lot_id == crude_output.lot_id

        hash_output = session.scalar(
            select(ExtractionRunOutput).where(ExtractionRunOutput.run_id == by_batch["SANDBOX-EXT-005"].id)
        )
        rosin_input = session.scalar(
            select(ExtractionRunInput).where(ExtractionRunInput.run_id == by_batch["SANDBOX-EXT-006"].id)
        )
        assert hash_output is not None and hash_output.lot_id
        assert rosin_input is not None
        assert rosin_input.lot_id == hash_output.lot_id

        assert _count(session, ExtractionCostEvent) >= 50
        assert _count(session, ExtractionResourceEvent) >= 20
        assert _count(session, ExtractionQAEvent) >= 5
        assert _count(session, TraceabilityTransaction) >= 10
        assert _count(session, ExtractionTollJob) >= 1

        before = {
            "runs": _count(session, ExtractionRun),
            "inputs": _count(session, ExtractionRunInput),
            "outputs": _count(session, ExtractionRunOutput),
            "costs": _count(session, ExtractionCostEvent),
            "resources": _count(session, ExtractionResourceEvent),
            "qa": _count(session, ExtractionQAEvent),
            "traceability": _count(session, TraceabilityTransaction),
            "lots": _count(session, InventoryLot),
            "transactions": _count(session, InventoryTransaction),
        }

    second = ensure_rich_extraction_sandbox(engine)
    assert second["seeded"] is True
    assert second["runs"] == first["runs"]

    with sessions() as session:
        after = {
            "runs": _count(session, ExtractionRun),
            "inputs": _count(session, ExtractionRunInput),
            "outputs": _count(session, ExtractionRunOutput),
            "costs": _count(session, ExtractionCostEvent),
            "resources": _count(session, ExtractionResourceEvent),
            "qa": _count(session, ExtractionQAEvent),
            "traceability": _count(session, TraceabilityTransaction),
            "lots": _count(session, InventoryLot),
            "transactions": _count(session, InventoryTransaction),
        }
    assert after == before


def test_rich_extraction_sandbox_never_writes_to_non_sandbox_tenant():
    engine, sessions, ids = _sandbox_engine()
    result = ensure_rich_extraction_sandbox(engine)
    assert result["seeded"] is True

    with sessions() as session:
        real_runs = int(
            session.scalar(
                select(func.count(ExtractionRun.id)).where(
                    ExtractionRun.organization_id == ids["real_org"],
                    ExtractionRun.facility_id == ids["real_facility"],
                )
            )
            or 0
        )
        real_lots = int(
            session.scalar(
                select(func.count(InventoryLot.id)).where(
                    InventoryLot.organization_id == ids["real_org"],
                    InventoryLot.facility_id == ids["real_facility"],
                )
            )
            or 0
        )
    assert real_runs == 0
    assert real_lots == 0


def test_api_startup_installs_extraction_sandbox_realism_seed():
    source = __import__("pathlib").Path("backend/app/main.py").read_text(encoding="utf-8")
    assert "from .services.sandbox_extraction import ensure_rich_extraction_sandbox" in source
    assert "ensure_rich_extraction_sandbox(engine)" in source
