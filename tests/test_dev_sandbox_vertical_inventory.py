from __future__ import annotations

from collections import Counter

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman import ComanRepository
from modules.coman.models import Base, InventoryLot, Product
from modules.coman.vertical_demo_inventory import retire_dev_sandbox_inventory
from modules.coman.vertical_demo_inventory_release import (
    EXPECTED_ACTIVE_PLANTS,
    EXPECTED_EXTRACT_SKUS,
    EXPECTED_FINISHED_SKUS,
    EXPECTED_MOCK_FINISHED_COAS,
    EXPECTED_TOTAL_PLANTS,
    replace_scaled_vertical_dev_inventory,
)
from modules.cultivation.service import ACTIVE_PLANT_PHASES, CultivationService
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


def test_scaled_vertical_dev_inventory_replaces_only_dev_and_is_repeatable():
    engine = _engine()
    coman = ComanRepository(engine)
    dev = coman.create_organization("DEV Sandbox")
    sandbox = coman.create_facility(dev.id, "Sandbox", "SANDBOX")

    # Explicitly model the separate Cowboy Kush tenant the user told us never to touch.
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
    assert len(first.flower_final_lots) == 350
    assert len(first.extraction_bulk_lots) == 30
    assert len(first.extract_final_lots) == EXPECTED_EXTRACT_SKUS == 150
    assert len(first.final_lots) == EXPECTED_FINISHED_SKUS == 500
    assert len(first.final_product_ids) == EXPECTED_FINISHED_SKUS

    validation = _validate(engine, dev.id, sandbox.id, first)
    assert validation["finished_lots"] == 500
    assert validation["wholesale_eligible"] == 500
    assert validation["canonical_quality"] == 500
    assert validation["mock_finished_coas"] == EXPECTED_MOCK_FINISHED_COAS == 50
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
    second = replace_scaled_vertical_dev_inventory(engine, dev.id, sandbox.id, generation="GEN2")
    second_ids = set(second.final_lots)
    assert len(second_ids) == 500
    assert second_ids.isdisjoint(first_ids)
    assert all(coman.inventory_balance(dev.id, lot_id) == 0 for lot_id in first_ids)
    with Session(engine) as session:
        assert all(session.get(InventoryLot, lot_id).status == "depleted" for lot_id in first_ids)

    second_validation = _validate(engine, dev.id, sandbox.id, second)
    assert second_validation["wholesale_eligible"] == 500
    assert second_validation["mock_finished_coas"] == 50
    assert second_validation["plant_ancestry"] == 500
    assert second_validation["extraction_graphs"] == 150
    assert second_validation["sales_orders"] == 12
    assert second_validation["purchase_orders"] == 6
    assert coman.inventory_balance(cowboy.id, cowboy_lot.id) == 13

    plants = CultivationService(engine).list_plants(dev.id, sandbox.id)
    active = Counter(row.phase for row in plants if row.phase in ACTIVE_PLANT_PHASES)
    assert active == Counter({"clone": 20, "seedling": 20, "vegetative": 20, "flowering": 20})


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
    assert coman.inventory_balance(other.id, lot.id) == 9

    try:
        retire_dev_sandbox_inventory(engine, other.id, facility.id)
    except RuntimeError as exc:
        assert "dev-sandbox" in str(exc)
    else:
        raise AssertionError("Base DEV retirement guard must also reject non-DEV tenants.")
