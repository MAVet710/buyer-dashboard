from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.auth import RequestContext
from backend.app.routers.enterprise_control import enterprise_control_tower
from backend.app.routers.package_360 import _snapshot, package_360
from backend.app.routers.traceability_actions import TraceabilityIntent, queue_action
from backend.app.routers.warehouse import PickAction, pick_action, pick_queue
from modules.coman.models import Base, InventoryLot
from modules.coman.repository import ComanRepository
from modules.commercial.repository import CommercialRepository
from modules.production_erp.service import ProductionERPService


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    organization = coman.create_organization("Beat Distru QA")
    facility = coman.create_facility(organization.id, "Main", "MAIN")
    context = RequestContext(user_id="dev-user", organization_id=organization.id, facility_id=facility.id, role="dev")
    return engine, coman, organization, facility, context


def test_package_360_builds_facility_scoped_timeline_and_rejects_cross_tenant_access():
    engine, coman, organization, facility, context = _setup()
    product = coman.create_product(organization.id, sku="PKG-1", name="Package Product", item_type="finished_good", base_unit="unit", unit_cost=5, actor="dev")
    lot = coman.create_inventory_lot(organization.id, facility.id, product_id=product.id, lot_code="LOT-360", compliance_package_id="1A4000000000000000000001", barcode_value="BC-360", opening_quantity=12, unit="unit", actor="dev")

    result = _snapshot(lot, context, engine)
    assert result["package"]["balance"] == 12
    assert result["product"]["name"] == "Package Product"
    assert any(row["event_type"] == "receipt" for row in result["timeline"])

    other = coman.create_organization("Hidden Tenant")
    other_facility = coman.create_facility(other.id, "Hidden", "HIDDEN")
    other_context = RequestContext(user_id="dev-user", organization_id=other.id, facility_id=other_facility.id, role="dev")
    with pytest.raises(HTTPException) as exc:
        package_360(lot.id, other_context, engine)
    assert exc.value.status_code == 404


def test_mobile_pick_queue_prefers_earliest_expiration_and_wrong_scan_cannot_mutate_inventory():
    engine, coman, organization, facility, context = _setup()
    product = coman.create_product(organization.id, sku="FG-1", name="Finished Good", item_type="finished_good", base_unit="unit", unit_cost=4, actor="dev")
    later = coman.create_inventory_lot(organization.id, facility.id, product_id=product.id, lot_code="LATER", compliance_package_id="PKG-LATER", barcode_value="BAR-LATER", opening_quantity=20, unit="unit", actor="dev")
    sooner = coman.create_inventory_lot(organization.id, facility.id, product_id=product.id, lot_code="SOONER", compliance_package_id="PKG-SOONER", barcode_value="BAR-SOONER", opening_quantity=20, unit="unit", actor="dev")
    with Session(engine) as session:
        session.get(InventoryLot, later.id).expiration_at = datetime.now(timezone.utc) + timedelta(days=60)
        session.get(InventoryLot, sooner.id).expiration_at = datetime.now(timezone.utc) + timedelta(days=10)
        session.commit()

    commercial = CommercialRepository(engine)
    customer = commercial.create_trade_partner(organization.id, name="Customer", partner_type="customer", actor="dev")
    order = commercial.create_order(organization_id=organization.id, facility_id=facility.id, partner_id=customer.id, order_number="SO-PICK", order_type="sales", order_date=datetime.now(timezone.utc).date(), due_date=None, lines=[{"product_id": product.id, "quantity": 5, "unit": "unit", "unit_price": 12}], actor="dev")
    commercial.confirm_order(order.id, organization_id=organization.id, facility_id=facility.id, actor="dev")
    line = commercial.list_order_lines(organization.id, order_id=order.id)[0]

    queue = pick_queue(context, engine)
    assert queue["queue"][0]["recommended_lot"]["id"] == sooner.id
    before = coman.inventory_balance(organization.id, sooner.id)
    with pytest.raises(HTTPException) as exc:
        pick_action(PickAction(order_line_id=line.id, lot_id=sooner.id, quantity=2, scan_code="WRONG", action="reserve"), context, engine)
    assert exc.value.status_code == 422
    assert coman.inventory_balance(organization.id, sooner.id) == before

    reserved = pick_action(PickAction(order_line_id=line.id, lot_id=sooner.id, quantity=2, scan_code="PKG-SOONER", action="reserve"), context, engine)
    assert reserved["action"] == "reserved"
    shipped = pick_action(PickAction(order_line_id=line.id, lot_id=sooner.id, quantity=2, scan_code="BAR-SOONER", action="ship", reference="SO-PICK"), context, engine)
    assert shipped["quantity_delta"] == -2
    assert coman.inventory_balance(organization.id, sooner.id) == before - 2


