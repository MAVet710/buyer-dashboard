from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import (
    RequestContext,
    get_authorization_engine,
    require_facility_capability,
    require_inventory_operation_capability,
)
from backend.app.database import get_engine
from backend.app.main import app
from modules.coman.models import Base, Facility, Organization, Product


def cultivation_only_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-cult", name="Cultivation Operator", slug="cultivation-operator"))
        session.add(
            Facility(
                id="facility-cult",
                organization_id="org-cult",
                name="Cultivation License",
                code="CULT-01",
                license_number="MC-CULT-001",
                license_type="Marijuana Cultivator",
                retail_enabled=False,
                production_enabled=False,
                cultivation_enabled=True,
                commercial_enabled=False,
            )
        )
        session.add(
            Product(
                id="product-cult",
                organization_id="org-cult",
                sku="CULT-BULK-001",
                name="Cultivation Bulk Flower",
                item_type="cannabis",
                base_unit="g",
            )
        )
        session.commit()
    return engine


def test_cultivation_only_facility_uses_shared_production_inventory_not_manufacturing_permissions():
    engine = cultivation_only_engine()
    context = RequestContext("operator", "org-cult", "facility-cult", "operator")

    # Shared Production Ops inventory accepts either manufacturing or cultivation.
    require_inventory_operation_capability(context, engine, "production")

    # Manufacturing-specific services remain protected by the production flag.
    with pytest.raises(HTTPException) as exc:
        require_facility_capability(context, engine, "production")
    assert exc.value.status_code == 403


def test_cultivation_only_facility_can_open_inventory_catalog_audits_and_plants():
    engine = cultivation_only_engine()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_authorization_engine] = lambda: engine
    client = TestClient(app)
    headers = {
        "X-Organization-Id": "org-cult",
        "X-Facility-Id": "facility-cult",
        "X-User-Id": "operator",
        "X-User-Role": "operator",
    }
    try:
        inventory = client.get("/api/v1/inventory/production/packages", headers=headers)
        catalog = client.get("/api/v1/product-master?operation=production", headers=headers)
        audits = client.get("/api/v1/inventory/production/audits", headers=headers)
        plants = client.get("/api/v1/inventory/production/plants", headers=headers)
        retail = client.get("/api/v1/inventory/retail/packages", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert inventory.status_code == 200, inventory.text
    assert inventory.json()["operation"] == "production"
    assert catalog.status_code == 200, catalog.text
    assert any(row["id"] == "product-cult" for row in catalog.json())
    assert audits.status_code == 200, audits.text
    assert audits.json() == []
    assert plants.status_code == 200, plants.text
    assert plants.json() == []
    assert retail.status_code == 403
