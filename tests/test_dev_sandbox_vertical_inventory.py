from __future__ import annotations

from collections import Counter
import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman import ComanRepository
from modules.coman.models import Base, InventoryLot, Product
from modules.coman.vertical_demo_inventory import retire_dev_sandbox_inventory
from modules.coman.vertical_demo_inventory_release import (
    EXPECTED_ACTIVE_PLANTS,
    EXPECTED_EXTRACT_SKUS,
    EXPECTED_FINISHED_SKUS,
    EXPECTED_FLOWER_SKUS,
    EXPECTED_MOCK_FINISHED_COAS,
    EXPECTED_TOTAL_PLANTS,
    replace_scaled_vertical_dev_inventory,
)
from modules.coman.vertical_demo_ma_coas import (
    DEV_MA_COA_EVIDENCE,
    DEV_MA_COA_SOURCE,
    DEV_MA_INHERITED_EVIDENCE,
    EXPECTED_MA_FLOWER_REFERENCE_COAS,
    MA_FLOWER_REFERENCE_STRAINS,
)
from modules.cultivation.service import ACTIVE_PLANT_PHASES, CultivationService
from modules.demo_traceability import is_synthetic_metrc_tag
from modules.inventory_quality.models import CoaAnalyteResult, CoaDocument, LotQualityEvidence
from scripts.reset_dev_sandbox_vertical_inventory import _validate


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _opening_lot(
    coman: ComanRepository,
    organization_id: str,
    facility_id: str,
    *,
    sku: str,
    lot_code: str,
    quantity: float,
):
    product = coman.create_product(
        organization_id,
        sku=sku,
        name=f"Old {sku}",
        item_type="finished_good",
        base_unit="unit",
        unit_cost=1,
        retail_price=10,
        actor="test",
    )
    lot = coman.create_inventory_lot(
        organization_id,
        facility_id,
        product_id=product.id,
        lot_code=lot_code,
        actor="test",
    )
    coman.post_inventory_transaction(
        organization_id,
        facility_id,
        lot_id=lot.id,
        transaction_type="receipt",
        quantity_delta=quantity,
        unit="unit",
        actor="test",
    )
    return product, lot


