from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import Base, Facility, InventoryLot, Organization, Product
from modules.extraction.elite_runtime import _performance_exceptions
from modules.extraction.models import (
    ExtractionCostEvent,
    ExtractionRun,
    ExtractionRunInput,
    ExtractionRunOutput,
)
from modules.extraction.performance import (
    ExtractionPerformanceService,
    benchmark_run_metrics,
    summarize_resource_events,
)
from modules.extraction.performance_models import ExtractionResourceEvent
from modules.product_master.models import ProductValueEvent


@pytest.fixture()
def extraction_env():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    now = datetime.now(timezone.utc)
    with sessions.begin() as session:
        org = Organization(name="Extraction Labs", slug="extraction-labs")
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Main Lab",
            code="LAB-1",
        )
        source_product = Product(
            organization_id=org.id,
            sku="FLOWER-1",
            name="Source Flower",
            item_type="cannabis",
            base_unit="g",
            unit_cost=1.0,
        )
        output_product = Product(
            organization_id=org.id,
            sku="LIVE-RESIN-1",
            name="Live Resin",
            item_type="finished_good",
            base_unit="g",
            unit_cost=0.0,
            retail_price=0.0,
        )
        session.add_all([facility, source_product, output_product])
        session.flush()
        lot = InventoryLot(
            organization_id=org.id,
            facility_id=facility.id,
            product_id=source_product.id,
            lot_code="SRC-001",
            status="available",
        )
        session.add(lot)
        session.flush()

        run = ExtractionRun(
            organization_id=org.id,
            facility_id=facility.id,
            batch_number="BHO-100",
            method="BHO",
            workflow_key="bho_cured",
            current_stage_key="recovery",
            status="active",
            release_status="blocked",
            product_family="Live Resin",
            strain="GMO",
            created_by="operator",
            updated_by="operator",
            started_at=now - timedelta(hours=8),
        )
        peer = ExtractionRun(
            organization_id=org.id,
            facility_id=facility.id,
            batch_number="BHO-099",
            method="BHO",
            workflow_key="bho_cured",
            current_stage_key="release",
            status="complete",
            release_status="approved",
            product_family="Live Resin",
            strain="GMO",
            created_by="operator",
            updated_by="operator",
            started_at=now - timedelta(days=2, hours=6),
            completed_at=now - timedelta(days=2),
        )
        session.add_all([run, peer])
        session.flush()

        session.add_all(
            [
                ExtractionRunInput(
                    organization_id=org.id,
                    facility_id=facility.id,
                    run_id=run.id,
                    lot_id=lot.id,
                    role="primary_input",
                    planned_quantity=100.0,
                    reserved_quantity=100.0,
                    consumed_quantity=100.0,
                    unit="g",
                    unit_cost_snapshot=1.0,
                    input_cost_usd=100.0,
                    status="consumed",
                    reserved_by="operator",
                ),
                ExtractionRunInput(
                    organization_id=org.id,
                    facility_id=facility.id,
                    run_id=peer.id,
                    lot_id=lot.id,
                    role="benchmark_input",
                    planned_quantity=100.0,
                    reserved_quantity=100.0,
                    consumed_quantity=100.0,
                    unit="g",
                    unit_cost_snapshot=1.0,
                    input_cost_usd=100.0,
                    status="consumed",
                    reserved_by="operator",
                ),
            ]
        )
        session.add_all(
            [
                ExtractionRunOutput(
                    organization_id=org.id,
                    facility_id=facility.id,
                    run_id=run.id,
                    product_id=output_product.id,
                    position=1,
                    output_label="Live Resin",
                    quantity=20.0,
                    unit="g",
                    status="quarantine",
                    coa_status="pending",
                    created_by="operator",
                ),
                ExtractionRunOutput(
                    organization_id=org.id,
                    facility_id=facility.id,
                    run_id=peer.id,
                    product_id=output_product.id,
                    position=1,
                    output_label="Live Resin",
                    quantity=25.0,
                    unit="g",
                    status="released",
                    coa_status="passed",
                    created_by="operator",
                ),
            ]
        )
        session.add_all(
            [
                ExtractionCostEvent(
                    organization_id=org.id,
                    facility_id=facility.id,
                    run_id=run.id,
                    category="material",
                    amount_usd=100.0,
                    actor="operator",
                ),
                ExtractionCostEvent(
                    organization_id=org.id,
                    facility_id=facility.id,
                    run_id=peer.id,
                    category="material",
                    amount_usd=90.0,
                    actor="operator",
                ),
                ProductValueEvent(
                    organization_id=org.id,
                    product_id=output_product.id,
                    value_type="wholesale_price",
                    amount=12.0,
                    currency="USD",
                    source="pricing",
                    actor="buyer",
                ),
            ]
        )
        session.flush()
        ids = {
            "org": org.id,
            "facility": facility.id,
            "run": run.id,
            "peer": peer.id,
        }
    return engine, sessions, ids


