from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from modules.coman.models import ProductBom
from modules.production_erp.models import ProductionBomStandard
from modules.production_erp.service import ProductionERPService


ROOT = Path(__file__).resolve().parents[1]


def test_standard_scale_uses_canonical_bom_batch_quantity():
    bom = ProductBom(output_quantity=100.0)
    assert ProductionERPService._standard_scale(bom, 250.0) == 2.5
    assert ProductionERPService._standard_scale(None, 250.0) == 1.0


def test_variance_math_and_actual_execution_reuse_run_events():
    start = datetime(2026, 8, 27, 8, 0, 0)
    events = [
        SimpleNamespace(event_type="started", occurred_at=start, labor_hours=1.0, machine_hours=0.5),
        SimpleNamespace(event_type="measurement", occurred_at=start + timedelta(hours=2), labor_hours=2.0, machine_hours=1.5),
        SimpleNamespace(event_type="completed", occurred_at=start + timedelta(hours=4), labor_hours=None, machine_hours=None),
    ]
    actual = ProductionERPService._actual_execution(events, None)
    assert actual["actual_labor_hours"] == 3.0
    assert actual["actual_machine_hours"] == 2.0
    assert actual["actual_cycle_hours"] == 4.0
    assert ProductionERPService._variance_pct(12.0, 10.0) == 20.0
    assert ProductionERPService._variance_pct(8.0, 10.0) == -20.0
    assert ProductionERPService._variance_pct(8.0, 0.0) is None


def test_production_standard_is_one_to_one_with_bom_and_auditable():
    constraints = " ".join(str(item) for item in ProductionBomStandard.__table__.constraints)
    assert "bom_id" in constraints
    assert hasattr(ProductionBomStandard, "standard_labor_hours")
    assert hasattr(ProductionBomStandard, "standard_machine_hours")
    assert hasattr(ProductionBomStandard, "standard_cycle_hours")
    assert hasattr(ProductionBomStandard, "resource_category")
    assert hasattr(ProductionBomStandard, "qa_required")
    assert hasattr(ProductionBomStandard, "compliance_checkpoint")
    assert hasattr(ProductionBomStandard, "created_by")
    assert hasattr(ProductionBomStandard, "updated_by")


def test_production_standard_migration_chains_from_current_head():
    migration = (ROOT / "migrations" / "versions" / "0046_production_bom_standards.py").read_text(encoding="utf-8")
    assert 'revision = "0046_production_bom_standards"' in migration
    assert 'down_revision = "0045_native_integrations"' in migration
    assert '"production_bom_standards"' in migration
    assert 'sa.UniqueConstraint("bom_id"' in migration


def test_run_360_owns_standard_configuration_and_variance_surface():
    router = (ROOT / "backend" / "app" / "routers" / "production.py").read_text(encoding="utf-8")
    service = (ROOT / "modules" / "production_erp" / "service.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "src" / "pages" / "ProductionRun360Page.tsx").read_text(encoding="utf-8")

    assert '@router.post("/orders/{order_id}/standard")' in router
    assert '"standard": _standard_payload(snapshot["standard"])' in router
    assert '"variance": snapshot["variance"]' in router
    assert "def upsert_bom_standard(" in service
    assert 'action="production_standard_updated"' in service
    assert '"standard_configured": standard is not None' in service
    assert '"Standards"' in frontend
    assert "Expected vs actual execution" in frontend
    assert "Standard labor hours / BOM batch" in frontend
    assert "Standard machine hours / BOM batch" in frontend
    assert "Standard cycle hours / BOM batch" in frontend
    assert "QA release required" in frontend
    assert "Compliance checkpoint" in frontend
    assert "/standard`" in frontend
