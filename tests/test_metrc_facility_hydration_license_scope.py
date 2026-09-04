from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from modules.coman.models import Base, Facility, InventoryLot, Organization, Product
from modules.traceability.object_links import TraceabilityObjectLink
from services.metrc_facility_materialization import MetrcCanonicalInventorySeeder


def test_hydration_does_not_reuse_item_identity_from_different_license():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        organization = Organization(name="License Scope", slug="license-scope", active=True)
        session.add(organization)
        session.flush()
        facility = Facility(
            organization_id=organization.id,
            name="Mapped Facility",
            code="MAP",
            license_number="LIC-CURRENT",
            production_enabled=True,
            active=True,
        )
        session.add(facility)
        session.flush()
        product = Product(
            organization_id=organization.id,
            sku="OLD-LICENSE-PRODUCT",
            name="Old GMO",
            item_type="cannabis",
            base_unit="Grams",
            active=True,
        )
        session.add(product)
        session.flush()
        session.add(TraceabilityObjectLink(
            organization_id=organization.id,
            facility_id=facility.id,
            provider="metrc",
            jurisdiction="MA",
            environment="sandbox",
            license_number="LIC-OLD",
            entity_type="product",
            entity_id=product.id,
            provider_resource="items",
            provider_id="41",
            provider_label="Old GMO",
            status="verified",
        ))
        organization_id = organization.id
        facility_id = facility.id

    result = MetrcCanonicalInventorySeeder(engine).seed(
        organization_id=organization_id,
        facility_id=facility_id,
        state="MA",
        environment="sandbox",
        license_number="LIC-CURRENT",
        actor="tester",
        packages=[{
            "provider": "metrc",
            "provider_id": "900",
            "label": "PKG-900",
            "name": "GMO Bulk Flower",
            "status": "TestPassed",
            "quantity": 20.0,
            "unit_of_measure": "Grams",
            "source": {
                "Id": "900",
                "Label": "PKG-900",
                "ItemId": 41,
                "ItemName": "GMO Bulk Flower",
                "Quantity": 20.0,
                "UnitOfMeasureName": "Grams",
                "LabTestingState": "TestPassed",
            },
        }],
    )

    assert result["created_products"] == 0
    assert result["created_inventory_lots"] == 0
    assert result["conflict_count"] == 1
    assert result["conflicts"][0]["code"] == "item_link_license_mismatch"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InventoryLot)) == 0
        assert session.scalar(select(func.count()).select_from(TraceabilityObjectLink)) == 1