def test_scaled_vertical_dev_inventory_is_realistic_sourced_only_and_repeatable():
    engine = _engine()
    coman = ComanRepository(engine)
    dev = coman.create_organization("DEV Sandbox")
    sandbox = coman.create_facility(dev.id, "Sandbox", "SANDBOX")

    # A separate demo/customer tenant is the blast-radius canary. DEV reset must
    # never change it.
    cowboy = coman.create_organization("Cowboy Kush Demo", slug="cowboy-kush")
    cowboy_facility = coman.create_facility(cowboy.id, "Cowboy Kush", "COWBOY")

    old_product, old_lot = _opening_lot(
        coman,
        dev.id,
        sandbox.id,
        sku="OLD-DEV-SKU",
        lot_code="OLD-DEV-LOT",
        quantity=25,
    )
    cowboy_product, cowboy_lot = _opening_lot(
        coman,
        cowboy.id,
        cowboy_facility.id,
        sku="COWBOY-SKU",
        lot_code="COWBOY-LOT",
        quantity=13,
    )

    first = replace_scaled_vertical_dev_inventory(engine, dev.id, sandbox.id, generation="GEN1")
    assert first.retired_lots == 1
    assert first.retired_quantity == 25
    assert first.plants == EXPECTED_TOTAL_PLANTS == 120
    assert first.harvests == 10
    assert first.flower_source_lots == 10
    assert first.trim_source_lots == 10
    assert len(first.flower_final_lots) == EXPECTED_FLOWER_SKUS == 350
    assert len(first.extraction_bulk_lots) == 30
    assert len(first.extract_final_lots) == EXPECTED_EXTRACT_SKUS == 150
    assert len(first.final_lots) == EXPECTED_FINISHED_SKUS == 500
    assert len(first.final_product_ids) == EXPECTED_FINISHED_SKUS

    validation = _validate(engine, dev.id, sandbox.id, first)
    assert validation["finished_lots"] == 500
    assert validation["wholesale_eligible"] == 350
    assert validation["wholesale_blocked"] == 150
    assert validation["canonical_quality"] == 500
    assert validation["sourced_finished_coas"] == 350
    assert validation["unsourced_finished_items"] == 150
    assert validation["mock_finished_coas"] == EXPECTED_MOCK_FINISHED_COAS == 0
    assert validation["realistic_package_tags"] == 500
    assert validation["packaging_profiles"] == 500
    assert validation["positive_cogs"] == 500
    assert validation["active_plants"] == EXPECTED_ACTIVE_PLANTS == 80
    assert validation["active_plant_phases"] == {
        "clone": 20,
        "seedling": 20,
        "vegetative": 20,
        "flowering": 20,
    }
    assert validation["plant_ancestry"] == 500
    assert validation["extraction_graphs"] == 150
    assert validation["finished_lots_in_extraction_picker"] == 0
    assert validation["purchase_orders"] == 6
    assert validation["purchase_order_statuses"] == {"draft": 3, "confirmed": 3}
    assert validation["sales_orders"] == 12
    assert validation["sales_order_statuses"] == {
        "draft": 3,
        "confirmed": 3,
        "allocated": 3,
        "partially_fulfilled": 2,
        "fulfilled": 1,
    }
    assert validation["sales_order_allocations"] == 30
    assert validation["sales_order_shipments"] == 9
    assert validation["lots_with_wholesale_reservations"] > 0

    with Session(engine) as session:
        ma_documents = list(
            session.scalars(
                select(CoaDocument).where(
                    CoaDocument.organization_id == dev.id,
                    CoaDocument.facility_id == sandbox.id,
                    CoaDocument.source == DEV_MA_COA_SOURCE,
                )
            )
        )
        assert len(ma_documents) == EXPECTED_MA_FLOWER_REFERENCE_COAS == 10
        assert {row.strain_name for row in ma_documents} == set(MA_FLOWER_REFERENCE_STRAINS)
        for document in ma_documents:
            raw = json.loads(document.raw_payload_json)
            assert raw["source_state"] == "MA"
            assert raw["sandbox_mapping"]["mapping_type"] == "strain_match_external_reference"
            assert raw["sandbox_mapping"]["external_reference_only"] is True
            assert "does not certify the sandbox package" in raw["sandbox_mapping"]["sandbox_release_basis"]
            assert document.package_id == ""
            assert document.lot_id is None
            assert document.verification_state == "external_reference"
            # Provenance identifiers from the public source stay attached to the
            # reference document; current sandbox package identity remains separate.
            assert not str(document.metrc_source_id or "").startswith("DEV")

        super_lemon = next(row for row in ma_documents if row.strain_name == "Super Lemon Haze")
        super_lemon_results = list(
            session.scalars(
                select(CoaAnalyteResult).where(CoaAnalyteResult.coa_document_id == super_lemon.id)
            )
        )
        assert len(super_lemon_results) == 37
        assert any(row.value_text == "<LOQ" for row in super_lemon_results)
        assert super_lemon.total_thc_percent == 24.87
        assert super_lemon.total_cannabinoids_percent == 29.55
        assert super_lemon.total_terpenes_percent == 1.69

        # No operator-visible finished lot may retain a fabricated/mock COA.
        mock_quality = list(
            session.scalars(
                select(LotQualityEvidence).where(
                    LotQualityEvidence.organization_id == dev.id,
                    LotQualityEvidence.facility_id == sandbox.id,
                    LotQualityEvidence.evidence_source == "mock_finished_lab",
                )
            )
        )
        assert mock_quality == []

        flower_lots = list(
            session.scalars(select(InventoryLot).where(InventoryLot.id.in_(first.flower_final_lots)))
        )
        assert len(flower_lots) == 350
        flower_quality = [session.get(LotQualityEvidence, lot.id) for lot in flower_lots]
        assert all(row is not None for row in flower_quality)
        assert all(
            row.evidence_source == DEV_MA_INHERITED_EVIDENCE and row.coa_document_id
            for row in flower_quality
            if row is not None
        )
        assert all(is_synthetic_metrc_tag(lot.compliance_package_id) for lot in flower_lots)
        assert all("example.invalid" not in (row.coa_url or "") for row in flower_quality if row is not None)
        for lot in flower_lots:
            meta = json.loads(lot.notes or "{}")
            assert meta["harvest_date"]
            assert meta["package_date"]
            assert meta["manufacture_date"]
            assert meta["package_date_basis"] in {"lot_received_at", "harvest_date_fallback"}
            assert meta["cultivated_by"] == sandbox.name
            assert meta["packaged_by"] == sandbox.name
            assert meta["sold_by"] == sandbox.name
            assert "example.invalid/dev-coa" not in lot.notes

        extract_lots = list(
            session.scalars(select(InventoryLot).where(InventoryLot.id.in_(first.extract_final_lots)))
        )
        assert len(extract_lots) == 150
        assert all(is_synthetic_metrc_tag(lot.compliance_package_id) for lot in extract_lots)
        for lot in extract_lots:
            evidence = session.get(LotQualityEvidence, lot.id)
            assert evidence is not None
            assert evidence.evidence_source == "dev_sandbox:no_sourced_coa"
            assert evidence.lab_testing_state == ""
            assert evidence.coa_reference == ""
            assert evidence.coa_url == ""
            assert evidence.coa_document_id is None
            assert evidence.total_thc_percent is None
            assert evidence.total_terpenes_percent is None

        blue_root = session.scalar(
            select(InventoryLot).where(InventoryLot.lot_code == "DEVV-GEN1-S04-FLOWER")
        )
        blue_child = session.scalar(
            select(InventoryLot).where(InventoryLot.lot_code == "DEVV-GEN1-S04-F01")
        )
        assert blue_root is not None and blue_child is not None
        blue_root_quality = session.get(LotQualityEvidence, blue_root.id)
        blue_child_quality = session.get(LotQualityEvidence, blue_child.id)
        assert blue_root_quality is not None and blue_root_quality.coa_document_id
        assert blue_child_quality is not None
        assert blue_child_quality.inherited_from_lot_id == blue_root.id
        assert blue_child_quality.coa_document_id == blue_root_quality.coa_document_id
        blue_document = session.get(CoaDocument, blue_root_quality.coa_document_id)
        assert blue_document is not None
        assert blue_root_quality.evidence_source == DEV_MA_COA_EVIDENCE
        assert blue_child_quality.evidence_source == DEV_MA_INHERITED_EVIDENCE
        assert blue_document.package_id == ""
        assert blue_document.lot_id is None
        assert blue_document.verification_state == "external_reference"
        assert is_synthetic_metrc_tag(blue_child.compliance_package_id)
        assert is_synthetic_metrc_tag(blue_root.compliance_package_id)
        assert blue_child.compliance_package_id != blue_root.compliance_package_id

        old_lot_row = session.get(InventoryLot, old_lot.id)
        old_product_row = session.get(Product, old_product.id)
        cowboy_lot_row = session.get(InventoryLot, cowboy_lot.id)
        cowboy_product_row = session.get(Product, cowboy_product.id)
        assert old_lot_row is not None and old_lot_row.status == "depleted"
        assert old_product_row is not None and not old_product_row.active
        assert cowboy_lot_row is not None and cowboy_lot_row.status == "available"
        assert cowboy_product_row is not None and cowboy_product_row.active
    assert coman.inventory_balance(dev.id, old_lot.id) == 0
    assert coman.inventory_balance(cowboy.id, cowboy_lot.id) == 13

    first_ids = set(first.final_lots)
    first_tags = {}
    with Session(engine) as session:
        first_tags = {lot_id: session.get(InventoryLot, lot_id).compliance_package_id for lot_id in first_ids}

    second = replace_scaled_vertical_dev_inventory(engine, dev.id, sandbox.id, generation="GEN2")
    second_ids = set(second.final_lots)
    assert len(second_ids) == 500
    assert second_ids.isdisjoint(first_ids)
    assert all(coman.inventory_balance(dev.id, lot_id) == 0 for lot_id in first_ids)
    with Session(engine) as session:
        # Historical traceability identity must not be rewritten by a later DEV reset.
        assert all(session.get(InventoryLot, lot_id).status == "depleted" for lot_id in first_ids)
        assert all(session.get(InventoryLot, lot_id).compliance_package_id == first_tags[lot_id] for lot_id in first_ids)

    second_validation = _validate(engine, dev.id, sandbox.id, second)
    assert second_validation["wholesale_eligible"] == 350
    assert second_validation["wholesale_blocked"] == 150
    assert second_validation["mock_finished_coas"] == 0
    assert second_validation["plant_ancestry"] == 500
    assert second_validation["extraction_graphs"] == 150
    assert second_validation["sales_orders"] == 12
    assert second_validation["purchase_orders"] == 6
    assert coman.inventory_balance(cowboy.id, cowboy_lot.id) == 13

    plants = CultivationService(engine).list_plants(dev.id, sandbox.id)
    active = Counter(row.phase for row in plants if row.phase in ACTIVE_PLANT_PHASES)
    assert active == Counter({"clone": 20, "seedling": 20, "vegetative": 20, "flowering": 20})
    assert all(is_synthetic_metrc_tag(row.plant_tag) for row in plants if row.phase in ACTIVE_PLANT_PHASES)


