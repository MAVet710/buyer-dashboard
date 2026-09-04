from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.traceability.object_links import TraceabilityObjectLink
from services import metrc_facility_bootstrap as bootstrap_module
from services.metrc_facility_bootstrap import MetrcFacilityBootstrapService
from services.metrc_facility_materialization import MetrcCanonicalInventorySeeder


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _tenant(engine):
    with Session(engine) as session, session.begin():
        organization = Organization(name="Hydration Test", slug="hydration-test", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Hydration Facility",
            code="HYD",
            license_number="LIC-HYD",
            production_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        return organization.id, facility.id


def _package(label: str, quantity: float, *, item_id: int = 41, item_name: str = "GMO Bulk Flower"):
    return {
        "provider": "metrc",
        "jurisdiction_code": "MA",
        "resource": "packages_active",
        "provider_id": label.removeprefix("PKG-"),
        "label": label,
        "name": item_name,
        "status": "TestPassed",
        "quantity": quantity,
        "unit_of_measure": "Grams",
        "source": {
            "Id": label.removeprefix("PKG-"),
            "Label": label,
            "ItemId": item_id,
            "ItemName": item_name,
            "ItemCategoryName": "Buds",
            "Quantity": quantity,
            "UnitOfMeasureName": "Grams",
            "LocationName": "Vault A",
            "LabTestingState": "TestPassed",
        },
    }


def test_metrc_materialization_seeds_new_packages_once_and_preserves_existing_balances():
    engine = _engine()
    organization_id, facility_id = _tenant(engine)
    service = MetrcCanonicalInventorySeeder(engine)
    packages = [_package("PKG-100", 100.0), _package("PKG-101", 50.0)]

    first = service.seed(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-HYD",
        actor="tester",
        packages=packages,
    )
    assert first["created_products"] == 1
    assert first["created_inventory_lots"] == 2
    assert first["created_inventory_transactions"] == 2
    assert first["created_product_links"] == 1
    assert first["created_package_links"] == 2
    assert first["conflict_count"] == 0
    assert first["overwrite_existing"] is False

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 1
        assert session.scalar(select(func.count()).select_from(InventoryLot)) == 2
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 2
        assert session.scalar(select(func.count()).select_from(TraceabilityObjectLink)) == 3
        product = session.scalar(select(Product))
        assert product is not None and product.external_product_id == ""
        links = list(session.scalars(select(TraceabilityObjectLink).order_by(
            TraceabilityObjectLink.provider_resource, TraceabilityObjectLink.provider_id
        )))
        assert {(row.provider_resource, row.provider_id) for row in links} == {
            ("items", "41"), ("packages", "100"), ("packages", "101")
        }
        assert all(row.provider == "metrc" for row in links)
        assert all(row.environment == "sandbox" for row in links)
        assert all(row.license_number == "LIC-HYD" for row in links)
        balance = session.scalar(select(func.sum(InventoryTransaction.quantity_delta)))
        assert float(balance or 0) == 150.0
        lots = list(session.scalars(select(InventoryLot).order_by(InventoryLot.lot_code)))
        assert [row.compliance_package_id for row in lots] == ["PKG-100", "PKG-101"]
        assert all(row.location_code == "Vault A" for row in lots)
        assert all(row.status == "available" for row in lots)

    changed_provider_snapshot = [_package("PKG-100", 75.0), _package("PKG-101", 25.0)]
    second = service.seed(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-HYD",
        actor="tester",
        packages=changed_provider_snapshot,
    )
    assert second["created_products"] == 0
    assert second["created_inventory_lots"] == 0
    assert second["created_inventory_transactions"] == 0
    assert second["created_product_links"] == 0
    assert second["created_package_links"] == 0
    assert second["existing_package_count"] == 2

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryLot)) == 2
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 2
        assert session.scalar(select(func.count()).select_from(TraceabilityObjectLink)) == 3
        balance = session.scalar(select(func.sum(InventoryTransaction.quantity_delta)))
        assert float(balance or 0) == 150.0