def test_enterprise_control_tower_rolls_up_only_current_organization_facilities():
    engine, coman, organization, facility, context = _setup()
    second = coman.create_facility(organization.id, "Second", "SECOND")
    hidden_org = coman.create_organization("Hidden Org")
    coman.create_facility(hidden_org.id, "Hidden Facility", "HIDDEN")

    result = enterprise_control_tower(context, engine)
    assert result["facility_count"] == 2
    assert {row["facility"]["id"] for row in result["facilities"]} == {facility.id, second.id}
    assert all(row["facility"]["name"] != "Hidden Facility" for row in result["facilities"])


def test_typed_traceability_intents_validate_required_fields_and_are_idempotent():
    engine, _coman, organization, facility, context = _setup()
    missing = TraceabilityIntent(provider="metrc", operation_type="package_adjust", entity_id="PKG-1", payload={"quantity_delta": -1}, reason="Cycle count correction", idempotency_key="adjust-1")
    with pytest.raises(HTTPException) as exc:
        queue_action(missing, context, engine)
    assert exc.value.status_code == 422

    payload = TraceabilityIntent(provider="metrc", operation_type="package_adjust", entity_id="PKG-1", payload={"quantity_delta": -1, "unit": "g", "reason": "Cycle count"}, reason="Approved cycle-count correction", idempotency_key="adjust-1")
    first = queue_action(payload, context, engine)
    second = queue_action(payload, context, engine)
    assert first["id"] == second["id"]
    assert first["status"] == "queued"
    assert first["provider_execution"] == "queued_not_assumed_successful"


def test_production_run_360_material_output_qa_and_cost_flow_stays_on_canonical_ledgers():
    engine, coman, organization, facility, context = _setup()
    material = coman.create_product(organization.id, sku="MAT", name="Bulk Material", item_type="cannabis", base_unit="g", unit_cost=1, actor="dev")
    finished = coman.create_product(organization.id, sku="FG", name="Finished Unit", item_type="finished_good", base_unit="unit", unit_cost=0, actor="dev")
    source = coman.create_inventory_lot(organization.id, facility.id, product_id=material.id, lot_code="SRC", opening_quantity=100, unit="g", actor="dev")
    coman.create_bom(organization.id, output_product_id=finished.id, output_quantity=10, expected_loss_pct=0, components=[{"input_product_id": material.id, "quantity": 10, "unit": "g"}], actor="dev")
    order = coman.create_production_order(organization_id=organization.id, facility_id=facility.id, order_number="RUN-360", work_type="internal", product_name=finished.name, product_format="Other", requested_units=10, sku=finished.sku, actor="dev")
    service = ProductionERPService(engine)

    reserve = service.reserve_bom_materials(organization_id=organization.id, facility_id=facility.id, order_id=order.id, actor=context.user_id)
    assert reserve["shortages"] == []
    assert reserve["reserved"] == 1
    output = service.add_output(organization_id=organization.id, facility_id=facility.id, order_id=order.id, product_id=finished.id, planned_quantity=10, actor=context.user_id, unit="unit")
    output = service.record_output_actual(organization_id=organization.id, facility_id=facility.id, output_id=output.id, actual_quantity=9, lot_code="FG-RUN-360", actor=context.user_id)
    assert output.status == "quarantine"
    service.add_cost(organization_id=organization.id, facility_id=facility.id, order_id=order.id, category="labor", amount_usd=18, actor=context.user_id)
    service.record_qa(organization_id=organization.id, facility_id=facility.id, order_id=order.id, event_type="release", result="passed", output_id=output.id, actor=context.user_id)

    snapshot = service.order_360(organization.id, facility.id, order.id)
    assert snapshot["actual_output"] == 9
    assert snapshot["attainment_pct"] == 90
    assert snapshot["cogs"]["total"] == 18
    with Session(engine) as session:
        finished_lot = session.get(InventoryLot, output.lot_id)
        assert finished_lot.status == "available"
    assert coman.inventory_balance(organization.id, source.id) == 100
