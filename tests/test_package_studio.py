import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import (
    AuditEvent,
    Base,
    Facility,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
)
from modules.navigation.role_home import actions_for_role
from modules.package_studio.models import PackageStudioOutput, PackageStudioRun
from modules.package_studio.service import (
    PackageStudioInputPlan,
    PackageStudioOutputPlan,
    PackageStudioPlan,
    PackageStudioService,
)
from modules.package_studio.ui import ACTION_LABELS
from backend.app.auth import get_authorization_engine
from backend.app.database import get_engine
from backend.app.main import app
from backend.app.routers.package_studio import COMMIT_ROLES


ROOT = Path(__file__).resolve().parents[1]


def _fixture():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org = Organization(name="Studio Test", slug="studio-test", active=True)
        session.add(org)
        session.flush()
        facility = Facility(
            organization_id=org.id,
            name="Studio Facility",
            code="STUDIO",
            timezone_name="America/New_York",
            active=True,
        )
        source_product = Product(
            organization_id=org.id,
            sku="BULK-001",
            name="Blue Harbor Bulk Flower",
            item_type="cannabis",
            base_unit="g",
            unit_cost=2.0,
            retail_price=0.0,
            active=True,
        )
        finished_product = Product(
            organization_id=org.id,
            sku="BH-35",
            name="Blue Harbor Flower 3.5g",
            item_type="finished_good",
            base_unit="unit",
            unit_cost=8.0,
            retail_price=30.0,
            active=True,
        )
        session.add_all([facility, source_product, finished_product])
        session.flush()
        source_lot = InventoryLot(
            organization_id=org.id,
            facility_id=facility.id,
            product_id=source_product.id,
            lot_code="BULK-LOT-1",
            compliance_package_id="1A406TESTBULK",
            location_code="VAULT",
            status="available",
        )
        session.add(source_lot)
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=org.id,
                facility_id=facility.id,
                lot_id=source_lot.id,
                transaction_type="receipt",
                quantity_delta=1000.0,
                unit="g",
                reason="test seed",
                reference="seed",
                actor="test",
            )
        )
        session.commit()
        return engine, org.id, facility.id, source_product.id, finished_product.id, source_lot.id


def _balance(engine, lot_id):
    with Session(engine) as session:
        return float(
            session.scalar(
                select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                    InventoryTransaction.lot_id == lot_id
                )
            )
            or 0.0
        )


def test_pack_down_commits_atomically_and_creates_source_trail():
    engine, org_id, facility_id, _source_product_id, finished_product_id, source_lot_id = _fixture()
    service = PackageStudioService(engine)
    plan = PackageStudioPlan(
        action_type="pack_down",
        inputs=(PackageStudioInputPlan(source_lot_id, 350.0, "g"),),
        outputs=(
            PackageStudioOutputPlan(
                product_id=finished_product_id,
                lot_code="BH-35-100",
                inventory_quantity=100,
                inventory_unit="unit",
                source_equivalent_quantity=350.0,
                source_equivalent_unit="g",
                compliance_package_id="1A406TESTCHILD",
            ),
        ),
        source_unit="g",
        reason="Retail pack down",
    )

    preview = service.preview(plan)
    assert preview.balanced is True
    assert preview.total_input == 350.0
    assert preview.total_output_source_equivalent == 350.0

    result = service.commit(
        plan,
        organization_id=org_id,
        facility_id=facility_id,
        actor="buyer@example",
    )
    assert result.run_number.startswith("PS-")
    assert len(result.output_lot_ids) == 1
    assert math.isclose(_balance(engine, source_lot_id), 650.0)
    assert math.isclose(_balance(engine, result.output_lot_ids[0]), 100.0)

    trail = service.source_trail(
        result.output_lot_ids[0],
        organization_id=org_id,
        facility_id=facility_id,
    )
    assert trail["created_by"]["action_type"] == "pack_down"
    assert trail["created_by"]["parents"][0]["lot_id"] == source_lot_id

    with Session(engine) as session:
        run = session.scalar(select(PackageStudioRun).where(PackageStudioRun.id == result.run_id))
        assert run.external_sync_status == "not_requested"
        assert run.status == "committed"
        assert session.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.entity_id == result.run_id)) == 1