def test_dev_inventory_reset_refuses_non_dev_tenant_before_any_mutation():
    engine = _engine()
    coman = ComanRepository(engine)
    other = coman.create_organization("Production Organization")
    facility = coman.create_facility(other.id, "Main", "SANDBOX")
    cultivation = CultivationService(engine)
    plant = cultivation.create_plant(
        other.id,
        facility.id,
        plant_tag="OTHER-PLANT-001",
        strain_name="Control Strain",
        phase="vegetative",
        room_code="VEG",
        actor="test",
    )
    _, lot = _opening_lot(
        coman,
        other.id,
        facility.id,
        sku="OTHER-SKU",
        lot_code="OTHER-LOT",
        quantity=9,
    )

    try:
        replace_scaled_vertical_dev_inventory(engine, other.id, facility.id, generation="SHOULDFAIL")
    except RuntimeError as exc:
        assert "dev-sandbox" in str(exc)
    else:
        raise AssertionError("Non-DEV tenant reset must be rejected.")

    refreshed = next(row for row in cultivation.list_plants(other.id, facility.id) if row.id == plant.id)
    assert refreshed.phase == "vegetative"
    assert refreshed.plant_tag == "OTHER-PLANT-001"
    assert coman.inventory_balance(other.id, lot.id) == 9

    try:
        retire_dev_sandbox_inventory(engine, other.id, facility.id)
    except RuntimeError as exc:
        assert "dev-sandbox" in str(exc)
    else:
        raise AssertionError("Base DEV retirement guard must also reject non-DEV tenants.")
