from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.services.sandbox_policy import SANDBOX_TEST_ARTIFACT_MARK, sandbox_execution_policy
from modules.coman import ComanRepository
from modules.coman.models import Base
from modules.coman.vertical_demo_integrity import enforce_vertical_demo_integrity
from modules.cultivation.service import CultivationService
from modules.demo_traceability import is_synthetic_metrc_tag, synthetic_metrc_tag
from modules.inventory_quality import LotQualityService
from modules.inventory_quality.models import LotQualityEvidence


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def test_synthetic_metrc_tag_is_stable_realistic_shaped_and_explicitly_dev_only():
    first = synthetic_metrc_tag("package:demo:1")
    second = synthetic_metrc_tag("package:demo:1")
    other = synthetic_metrc_tag("package:demo:2")

    assert first == second
    assert first != other
    assert len(first) == 24
    assert is_synthetic_metrc_tag(first)
    assert first.startswith("1A40D03")
    assert sum(ch.isdigit() for ch in first) >= 20
    assert not is_synthetic_metrc_tag("DEV-PKG-GEN1-S01-F01")


def test_sandbox_policy_relaxes_only_canonical_dev_admin_scope_and_never_provider_writes():
    engine = _engine()
    repo = ComanRepository(engine)
    dev = repo.create_organization("DEV Sandbox")
    sandbox = repo.create_facility(dev.id, "Sandbox", "SANDBOX")
    other = repo.create_organization("Other Organization", slug="other-org")
    other_facility = repo.create_facility(other.id, "Sandbox", "SANDBOX")

    enabled = sandbox_execution_policy(
        engine,
        organization_id=dev.id,
        facility_id=sandbox.id,
        role="dev",
    )
    assert enabled == {
        "canonical_dev_sandbox": True,
        "developer_authorized": True,
        "operator_rehearsal_enabled": True,
        "label_layout_testing_enabled": True,
        "local_mutations_enabled": True,
        "external_provider_writes_enabled": False,
        "provider_transport": "deterministic_fixture",
        "test_artifact_mark": SANDBOX_TEST_ARTIFACT_MARK,
        "production_guardrails_intact": True,
    }

    operator = sandbox_execution_policy(
        engine,
        organization_id=dev.id,
        facility_id=sandbox.id,
        role="operator",
    )
    assert operator["canonical_dev_sandbox"] is True
    assert operator["developer_authorized"] is False
    assert operator["operator_rehearsal_enabled"] is False
    assert operator["label_layout_testing_enabled"] is False
    assert operator["external_provider_writes_enabled"] is False

    wrong_tenant = sandbox_execution_policy(
        engine,
        organization_id=other.id,
        facility_id=other_facility.id,
        role="dev",
    )
    assert wrong_tenant["developer_authorized"] is True
    assert wrong_tenant["canonical_dev_sandbox"] is False
    assert wrong_tenant["operator_rehearsal_enabled"] is False
    assert wrong_tenant["external_provider_writes_enabled"] is False


def test_integrity_boundary_replaces_current_placeholders_and_clears_unsourced_lab_claims_only():
    engine = _engine()
    repo = ComanRepository(engine)
    dev = repo.create_organization("DEV Sandbox")
    sandbox = repo.create_facility(dev.id, "Sandbox", "SANDBOX")
    product = repo.create_product(
        dev.id,
        sku="DEV-EXTRACT-1",
        name="DEV Extract",
        item_type="finished_good",
        base_unit="g",
        unit_cost=10,
        actor="test",
    )
    lot = repo.create_inventory_lot(
        dev.id,
        sandbox.id,
        product_id=product.id,
        lot_code="DEVV-GEN1-EXTRACT-1",
        compliance_package_id="DEV-PKG-GEN1-EXTRACT-1",
        status="available",
        actor="test",
    )
    repo.post_inventory_transaction(
        dev.id,
        sandbox.id,
        lot_id=lot.id,
        transaction_type="receipt",
        quantity_delta=10,
        unit="g",
        actor="test",
    )
    plant = CultivationService(engine).create_plant(
        dev.id,
        sandbox.id,
        plant_tag="DEVV-GEN1-S01-VE01",
        strain_name="GMO",
        phase="vegetative",
        room_code="DEV-VEGETATIVE",
        actor="test",
    )
    with Session(engine) as session, session.begin():
        LotQualityService.set_evidence(
            session,
            lot_id=lot.id,
            lab_testing_state="Passed",
            coa_reference="DEV-MOCK-FINISHED-COA-GEN1-001",
            coa_url="https://example.invalid/dev-coa/gen1/001.pdf",
            total_thc_percent=81.2,
            total_terpenes_percent=7.4,
            evidence_source="mock_finished_lab",
            actor="test",
        )

    result = enforce_vertical_demo_integrity(
        engine,
        dev.id,
        sandbox.id,
        generation="GEN1",
        actor="test",
    )
    assert result["realistic_package_tags"] == 1
    assert result["realistic_plant_tags"] == 1
    assert result["unsourced_lab_claims_cleared"] == 1

    refreshed_lot = repo.get_inventory_lot(dev.id, sandbox.id, lot.id)
    assert is_synthetic_metrc_tag(refreshed_lot.compliance_package_id)
    refreshed_plant = next(row for row in CultivationService(engine).list_plants(dev.id, sandbox.id) if row.id == plant.id)
    assert is_synthetic_metrc_tag(refreshed_plant.plant_tag)
    with Session(engine) as session:
        evidence = session.get(LotQualityEvidence, lot.id)
        assert evidence is not None
        assert evidence.evidence_source == "dev_sandbox:no_sourced_coa"
        assert evidence.lab_testing_state == ""
        assert evidence.coa_reference == ""
        assert evidence.coa_url == ""
        assert evidence.total_thc_percent is None
        assert evidence.total_terpenes_percent is None


def test_integrity_boundary_refuses_noncanonical_facility():
    engine = _engine()
    repo = ComanRepository(engine)
    organization = repo.create_organization("Production")
    facility = repo.create_facility(organization.id, "Main", "SANDBOX")

    try:
        enforce_vertical_demo_integrity(
            engine,
            organization.id,
            facility.id,
            generation="GEN1",
            actor="test",
        )
    except RuntimeError as exc:
        assert "dev-sandbox" in str(exc)
    else:
        raise AssertionError("Noncanonical tenants must never receive DEV sandbox mutations.")
