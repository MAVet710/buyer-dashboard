from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, InventoryLot, Organization, Product
from modules.traceability.object_links import TraceabilityObjectLink
from services.metrc_facility_materialization import MetrcCanonicalInventorySeeder


def _package(provider_id: str, label: str, quantity: float) -> dict:
    return {
        "provider": "metrc",
        "resource": "packages",
        "provider_id": provider_id,
        "label": label,
        "quantity": quantity,
        "unit_of_measure": "Grams",
        "source": {
            "Id": int(provider_id),
            "Label": label,
            "Quantity": quantity,
            "UnitOfMeasureName": "Grams",
            "LabTestingState": "TestPassed",
            "LocationName": "Vault",
            "Item": {
                "Id": 501,
                "Name": "GMO Flower",
                "ProductCategoryName": "Buds",
                "UnitOfMeasureName": "Grams",
            },
        },
    }


def test_direct_inventory_seeder_scopes_fallback_product_sku_by_license():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-direct-multi", name="Direct Multi", slug="direct-multi"))
        session.add(Facility(
            id="fac-cult",
            organization_id="org-direct-multi",
            name="Cultivation",
            code="CULT",
            license_number="MC281001",
            license_type="Cultivation",
            active=True,
        ))
        session.add(Facility(
            id="fac-mfg",
            organization_id="org-direct-multi",
            name="Manufacturing",
            code="MFG",
            license_number="MP281002",
            license_type="Manufacturing",
            active=True,
        ))

    seeder = MetrcCanonicalInventorySeeder(engine)
    first = seeder.seed(
        organization_id="org-direct-multi",
        facility_id="fac-cult",
        state="MA",
        environment="sandbox",
        license_number="MC281001",
        actor="admin",
        packages=[_package("9001", "1A4FF0100000000000009001", 100)],
    )
    second = seeder.seed(
        organization_id="org-direct-multi",
        facility_id="fac-mfg",
        state="MA",
        environment="sandbox",
        license_number="MP281002",
        actor="admin",
        packages=[_package("9002", "1A4FF0100000000000009002", 200)],
    )

    assert first["created_products"] == 1
    assert first["created_inventory_lots"] == 1
    assert first["conflict_count"] == 0
    assert second["created_products"] == 1
    assert second["created_inventory_lots"] == 1
    assert second["conflict_count"] == 0

    with Session(engine) as session:
        products = list(session.scalars(select(Product).where(Product.organization_id == "org-direct-multi")))
        lots = list(session.scalars(select(InventoryLot).where(InventoryLot.organization_id == "org-direct-multi")))
        item_links = list(session.scalars(select(TraceabilityObjectLink).where(
            TraceabilityObjectLink.organization_id == "org-direct-multi",
            TraceabilityObjectLink.provider == "metrc",
            TraceabilityObjectLink.provider_resource == "items",
            TraceabilityObjectLink.provider_id == "501",
        )))

    assert {product.sku for product in products} == {
        "METRC-MA-MC281001-501",
        "METRC-MA-MP281002-501",
    }
    assert len(lots) == 2
    assert {lot.facility_id for lot in lots} == {"fac-cult", "fac-mfg"}
    assert len(item_links) == 2
    assert {link.license_number for link in item_links} == {"MC281001", "MP281002"}
    assert {link.entity_id for link in item_links} == {product.id for product in products}
