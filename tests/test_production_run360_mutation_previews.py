from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import (
    Base,
    BomComponent,
    Facility,
    InventoryLot,
    InventoryTransaction,
    Organization,
    Product,
    ProductBom,
    ProductionOrder,
)
from modules.production_erp.models import ProductionBomStandard, ProductionRunOutput
from modules.production_erp.mutations import ProductionMutationService


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
        organization = Organization(name="Run 360 Preview QA", slug="run360-preview-qa")
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Production One",
            code="PROD-1",
            production_enabled=True,
            retail_enabled=False,
        )
        material = Product(
            organization_id=organization.id,
            sku="BULK-1",
            name="Bulk Flower",
            item_type="cannabis",
            base_unit="g",
        )
        finished = Product(
            organization_id=organization.id,
            sku="FG-1",
            name="Finished Pouch",
            item_type="finished_good",
            base_unit="each",
        )
        session.add_all([facility, material, finished])
        session.flush()
        bom = ProductBom(
            organization_id=organization.id,
            output_product_id=finished.id,
            version=1,
            output_quantity=100,
            expected_loss_pct=2,
            active=True,
        )
        session.add(bom)
        session.flush()
        session.add(
            BomComponent(
                organization_id=organization.id,
                bom_id=bom.id,
                input_product_id=material.id,
                quantity=2,
                unit="g",
                scrap_pct=0,
            )
        )
        session.add(
            ProductionBomStandard(
                organization_id=organization.id,
                bom_id=bom.id,
                standard_labor_hours=2,
                standard_machine_hours=1,
                standard_cycle_hours=4,
                resource_category="Packaging",
                qa_required=True,
                compliance_checkpoint="COA required",
                created_by="seed",
                updated_by="seed",
            )
        )
        lot = InventoryLot(
            organization_id=organization.id,
            facility_id=facility.id,
            product_id=material.id,
            lot_code="BULK-LOT-1",
            location_code="VAULT",
            status="available",
        )
        order = ProductionOrder(
            organization_id=organization.id,
            facility_id=facility.id,
            order_number="RUN-1",
            work_type="internal",
            product_name=finished.name,
            sku=finished.sku,
            product_format="pouch",
            requested_units=100,
            priority="normal",
            status="in_progress",
            created_by="seed",
            updated_by="seed",
        )
        session.add_all([lot, order])
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=organization.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="receipt",
                quantity_delta=500,
                unit="g",
                production_order_id=None,
                commercial_order_id=None,
                commercial_order_line_id=None,
                reason="Seed inventory",
                reference="seed",
                actor="seed",
            )
        )
        output = ProductionRunOutput(
            organization_id=organization.id,
            facility_id=facility.id,
            production_order_id=order.id,
            product_id=finished.id,
            position=1,
            label="Finished Pouch",
            planned_quantity=100,
            actual_quantity=0,
            unit="each",
            status="planned",
            created_by="seed",
        )
        session.add(output)
        session.commit()
        return engine, organization.id, facility.id, order.id, lot.id, output.id


def _preview(service, organization_id, facility_id, order_id, action_type, payload):
    return service.preview(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type=action_type,
        payload=payload,
    )


def _commit(service, organization_id, facility_id, order_id, action_type, payload, preview):
    return service.commit(
        organization_id=organization_id,
        facility_id=facility_id,
        order_id=order_id,
        action_type=action_type,
        payload=payload,
        preview_key=preview["preview_key"],
        actor="operator-1",
    )


def test_material_preview_reserves_only_uncovered_requirement_once():
    engine, organization_id, facility_id, order_id, _, _ = _fixture()
    service = ProductionMutationService(engine)

    first = _preview(service, organization_id, facility_id, order_id, "reserve_materials", {})
    assert first["blocker_count"] == 0
    assert first["details"]["allocations"] == [
        {
            "product_id": first["details"]["allocations"][0]["product_id"],
            "product": "Bulk Flower",
            "lot_id": first["details"]["allocations"][0]["lot_id"],
            "lot_code": "BULK-LOT-1",
            "quantity": 200.0,
            "unit": "g",
            "available_before": 500.0,
        }
    ]
    _commit(service, organization_id, facility_id, order_id, "reserve_materials", {}, first)

    second = _preview(service, organization_id, facility_id, order_id, "reserve_materials", {})
    assert second["details"]["allocations"] == []
    assert second["details"]["shortages"] == []
    with Session(engine) as session:
        reserved = session.scalar(
            select(func.coalesce(func.sum(__import__("modules.coman.models", fromlist=["MaterialReservation"]).MaterialReservation.quantity), 0.0)).where(
                __import__("modules.coman.models", fromlist=["MaterialReservation"]).MaterialReservation.production_order_id == order_id,
                __import__("modules.coman.models", fromlist=["MaterialReservation"]).MaterialReservation.status == "reserved",
            )
        )
        assert float(reserved or 0) == 200.0


def test_stale_material_preview_is_rejected_after_inventory_changes():
    engine, organization_id, facility_id, order_id, lot_id, _ = _fixture()
    service = ProductionMutationService(engine)
    preview = _preview(service, organization_id, facility_id, order_id, "reserve_materials", {})

    with Session(engine) as session:
        session.add(
            InventoryTransaction(
                organization_id=organization_id,
                facility_id=facility_id,
                lot_id=lot_id,
                transaction_type="adjustment_out",
                quantity_delta=-25,
                unit="g",
                production_order_id=None,
                commercial_order_id=None,
                commercial_order_line_id=None,
                reason="Concurrent inventory change",
                reference="concurrent",
                actor="other-user",
            )
        )
        session.commit()

    with pytest.raises(ValueError, match="stale"):
        _commit(service, organization_id, facility_id, order_id, "reserve_materials", {}, preview)


