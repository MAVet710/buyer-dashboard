from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Base, Facility, InventoryLot, InventoryTransaction, Organization, Product
from modules.product_master.models import ProductMasterProfile
from modules.traceability.object_links import TraceabilityObjectLink
from services.metrc_workspace_hydration import MetrcWorkspaceHydrationService


def _item() -> dict:
    return {
        "provider": "metrc",
        "resource": "items",
        "provider_id": "501",
        "name": "GMO Flower",
        "unit": "Grams",
        "source": {
            "Id": 501,
            "Name": "GMO Flower",
            "ProductCategoryName": "Buds",
            "UnitOfMeasureName": "Grams",
        },
    }


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


def test_same_numeric_metrc_item_id_across_three_licenses_stays_exact_and_visible_without_sku_collision():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    facilities = [
        ("fac-cult", "MC281001", "Cultivation"),
        ("fac-mfg", "MP281002", "Manufacturing"),
        ("fac-retail", "MR281003", "Retail"),
    ]
    with Session(engine) as session, session.begin():
        session.add(Organization(id="org-multi-item", name="Multi Item Operator", slug="multi-item-operator"))
        for facility_id, license_number, name in facilities:
            session.add(Facility(
                id=facility_id,
                organization_id="org-multi-item",
                name=name,
                code=facility_id.upper(),
                license_number=license_number,
                license_type=name,
                active=True,
            ))

    hydrator = MetrcWorkspaceHydrationService(engine)
    packages = [
        _package("9001", "1A4FF0100000000000009001", 100),
        _package("9002", "1A4FF0100000000000009002", 200),
        _package("9003", "1A4FF0100000000000009003", 300),
    ]

    first = hydrator.hydrate(
        organization_id="org-multi-item",
        facility_id="fac-cult",
        state="MA",
        environment="sandbox",
        license_number="MC281001",
        actor="admin",
        resource_snapshots={"items": [_item()], "packages": [packages[0]]},
    )
    assert first["workspaces"]["product_master"]["created_products"] == 1
    assert first["workspaces"]["product_master"]["identity_scope"] == "facility_license"
    assert first["workspaces"]["inventory"]["created_inventory_lots"] == 1

    # These two licenses intentionally receive only changed Package rows. Exact
    # embedded Item identity must be materialized for each same-license scope before
    # Inventory hydration. Numeric Item IDs are not assumed globally unique across
    # licenses, and license-scoped Product SKUs prevent organization-wide collision.
    second = hydrator.hydrate(
        organization_id="org-multi-item",
        facility_id="fac-mfg",
        state="MA",
        environment="sandbox",
        license_number="MP281002",
        actor="admin",
        resource_snapshots={"packages": [packages[1]]},
    )
    third = hydrator.hydrate(
        organization_id="org-multi-item",
        facility_id="fac-retail",
        state="MA",
        environment="sandbox",
        license_number="MR281003",
        actor="admin",
        resource_snapshots={"packages": [packages[2]]},
    )

    assert second["workspaces"]["product_master"]["created_products"] == 1
    assert second["workspaces"]["product_master"]["embedded_package_item_evidence_count"] == 1
    assert second["workspaces"]["inventory"]["created_inventory_lots"] == 1
    assert third["workspaces"]["product_master"]["created_products"] == 1
    assert third["workspaces"]["product_master"]["embedded_package_item_evidence_count"] == 1
    assert third["workspaces"]["inventory"]["created_inventory_lots"] == 1

    with Session(engine) as session:
        products = list(session.scalars(select(Product).where(Product.organization_id == "org-multi-item")))
        profiles = list(session.scalars(select(ProductMasterProfile).where(ProductMasterProfile.organization_id == "org-multi-item")))
        lots = list(session.scalars(select(InventoryLot).where(InventoryLot.organization_id == "org-multi-item")))
        transactions = list(session.scalars(select(InventoryTransaction).where(InventoryTransaction.organization_id == "org-multi-item")))
        item_links = list(session.scalars(select(TraceabilityObjectLink).where(
            TraceabilityObjectLink.organization_id == "org-multi-item",
            TraceabilityObjectLink.provider == "metrc",
            TraceabilityObjectLink.environment == "sandbox",
            TraceabilityObjectLink.provider_resource == "items",
            TraceabilityObjectLink.provider_id == "501",
        )))
        package_links = list(session.scalars(select(TraceabilityObjectLink).where(
            TraceabilityObjectLink.organization_id == "org-multi-item",
            TraceabilityObjectLink.provider == "metrc",
            TraceabilityObjectLink.environment == "sandbox",
            TraceabilityObjectLink.provider_resource == "packages",
        )))

    assert len(products) == 3
    assert {product.name for product in products} == {"GMO Flower"}
    assert {product.sku for product in products} == {
        "METRC-MA-MC281001-501",
        "METRC-MA-MP281002-501",
        "METRC-MA-MR281003-501",
    }
    assert len(profiles) == 3
    assert len(lots) == 3
    assert {lot.facility_id for lot in lots} == {"fac-cult", "fac-mfg", "fac-retail"}
    assert {lot.product_id for lot in lots} == {product.id for product in products}
    assert len(transactions) == 3
    assert sorted(transaction.quantity_delta for transaction in transactions) == [100.0, 200.0, 300.0]

    assert len(item_links) == 3
    assert {link.facility_id for link in item_links} == {"fac-cult", "fac-mfg", "fac-retail"}
    assert {link.license_number for link in item_links} == {"MC281001", "MP281002", "MR281003"}
    assert {link.entity_id for link in item_links} == {product.id for product in products}
    assert len(package_links) == 3

    replay = hydrator.hydrate(
        organization_id="org-multi-item",
        facility_id="fac-retail",
        state="MA",
        environment="sandbox",
        license_number="MR281003",
        actor="admin",
        resource_snapshots={"packages": [packages[2]]},
    )
    assert replay["workspaces"]["product_master"]["created_products"] == 0
    assert replay["workspaces"]["product_master"]["existing_product_count"] == 1
    assert replay["workspaces"]["inventory"]["created_inventory_lots"] == 0
    assert replay["workspaces"]["inventory"]["created_inventory_transactions"] == 0

    with Session(engine) as session:
        assert len(list(session.scalars(select(Product).where(Product.organization_id == "org-multi-item")))) == 3
        assert len(list(session.scalars(select(InventoryLot).where(InventoryLot.organization_id == "org-multi-item")))) == 3
        assert len(list(session.scalars(select(InventoryTransaction).where(InventoryTransaction.organization_id == "org-multi-item")))) == 3
