import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.services import metrc_package_actions as actions_module
from backend.app.services.metrc_package_operator_service import GovernedMetrcPackageActionService
from modules.coman.models import AuditEvent, Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.traceability.object_links import TraceabilityObjectLinkRepository


def _fixture():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="Org", slug="org")
        session.add(org)
        session.flush()
        facility = Facility(organization_id=org.id, name="Production", code="PROD", production_enabled=True)
        session.add(facility)
        session.flush()
        product = Product(
            organization_id=org.id,
            sku="GMO-BULK",
            name="GMO Bulk",
            item_type="cannabis",
            base_unit="g",
            active=True,
        )
        session.add(product)
        session.flush()
        lot = InventoryLot(
            organization_id=org.id,
            facility_id=facility.id,
            product_id=product.id,
            lot_code="LOT-1",
            compliance_package_id="1A4000000000000000000001",
            location_code="FG",
            status="finished",
        )
        session.add(lot)
        session.flush()
        session.add(
            InventoryTransaction(
                organization_id=org.id,
                facility_id=facility.id,
                lot_id=lot.id,
                transaction_type="receive",
                quantity_delta=100,
                unit="g",
                reason="seed",
                actor="tester",
            )
        )
        session.add(
            AuditEvent(
                organization_id=org.id,
                facility_id=facility.id,
                entity_type="inventory_lot",
                entity_id=lot.id,
                action="metrc_package_finished",
                actor="tester",
                changes_json=json.dumps({"previous_status": "available", "status": "finished"}),
            )
        )
        org_id, facility_id, product_id, lot_id = org.id, facility.id, product.id, lot.id

    links = TraceabilityObjectLinkRepository(engine)
    links.upsert_verified(
        organization_id=org_id,
        facility_id=facility_id,
        provider="metrc",
        jurisdiction="MA",
        environment="sandbox",
        license_number="LIC-1",
        entity_type="product",
        entity_id=product_id,
        provider_resource="items",
        provider_id="11",
        provider_label="GMO Flower",
    )
    links.upsert_verified(
        organization_id=org_id,
        facility_id=facility_id,
        provider="metrc",
        jurisdiction="MA",
        environment="sandbox",
        license_number="LIC-1",
        entity_type="inventory_lot",
        entity_id=lot_id,
        provider_resource="packages",
        provider_id="77",
        provider_label="1A4000000000000000000001",
    )
    return engine, org_id, facility_id, lot_id


def test_governed_unfinish_uses_real_audit_timestamp_and_restores_prior_status(monkeypatch):
    engine, org_id, facility_id, lot_id = _fixture()

    def fake_fetch(*, resource, path_parameters, **kwargs):
        assert resource == "packages_by_id"
        assert str(path_parameters["id"]) == "77"
        return {
            "ok": True,
            "records": [
                {
                    "provider_id": "77",
                    "label": "1A4000000000000000000001",
                    "quantity": 100,
                    "unit_of_measure": "Grams",
                    "source": {
                        "Id": 77,
                        "Label": "1A4000000000000000000001",
                        "ItemName": "GMO Flower",
                        "Quantity": 100,
                        "UnitOfMeasureName": "Grams",
                        "IsFinished": True,
                    },
                }
            ],
        }

    monkeypatch.setattr(actions_module, "fetch_metrc_resource", fake_fetch)
    service = GovernedMetrcPackageActionService(engine)
    prepared = service.prepare(
        organization_id=org_id,
        facility_id=facility_id,
        operation_type="package_unfinish",
        lot_id=lot_id,
        actual_date="2026-09-04",
        reason="Reopen after review",
        state="MA",
        environment="sandbox",
        license_number="LIC-1",
        integrator_api_key="integrator",
        user_api_key="user",
    )
    assert prepared["expected_provider_state"]["finished"] is False

    result = service._apply_local(
        organization_id=org_id,
        facility_id=facility_id,
        actor="tester",
        prepared=prepared,
        transaction_id="tx-test",
    )
    assert result["status"] == "available"
    with Session(engine) as session:
        assert session.get(InventoryLot, lot_id).status == "available"
        reopen = session.query(AuditEvent).filter(AuditEvent.action == "metrc_package_reopened").one()
        assert json.loads(reopen.changes_json)["source_finish_audit_id"]