def test_output_actual_keeps_inventory_ledger_in_sync_and_requarantines_after_release():
    engine, organization_id, facility_id, order_id, _, output_id = _fixture()
    service = ProductionMutationService(engine)

    first_payload = {"output_id": output_id, "actual_quantity": 80, "lot_code": "FG-LOT-1"}
    first = _preview(service, organization_id, facility_id, order_id, "record_output_actual", first_payload)
    assert first["details"]["inventory_delta"] == 80
    _commit(service, organization_id, facility_id, order_id, "record_output_actual", first_payload, first)

    qa_payload = {
        "event_type": "release",
        "result": "passed",
        "output_id": output_id,
        "document_reference": "COA-1",
        "notes": "QA passed",
    }
    qa_preview = _preview(service, organization_id, facility_id, order_id, "qa_decision", qa_payload)
    _commit(service, organization_id, facility_id, order_id, "qa_decision", qa_payload, qa_preview)

    change_payload = {"output_id": output_id, "actual_quantity": 75, "lot_code": ""}
    change = _preview(service, organization_id, facility_id, order_id, "record_output_actual", change_payload)
    assert change["details"]["inventory_delta"] == -5
    assert any("return it to QA quarantine" in row["message"] for row in change["warnings"])
    _commit(service, organization_id, facility_id, order_id, "record_output_actual", change_payload, change)

    with Session(engine) as session:
        output = session.get(ProductionRunOutput, output_id)
        lot = session.get(InventoryLot, output.lot_id)
        balance = session.scalar(
            select(func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).where(
                InventoryTransaction.lot_id == lot.id
            )
        )
        assert output.actual_quantity == 75
        assert output.status == "quarantine"
        assert lot.status == "quarantine"
        assert lot.location_code == "QA-HOLD"
        assert float(balance or 0) == 75.0


def test_output_preview_blocks_reduction_below_downstream_inventory_use():
    engine, organization_id, facility_id, order_id, _, output_id = _fixture()
    service = ProductionMutationService(engine)
    first_payload = {"output_id": output_id, "actual_quantity": 80, "lot_code": "FG-LOT-2"}
    first = _preview(service, organization_id, facility_id, order_id, "record_output_actual", first_payload)
    _commit(service, organization_id, facility_id, order_id, "record_output_actual", first_payload, first)

    with Session(engine) as session:
        output = session.get(ProductionRunOutput, output_id)
        session.add(
            InventoryTransaction(
                organization_id=organization_id,
                facility_id=facility_id,
                lot_id=output.lot_id,
                transaction_type="consumption",
                quantity_delta=-70,
                unit="each",
                production_order_id=order_id,
                commercial_order_id=None,
                commercial_order_line_id=None,
                reason="Downstream use",
                reference="downstream",
                actor="operator-2",
            )
        )
        session.commit()

    reduction = _preview(
        service,
        organization_id,
        facility_id,
        order_id,
        "record_output_actual",
        {"output_id": output_id, "actual_quantity": 5, "lot_code": ""},
    )
    assert reduction["blocker_count"] == 1
    with pytest.raises(ValueError, match="blockers"):
        _commit(
            service,
            organization_id,
            facility_id,
            order_id,
            "record_output_actual",
            {"output_id": output_id, "actual_quantity": 5, "lot_code": ""},
            reduction,
        )


def test_cost_preview_shows_before_after_cogs_and_becomes_stale_when_costs_change():
    engine, organization_id, facility_id, order_id, _, _ = _fixture()
    service = ProductionMutationService(engine)
    payload = {"category": "labor", "amount_usd": 50, "quantity": 2, "unit": "hr", "source_type": "manual", "source_id": "", "notes": "Crew"}
    preview = _preview(service, organization_id, facility_id, order_id, "cost_event", payload)
    assert preview["details"]["cogs_before"] == 0
    assert preview["details"]["cogs_after"] == 50
    _commit(service, organization_id, facility_id, order_id, "cost_event", payload, preview)
    next_preview = _preview(service, organization_id, facility_id, order_id, "cost_event", payload)
    assert next_preview["details"]["cogs_before"] == 50
    assert next_preview["details"]["cogs_after"] == 100


def test_run360_frontend_uses_canonical_vocab_and_preview_before_high_impact_mutations():
    frontend = (ROOT / "frontend" / "src" / "pages" / "ProductionRun360Page.tsx").read_text(encoding="utf-8")
    router = (ROOT / "backend" / "app" / "routers" / "production_mutations.py").read_text(encoding="utf-8")
    service = (ROOT / "modules" / "production_erp" / "mutations.py").read_text(encoding="utf-8")

    assert 'new Set(["hold","release","completed","waste","rework"])' in frontend
    assert '["started","measurement","note","hold","release","completed","waste","rework"]' in frontend
    assert '["hold","sample","pass","fail","release","retest","deviation","remediation"]' in frontend
    assert '["material","packaging","labor","machine","overhead","waste","other"]' in frontend
    assert "EXACT CHANGE PREVIEW" in frontend
    assert "Apply exact change" in frontend
    assert "/mutations/preview" in frontend
    assert "/mutations/commit" in frontend
    assert '@router.post("/orders/{order_id}/mutations/preview")' in router
    assert '@router.post("/orders/{order_id}/mutations/commit")' in router
    assert "with_for_update()" in service
    assert "This change preview is stale" in service
    assert 'transaction_type = "production_output_adjustment"' in service
    assert "No purchase order will be created automatically" in service