def test_resource_summary_tracks_usage_recovery_and_cost():
    summary = summarize_resource_events(
        [
            {
                "resource_type": "solvent",
                "quantity": 100.0,
                "recovered_quantity": 92.0,
                "cost_usd": 25.0,
            },
            {
                "resource_type": "utility",
                "quantity": 4.0,
                "recovered_quantity": None,
                "cost_usd": 12.0,
            },
        ]
    )
    assert summary["solvent_used"] == 100.0
    assert summary["solvent_recovered"] == 92.0
    assert summary["solvent_recovery_pct"] == 92.0
    assert summary["total_cost"] == 37.0


def test_peer_benchmark_uses_transparent_medians_and_percentiles():
    benchmark = benchmark_run_metrics(
        {
            "yield_pct": 20.0,
            "cost_per_output": 5.0,
            "cycle_hours": 8.0,
            "solvent_recovery_pct": 90.0,
        },
        [
            {"yield_pct": 18.0, "cost_per_output": 6.0, "cycle_hours": 10.0, "solvent_recovery_pct": 85.0},
            {"yield_pct": 20.0, "cost_per_output": 5.5, "cycle_hours": 9.0, "solvent_recovery_pct": 88.0},
            {"yield_pct": 22.0, "cost_per_output": 5.0, "cycle_hours": 8.0, "solvent_recovery_pct": 92.0},
        ],
    )
    assert benchmark["peer_count"] == 3
    assert benchmark["yield_median"] == 20.0
    assert benchmark["cost_per_output_median"] == 5.5
    assert benchmark["yield_delta"] == 0.0
    assert benchmark["cost_delta"] == pytest.approx(-0.5)
    assert benchmark["yield_percentile"] == pytest.approx(66.6666666)


def test_run_metrics_use_product_master_value_and_resource_cost(extraction_env):
    engine, sessions, ids = extraction_env
    service = ExtractionPerformanceService(engine)
    service.record_resource_usage(
        organization_id=ids["org"],
        facility_id=ids["facility"],
        run_id=ids["run"],
        resource_type="solvent",
        resource_name="Butane blend",
        quantity=50.0,
        recovered_quantity=45.0,
        unit="g",
        cost_usd=20.0,
        actor="operator",
    )

    metrics = service.run_metrics(ids["org"], ids["facility"], ids["run"])
    assert metrics["yield_pct"] == 20.0
    assert metrics["projected_output_value"] == 240.0
    assert metrics["total_cogs"] == 120.0
    assert metrics["projected_gross_profit"] == 120.0
    assert metrics["projected_margin_pct"] == 50.0
    assert metrics["solvent_recovery_pct"] == 90.0
    assert metrics["resource_cost"] == 20.0

    with sessions() as session:
        resources = list(session.scalars(select(ExtractionResourceEvent)))
        costs = list(
            session.scalars(
                select(ExtractionCostEvent).where(
                    ExtractionCostEvent.run_id == ids["run"],
                    ExtractionCostEvent.source_type == "resource_usage",
                )
            )
        )
        assert len(resources) == 1
        assert len(costs) == 1
        assert costs[0].amount_usd == 20.0


def test_peer_benchmark_is_scoped_to_same_workflow(extraction_env):
    engine, _sessions, ids = extraction_env
    service = ExtractionPerformanceService(engine)
    benchmark = service.peer_benchmark(ids["org"], ids["facility"], ids["run"])
    assert benchmark["peer_count"] == 1
    assert benchmark["yield_median"] == 25.0
    assert benchmark["target"]["batch_number"] == "BHO-100"


def test_performance_exceptions_flag_material_yield_and_cost_outliers():
    board = pd.DataFrame(
        [
            {"run_id": "1", "Run": "R-1", "Method": "BHO", "Status": "Active", "Yield %": 10.0, "Cost / Output": 10.0},
            {"run_id": "2", "Run": "R-2", "Method": "BHO", "Status": "Active", "Yield %": 20.0, "Cost / Output": 5.0},
            {"run_id": "3", "Run": "R-3", "Method": "BHO", "Status": "Active", "Yield %": 21.0, "Cost / Output": 5.2},
            {"run_id": "4", "Run": "R-4", "Method": "BHO", "Status": "Active", "Yield %": 22.0, "Cost / Output": 5.1},
        ]
    )

    def base_builder(_board):
        return []

    exceptions = _performance_exceptions(board, base_builder)
    titles = [item.title for item in exceptions]
    assert any("R-1: yield is materially below peers" == title for title in titles)
    assert any("R-1: cost per output is above peers" == title for title in titles)