def test_multi_build_supports_multiple_outputs_and_records_loss():
    engine, org_id, facility_id, _source_product_id, finished_product_id, source_lot_id = _fixture()
    service = PackageStudioService(engine)
    plan = PackageStudioPlan(
        action_type="multi_build",
        inputs=(PackageStudioInputPlan(source_lot_id, 362.0, "g"),),
        outputs=(
            PackageStudioOutputPlan(
                product_id=finished_product_id,
                lot_code="MULTI-01",
                inventory_quantity=50,
                inventory_unit="unit",
                source_equivalent_quantity=175.0,
                source_equivalent_unit="g",
            ),
            PackageStudioOutputPlan(
                product_id=finished_product_id,
                lot_code="MULTI-02",
                inventory_quantity=50,
                inventory_unit="unit",
                source_equivalent_quantity=175.0,
                source_equivalent_unit="g",
            ),
        ),
        source_unit="g",
        loss_quantity=12.0,
    )
    preview = service.preview(plan)
    assert preview.output_count == 2
    assert preview.loss_quantity == 12.0
    result = service.commit(plan, organization_id=org_id, facility_id=facility_id, actor="operator")
    assert len(result.output_lot_ids) == 2
    assert math.isclose(_balance(engine, source_lot_id), 638.0)


def test_breakdown_and_sample_pull_preserve_source_product_identity():
    engine, org_id, facility_id, source_product_id, finished_product_id, source_lot_id = _fixture()
    service = PackageStudioService(engine)
    invalid = PackageStudioPlan(
        action_type="breakdown",
        inputs=(PackageStudioInputPlan(source_lot_id, 100.0, "g"),),
        outputs=(
            PackageStudioOutputPlan(
                product_id=finished_product_id,
                lot_code="WRONG-PRODUCT",
                inventory_quantity=100.0,
                inventory_unit="g",
                source_equivalent_quantity=100.0,
                source_equivalent_unit="g",
            ),
        ),
        source_unit="g",
    )
    with pytest.raises(ValueError, match="keep the source product identity"):
        service.commit(invalid, organization_id=org_id, facility_id=facility_id, actor="operator")

    valid = PackageStudioPlan(
        action_type="sample_pull",
        inputs=(PackageStudioInputPlan(source_lot_id, 5.0, "g"),),
        outputs=(
            PackageStudioOutputPlan(
                product_id=source_product_id,
                lot_code="LAB-SAMPLE-1",
                inventory_quantity=5.0,
                inventory_unit="g",
                source_equivalent_quantity=5.0,
                source_equivalent_unit="g",
                purpose="lab_sample",
            ),
        ),
        source_unit="g",
    )
    result = service.commit(valid, organization_id=org_id, facility_id=facility_id, actor="qa")
    with Session(engine) as session:
        output = session.scalar(select(PackageStudioOutput).where(PackageStudioOutput.lot_id == result.output_lot_ids[0]))
        assert output.purpose == "lab_sample"


def test_unbalanced_run_is_rejected_before_inventory_changes():
    engine, org_id, facility_id, _source_product_id, finished_product_id, source_lot_id = _fixture()
    service = PackageStudioService(engine)
    plan = PackageStudioPlan(
        action_type="pack_down",
        inputs=(PackageStudioInputPlan(source_lot_id, 350.0, "g"),),
        outputs=(
            PackageStudioOutputPlan(
                product_id=finished_product_id,
                lot_code="UNBALANCED",
                inventory_quantity=100,
                inventory_unit="unit",
                source_equivalent_quantity=340.0,
                source_equivalent_unit="g",
            ),
        ),
        source_unit="g",
    )
    with pytest.raises(ValueError, match="balance exactly"):
        service.commit(plan, organization_id=org_id, facility_id=facility_id, actor="buyer")
    assert math.isclose(_balance(engine, source_lot_id), 1000.0)


def test_package_studio_uses_buyer_dash_nomenclature_not_distru_labels():
    assert set(ACTION_LABELS) == {
        "Breakdown",
        "Pack Down",
        "Build Run",
        "Multi-Build",
        "Sample Pull",
        "Rework",
        "Source Correction",
    }
    public_labels = " ".join(ACTION_LABELS).casefold()
    assert "assembly" not in public_labels
    assert "split package" not in public_labels
    assert any(action.intent == "package_studio" for action in actions_for_role("buyer"))
    assert not any(action.intent == "package_studio" for action in actions_for_role("read_only"))
    assert COMMIT_ROLES == {"dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"}


