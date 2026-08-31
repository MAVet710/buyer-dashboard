from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman import ComanRepository
from modules.coman.models import Base, InventoryLot, Product
from modules.coman.vertical_demo_inventory import replace_dev_sandbox_inventory, retire_dev_sandbox_inventory
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.extraction import ExtractionRepository
from modules.inventory_quality import LotQualityEvidence
from modules.material_lineage.service import MaterialLineageService
from modules.product_master import ProductPackagingProfile


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine


def _opening_lot(coman: ComanRepository, organization_id: str, facility_id: str, *, sku: str, lot_code: str, quantity: float):
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
        status="available",
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


def test_vertical_dev_inventory_replaces_only_dev_sandbox_and_is_repeatable():
    engine = _engine()
    coman = ComanRepository(engine)
    dev = coman.create_organization("DEV Sandbox")
    sandbox = coman.create_facility(dev.id, "Sandbox", "SANDBOX")
    other = coman.create_organization("Other Tenant")
    other_facility = coman.create_facility(other.id, "Other", "OTHER")

    old_product, old_lot = _opening_lot(
        coman,
        dev.id,
        sandbox.id,
        sku="OLD-DEV-SKU",
        lot_code="OLD-DEV-LOT",
        quantity=25,
    )
    other_product, other_lot = _opening_lot(
        coman,
        other.id,
        other_facility.id,
        sku="OTHER-SKU",
        lot_code="OTHER-LOT",
        quantity=13,
    )

    first = replace_dev_sandbox_inventory(engine, dev.id, sandbox.id, generation="GEN1")
    assert first.retired_lots == 1
    assert first.retired_quantity == 25
    assert first.plants == 20
    assert first.harvests == 10
    assert first.flower_source_lots == 10
    assert first.trim_source_lots == 10
    assert len(first.flower_final_lots) == 70
    assert len(first.extraction_bulk_lots) == 30
    assert len(first.extract_final_lots) == 30
    assert len(first.final_lots) == 100
    assert len(first.final_product_ids) == 100

    with Session(engine) as session:
        old_lot_row = session.get(InventoryLot, old_lot.id)
        old_product_row = session.get(Product, old_product.id)
        other_lot_row = session.get(InventoryLot, other_lot.id)
        other_product_row = session.get(Product, other_product.id)
        assert old_lot_row is not None and old_lot_row.status == "depleted"
        assert old_product_row is not None and not old_product_row.active
        assert other_lot_row is not None and other_lot_row.status == "available"
        assert other_product_row is not None and other_product_row.active
    assert coman.inventory_balance(dev.id, old_lot.id) == 0
    assert coman.inventory_balance(other.id, other_lot.id) == 13

    wholesale = WholesaleCommerceStorefrontService(engine).wholesale_inventory(dev.id, sandbox.id)
    first_ids = set(first.final_lots)
    assert len([row for row in wholesale["items"] if row["lot_id"] in first_ids]) == 100
    assert not [row for row in wholesale["blocked_items"] if row["lot_id"] in first_ids]

    with Session(engine) as session:
        assert all(session.get(LotQualityEvidence, lot_id) is not None for lot_id in first.final_lots)
        assert all(session.get(ProductPackagingProfile, product_id) is not None for product_id in first.final_product_ids)
        assert all((session.get(Product, product_id).unit_cost if session.get(Product, product_id) else 0) > 0 for product_id in first.final_product_ids)

    lineage = MaterialLineageService(engine)
    extraction_graphs = 0
    for lot_id in first.final_lots:
        graph = lineage.lot_graph(organization_id=dev.id, facility_id=sandbox.id, lot_id=lot_id)
        assert any(node["type"] == "plant" for node in graph["nodes"])
        if lot_id in set(first.extract_final_lots) and any(node.get("transformation_type") == "extraction_run" for node in graph["nodes"]):
            extraction_graphs += 1
    assert extraction_graphs == 30

    picker_ids = {row["lot_id"] for row in ExtractionRepository(engine).list_available_lots(dev.id, sandbox.id)}
    assert first_ids.isdisjoint(picker_ids)

    second = replace_dev_sandbox_inventory(engine, dev.id, sandbox.id, generation="GEN2")
    assert len(second.final_lots) == 100
    assert set(second.final_lots).isdisjoint(first_ids)
    assert all(coman.inventory_balance(dev.id, lot_id) == 0 for lot_id in first.final_lots)
    with Session(engine) as session:
        assert all(session.get(InventoryLot, lot_id).status == "depleted" for lot_id in first.final_lots)

    second_wholesale = WholesaleCommerceStorefrontService(engine).wholesale_inventory(dev.id, sandbox.id)
    second_ids = set(second.final_lots)
    assert len([row for row in second_wholesale["items"] if row["lot_id"] in second_ids]) == 100
    assert not first_ids.intersection({row["lot_id"] for row in second_wholesale["items"]})
    assert coman.inventory_balance(other.id, other_lot.id) == 13


def test_dev_inventory_reset_refuses_non_dev_tenant():
    engine = _engine()
    coman = ComanRepository(engine)
    other = coman.create_organization("Production Organization")
    facility = coman.create_facility(other.id, "Main", "SANDBOX")
    try:
        retire_dev_sandbox_inventory(engine, other.id, facility.id)
    except RuntimeError as exc:
        assert "dev-sandbox" in str(exc)
    else:
        raise AssertionError("Non-DEV tenant reset must be rejected.")