def test_existing_exact_package_label_gets_identity_links_without_balance_mutation():
    engine = _engine()
    organization_id, facility_id = _tenant(engine)
    with Session(engine) as session, session.begin():
        product = Product(
            organization_id=organization_id,
            sku="LOCAL-GMO",
            name="GMO Bulk Flower",
            item_type="cannabis",
            base_unit="Grams",
            active=True,
        )
        session.add(product)
        session.flush()
        lot = InventoryLot(
            organization_id=organization_id,
            facility_id=facility_id,
            product_id=product.id,
            lot_code="LOCAL-300",
            compliance_package_id="PKG-300",
            location_code="LOCAL",
            status="available",
        )
        session.add(lot)
        session.flush()
        session.add(InventoryTransaction(
            organization_id=organization_id,
            facility_id=facility_id,
            lot_id=lot.id,
            transaction_type="receive",
            quantity_delta=30.0,
            unit="Grams",
            reason="Existing local package",
            reference="PKG-300",
            actor="tester",
        ))

    result = MetrcCanonicalInventorySeeder(engine).seed(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-HYD",
        actor="tester",
        packages=[_package("PKG-300", 25.0)],
    )
    assert result["created_products"] == 0
    assert result["created_inventory_lots"] == 0
    assert result["created_inventory_transactions"] == 0
    assert result["created_product_links"] == 1
    assert result["created_package_links"] == 1
    assert result["existing_package_count"] == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(TraceabilityObjectLink)) == 2
        balance = session.scalar(select(func.sum(InventoryTransaction.quantity_delta)))
        assert float(balance or 0) == 30.0


def test_metrc_materialization_fails_closed_on_local_lot_code_collision():
    engine = _engine()
    organization_id, facility_id = _tenant(engine)
    with Session(engine) as session, session.begin():
        product = Product(
            organization_id=organization_id,
            sku="LOCAL-GMO",
            name="Local GMO",
            item_type="cannabis",
            base_unit="Grams",
            active=True,
        )
        session.add(product)
        session.flush()
        session.add(InventoryLot(
            organization_id=organization_id,
            facility_id=facility_id,
            product_id=product.id,
            lot_code="PKG-200",
            compliance_package_id="",
            location_code="LOCAL",
            status="available",
        ))

    result = MetrcCanonicalInventorySeeder(engine).seed(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-HYD",
        actor="tester",
        packages=[_package("PKG-200", 20.0)],
    )
    assert result["created_inventory_lots"] == 0
    assert result["conflict_count"] == 1
    assert result["conflicts"][0]["code"] == "lot_code_collision"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryLot)) == 1
        assert session.scalar(select(func.count()).select_from(InventoryTransaction)) == 0
        assert session.scalar(select(func.count()).select_from(TraceabilityObjectLink)) == 0


def test_normalized_initial_hydration_walks_every_provider_page(monkeypatch):
    engine = _engine()
    calls = []

    def fake_fetch(**kwargs):
        page = kwargs["page_number"]
        calls.append(page)
        return {
            "ok": True,
            "http_status": 200,
            "resource": kwargs["resource"],
            "payload": {"Data": [{"Id": page}], "TotalPages": 3},
            "records": [{"provider_id": str(page), "source": {"Id": page}}],
        }

    monkeypatch.setattr(bootstrap_module, "fetch_metrc_resource", fake_fetch)
    result = MetrcFacilityBootstrapService(engine)._fetch_all_normalized(
        resource="packages_active",
        state="MA",
        user_api_key="user",
        integrator_api_key="vendor",
        license_number="LIC-HYD",
        environment="sandbox",
    )
    assert calls == [1, 2, 3]
    assert result["page_count"] == 3
    assert result["truncated"] is False
    assert [row["provider_id"] for row in result["records"]] == ["1", "2", "3"]


def test_direct_initial_hydration_walks_every_provider_page():
    class Transport:
        def __init__(self):
            self.calls = []

        def get(self, path, params):
            self.calls.append((path, dict(params)))
            page = int(params["pageNumber"])
            return {
                "ok": True,
                "http_status": 200,
                "payload": {"Data": [{"Id": page}], "TotalPages": 2},
            }

    transport = Transport()
    result = MetrcFacilityBootstrapService._fetch_all_direct(
        transport=transport,
        path="items/v2/categories",
        params={"licenseNumber": "LIC-HYD"},
        paginated=True,
    )
    assert [call[1]["pageNumber"] for call in transport.calls] == [1, 2]
    assert result["page_count"] == 2
    assert result["truncated"] is False
    assert [row["Id"] for row in result["records"]] == [1, 2]
