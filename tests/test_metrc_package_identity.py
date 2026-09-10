import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.services import metrc_package_identity as identity_module
from backend.app.services.metrc_package_identity import MetrcPackageIdentityError, MetrcPackageIdentityService
from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product


def engine_and_rows():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        org = Organization(name="Org", slug="org")
        session.add(org); session.flush()
        facility = Facility(organization_id=org.id, name="Production", code="PROD", production_enabled=True)
        session.add(facility); session.flush()
        product = Product(organization_id=org.id, sku="GMO-BULK", name="GMO Bulk", item_type="cannabis", base_unit="g", active=True)
        session.add(product); session.flush()
        lot = InventoryLot(organization_id=org.id, facility_id=facility.id, product_id=product.id, lot_code="LOT-1", compliance_package_id="", location_code="FG", status="available")
        session.add(lot); session.flush()
        session.add(InventoryTransaction(organization_id=org.id, facility_id=facility.id, lot_id=lot.id, transaction_type="receive", quantity_delta=100, unit="g", reason="seed", actor="tester"))
        return engine, org.id, facility.id, product.id, lot.id


def test_product_and_lot_links_require_fresh_exact_provider_identity(monkeypatch):
    engine, org_id, facility_id, product_id, lot_id = engine_and_rows()

    def fake_fetch(*, resource, path_parameters, **kwargs):
        provider_id = str(path_parameters["id"])
        if resource == "items_by_id":
            return {"ok": True, "records": [{"provider_id": provider_id, "name": "GMO Flower", "source": {"Id": int(provider_id), "Name": "GMO Flower", "IsActive": True}}]}
        return {"ok": True, "records": [{
            "provider_id": provider_id, "label": "1A4000000000000000000001", "quantity": 100,
            "unit_of_measure": "Grams", "source": {"Id": int(provider_id), "Label": "1A4000000000000000000001", "ItemName": "GMO Flower", "Quantity": 100, "UnitOfMeasureName": "Grams", "IsFinished": False},
        }]}

    monkeypatch.setattr(identity_module, "fetch_metrc_resource", fake_fetch)
    service = MetrcPackageIdentityService(engine)
    product_result = service.link_product(
        organization_id=org_id, facility_id=facility_id, product_id=product_id, provider_item_id="11",
        state="MA", environment="sandbox", license_number="LIC-1", integrator_api_key="i", user_api_key="u",
    )
    assert product_result["link"]["provider_id"] == "11"
    lot_result = service.link_lot(
        organization_id=org_id, facility_id=facility_id, lot_id=lot_id, provider_package_id="77",
        state="MA", environment="sandbox", license_number="LIC-1", integrator_api_key="i", user_api_key="u",
    )
    assert lot_result["link"]["provider_id"] == "77"
    assert lot_result["lot"]["compliance_package_id"] == "1A4000000000000000000001"
    with Session(engine) as session:
        assert session.get(InventoryLot, lot_id).compliance_package_id == "1A4000000000000000000001"


def test_lot_link_fails_when_provider_quantity_does_not_equal_append_only_local_balance(monkeypatch):
    engine, org_id, facility_id, product_id, lot_id = engine_and_rows()

    def fake_fetch(*, resource, path_parameters, **kwargs):
        provider_id = str(path_parameters["id"])
        if resource == "items_by_id":
            return {"ok": True, "records": [{"provider_id": provider_id, "name": "GMO Flower", "source": {"Id": int(provider_id), "Name": "GMO Flower"}}]}
        return {"ok": True, "records": [{"provider_id": provider_id, "label": "TAG", "quantity": 99, "unit_of_measure": "Grams", "source": {"Id": int(provider_id), "Label": "TAG", "ItemName": "GMO Flower", "Quantity": 99, "UnitOfMeasureName": "Grams"}}]}

    monkeypatch.setattr(identity_module, "fetch_metrc_resource", fake_fetch)
    service = MetrcPackageIdentityService(engine)
    service.link_product(organization_id=org_id, facility_id=facility_id, product_id=product_id, provider_item_id="11", state="MA", environment="sandbox", license_number="LIC-1", integrator_api_key="i", user_api_key="u")
    with pytest.raises(MetrcPackageIdentityError, match="balance does not match"):
        service.link_lot(organization_id=org_id, facility_id=facility_id, lot_id=lot_id, provider_package_id="77", state="MA", environment="sandbox", license_number="LIC-1", integrator_api_key="i", user_api_key="u")


def test_lot_link_requires_product_item_identity_first(monkeypatch):
    engine, org_id, facility_id, _product_id, lot_id = engine_and_rows()
    with pytest.raises(MetrcPackageIdentityError, match="Product to the exact Metrc Item"):
        MetrcPackageIdentityService(engine).link_lot(
            organization_id=org_id, facility_id=facility_id, lot_id=lot_id, provider_package_id="77",
            state="MA", environment="sandbox", license_number="LIC-1", integrator_api_key="i", user_api_key="u",
        )