def test_react_package_studio_keeps_the_streamlit_tabs_controls_and_drawer_prefill():
    page = (ROOT / "frontend" / "src" / "pages" / "PackageStudioPage.tsx").read_text(encoding="utf-8")
    inventory = (ROOT / "frontend" / "src" / "pages" / "InventoryPage.tsx").read_text(encoding="utf-8")
    for label in [
        "PACKAGE STUDIO", "Package transformation", "New Run", "Source Trail", "Recent Runs",
        "Package action", "Source package", "Available", "Source", "Product", "Location",
        "Number of outputs", "Recorded loss / waste", "Reason / work note", "Outputs",
        "Output product", "Lot / package code", "METRC package tag", "Finished quantity",
        "Finished unit", "Source used", "Sample type", "Output purpose", "Mass balance preview",
        "I reviewed the source, outputs, and mass balance.", "Parent source", "Downstream use",
    ]:
        assert label in page
    for label in ACTION_LABELS:
        assert f'["{label}"' in page
    assert "Preview balance" not in page
    assert "initialLotId={first?.id}" in inventory


def test_migration_0017_tracks_package_studio_lineage():
    migration = (ROOT / "migrations" / "versions" / "0017_package_studio.sql").read_text(encoding="utf-8")
    assert "package_studio_runs" in migration
    assert "package_studio_inputs" in migration
    assert "package_studio_outputs" in migration
    assert "0017_package_studio" in migration


def test_web_package_studio_restores_workspace_preview_commit_and_source_trail():
    engine, org_id, facility_id, _source_product_id, finished_product_id, source_lot_id = _fixture()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    client = TestClient(app)
    buyer = {"X-Organization-Id": org_id, "X-Facility-Id": facility_id, "X-User-Id": "buyer-user", "X-User-Role": "buyer"}
    read_only = {**buyer, "X-User-Id": "read-user", "X-User-Role": "read_only"}
    plan = {
        "action_type": "pack_down",
        "inputs": [{"lot_id": source_lot_id, "quantity": 350, "unit": "g", "purpose": "source"}],
        "outputs": [{
            "product_id": finished_product_id,
            "lot_code": "WEB-PACK-1",
            "inventory_quantity": 100,
            "inventory_unit": "unit",
            "source_equivalent_quantity": 350,
            "source_equivalent_unit": "g",
            "compliance_package_id": "1A406WEBPACK",
            "purpose": "standard",
        }],
        "loss_quantity": 0,
        "source_unit": "g",
        "reason": "Web Package Studio parity",
    }
    try:
        workspace_response = client.get("/api/v1/package-studio/workspace", headers=buyer)
        assert workspace_response.status_code == 200, workspace_response.text
        assert workspace_response.json()["can_commit"] is True
        assert workspace_response.json()["lots"][0]["lot_id"] == source_lot_id

        read_workspace = client.get("/api/v1/package-studio/workspace", headers=read_only)
        assert read_workspace.status_code == 200
        assert read_workspace.json()["can_commit"] is False
        assert client.post("/api/v1/package-studio/commit", headers=read_only, json=plan).status_code == 403

        preview_response = client.post("/api/v1/package-studio/preview", headers=buyer, json=plan)
        assert preview_response.status_code == 200, preview_response.text
        assert preview_response.json()["balanced"] is True

        commit_response = client.post("/api/v1/package-studio/commit", headers=buyer, json=plan)
        assert commit_response.status_code == 201, commit_response.text
        output_lot_id = commit_response.json()["output_lot_ids"][0]
        trail_response = client.get(f"/api/v1/package-studio/source-trail/{output_lot_id}", headers=buyer)
        assert trail_response.status_code == 200, trail_response.text
        assert trail_response.json()["created_by"]["action_type"] == "pack_down"
        assert trail_response.json()["created_by"]["parents"][0]["lot_id"] == source_lot_id
    finally:
        app.dependency_overrides.clear()
