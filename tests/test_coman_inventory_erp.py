from sqlalchemy import create_engine, event
from modules.coman.models import Base
from modules.coman.repository import ComanRepository

def setup_repo():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    repo = ComanRepository(engine)
    org = repo.create_organization("ERP QA")
    facility = repo.create_facility(org.id, "Main", "MAIN")
    return repo, org, facility

def test_bom_lot_ledger_and_reservation_flow():
    repo, org, facility = setup_repo()
    flower = repo.create_product(org.id, sku="BULK-1", name="Bulk Flower", item_type="cannabis", base_unit="g", unit_cost=1.5, actor="dev")
    pouch = repo.create_product(org.id, sku="POUCH-35", name="3.5g Pouch", item_type="packaging", base_unit="unit", unit_cost=.25, actor="dev")
    finished = repo.create_product(org.id, sku="FG-35", name="Flower 3.5g", item_type="finished_good", base_unit="unit", actor="dev")
    bom = repo.create_bom(org.id, output_product_id=finished.id, output_quantity=1, expected_loss_pct=3, components=[{"input_product_id": flower.id, "quantity": 3.5, "unit": "g"}, {"input_product_id": pouch.id, "quantity": 1, "unit": "unit"}], actor="dev")
    assert bom.output_product_id == finished.id
    lot = repo.create_inventory_lot(org.id, facility.id, product_id=flower.id, lot_code="QA-LOT-1", actor="dev", opening_quantity=1000, unit="g")
    assert repo.inventory_balance(org.id, lot.id) == 1000
    order = repo.create_production_order(organization_id=org.id, facility_id=facility.id, order_number="QA-ORDER-1", work_type="internal", product_name=finished.name, product_format="pouched flower", requested_units=100, actor="dev")
    reservation = repo.reserve_material(org.id, facility.id, production_order_id=order.id, lot_id=lot.id, quantity=350, unit="g", actor="dev")
    assert reservation.quantity == 350
    repo.post_inventory_transaction(org.id, facility.id, lot_id=lot.id, transaction_type="production_consume", quantity_delta=-350, unit="g", actor="dev", production_order_id=order.id)
    assert repo.inventory_balance(org.id, lot.id) == 650

def test_ledger_prevents_negative_inventory_and_over_reservation():
    repo, org, facility = setup_repo()
    flower = repo.create_product(org.id, sku="BULK-2", name="Bulk Flower", item_type="cannabis", base_unit="g", actor="dev")
    lot = repo.create_inventory_lot(org.id, facility.id, product_id=flower.id, lot_code="QA-LOT-2", actor="dev", opening_quantity=100, unit="g")
    order = repo.create_production_order(organization_id=org.id, facility_id=facility.id, order_number="QA-ORDER-2", work_type="internal", product_name="Test", product_format="pouched flower", requested_units=1, actor="dev")
    try: repo.reserve_material(org.id, facility.id, production_order_id=order.id, lot_id=lot.id, quantity=101, unit="g", actor="dev")
    except ValueError as exc: assert "exceeds" in str(exc)
    else: raise AssertionError("over-reservation must fail")
    try: repo.post_inventory_transaction(org.id, facility.id, lot_id=lot.id, transaction_type="waste", quantity_delta=-101, unit="g", actor="dev")
    except ValueError as exc: assert "negative" in str(exc)
    else: raise AssertionError("negative inventory must fail")


def test_listing_lots_prefetches_balances_without_per_lot_queries():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    repo = ComanRepository(engine)
    org = repo.create_organization("Balance Batch QA")
    facility = repo.create_facility(org.id, "Main", "MAIN")
    product = repo.create_product(org.id, sku="BAL-1", name="Balance Test", item_type="cannabis", base_unit="g", actor="dev")
    expected = {}
    for index, quantity in enumerate((100.0, 250.0, 0.0), start=1):
        lot = repo.create_inventory_lot(org.id, facility.id, product_id=product.id, lot_code=f"BAL-{index}", actor="dev", opening_quantity=quantity, unit="g")
        expected[lot.id] = quantity

    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def count_queries(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    lots = repo.list_inventory_lots(org.id, facility.id)
    queries_after_listing = len(statements)
    balances = {lot.id: repo.inventory_balance(org.id, lot.id) for lot in lots}

    assert balances == expected
    assert len(statements) == queries_after_listing
    assert queries_after_listing == 1


def test_prefetched_balance_is_one_shot_and_cannot_hide_external_ledger_writes():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    reader = ComanRepository(engine)
    writer = ComanRepository(engine)
    org = reader.create_organization("Balance Freshness QA")
    facility = reader.create_facility(org.id, "Main", "MAIN")
    product = reader.create_product(org.id, sku="BAL-FRESH", name="Fresh Balance", item_type="cannabis", base_unit="g", actor="dev")
    lot = reader.create_inventory_lot(org.id, facility.id, product_id=product.id, lot_code="BAL-FRESH-1", actor="dev", opening_quantity=100, unit="g")

    reader.list_inventory_lots(org.id, facility.id)
    assert reader.inventory_balance(org.id, lot.id) == 100

    writer.post_inventory_transaction(org.id, facility.id, lot_id=lot.id, transaction_type="waste", quantity_delta=-10, unit="g", actor="dev")

    assert reader.inventory_balance(org.id, lot.id) == 90
