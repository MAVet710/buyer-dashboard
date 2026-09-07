from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext, get_request_context
from backend.app.database import get_engine
from backend.app.routers.supplier_portal import public_router, router
from modules.coman.models import Facility, Organization, TradePartner
from modules.operational_moats.models import PartnerPortalAccess
from modules.operational_moats.service import OperationalMoatService
from modules.supplier_portal.models import SupplierOffer, SupplierOfferLine, SupplierPortalGrant
from modules.supplier_portal.service import SupplierPortalService


def _engine():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    TradePartner.__table__.create(engine)
    PartnerPortalAccess.__table__.create(engine)
    SupplierPortalGrant.__table__.create(engine)
    SupplierOffer.__table__.create(engine)
    SupplierOfferLine.__table__.create(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-1", name="Demo", slug="demo"))
        session.add(Facility(id="fac-1", organization_id="org-1", name="Buyer", code="BUYER"))
        session.add(TradePartner(id="vendor-1", organization_id="org-1", name="Vendor One", partner_type="vendor"))
        session.add(TradePartner(id="customer-1", organization_id="org-1", name="Retailer One", partner_type="customer"))
        session.commit()
    return engine


def _client(engine, role: str = "buyer") -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(public_router, prefix="/api/v1")
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_request_context] = lambda: RequestContext(
        user_id="buyer-1",
        organization_id="org-1",
        facility_id="fac-1",
        role=role,
    )
    return TestClient(app)


def _offer_payload(price: float = 700.0):
    return {
        "external_reference": "SEPT-MENU",
        "valid_from": "2026-09-07",
        "valid_until": "2026-09-30",
        "promotion_terms": "10+ lb: 5% off",
        "lead_time_days": 3,
        "lines": [
            {
                "supplier_sku": "GMO-BULK",
                "product_name": "GMO Bulk Flower",
                "strain": "GMO",
                "form": "flower",
                "available_quantity": 12,
                "availability_unit": "lb",
                "unit_price": price,
                "price_basis": "lb",
                "minimum_order_quantity": 1,
                "minimum_order_unit": "lb",
                "batch_lot_identifier": "LOT-GMO-1",
                "coa_reference": "coa-123",
                "sample_status": "offered",
            }
        ],
    }


def test_supplier_offer_http_flow_is_staging_only_and_revision_safe():
    engine = _engine()
    token = SupplierPortalService(engine).issue_supplier_access(
        organization_id="org-1",
        facility_id="fac-1",
        partner_id="vendor-1",
        actor="buyer-1",
    )[2]
    client = _client(engine)

    submitted = client.post(f"/api/v1/commerce-portal/{token}/offers", json=_offer_payload())
    assert submitted.status_code == 201, submitted.text
    first = submitted.json()
    assert first["status"] == "submitted"
    assert first["revision"] == 1
    assert first["lines"][0]["unit_price"] == 700.0

    revised = client.post(
        f"/api/v1/commerce-portal/{token}/offers/{first['id']}/revisions",
        json=_offer_payload(675.0),
    )
    assert revised.status_code == 201, revised.text
    second = revised.json()
    assert second["revision"] == 2
    assert second["supersedes_offer_id"] == first["id"]
    assert second["lines"][0]["unit_price"] == 675.0

    history = client.get(f"/api/v1/commerce-portal/{token}/offers")
    assert history.status_code == 200
    assert {row["status"] for row in history.json()} == {"submitted", "superseded"}

    withdrawn = client.post(f"/api/v1/commerce-portal/{token}/offers/{second['id']}/withdraw")
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"

    tables = set(inspect(engine).get_table_names())
    assert "commercial_orders" not in tables
    assert "coman_inventory_transactions" not in tables


def test_buyer_can_issue_and_review_but_operator_cannot():
    engine = _engine()
    buyer = _client(engine, "buyer")
    issued = buyer.post(
        "/api/v1/supplier-portal/access",
        json={"partner_id": "vendor-1", "label": "Vendor September Portal"},
    )
    assert issued.status_code == 201, issued.text
    token = issued.json()["token"]
    assert token.startswith("dlp_")

    submitted = buyer.post(f"/api/v1/commerce-portal/{token}/offers", json=_offer_payload())
    assert submitted.status_code == 201, submitted.text
    offer_id = submitted.json()["id"]
    reviewed = buyer.post(
        f"/api/v1/supplier-portal/offers/{offer_id}/review",
        json={"status": "accepted"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "accepted"

    operator = _client(engine, "operator")
    assert operator.get("/api/v1/supplier-portal/offers").status_code == 403
    assert operator.post(
        "/api/v1/supplier-portal/access",
        json={"partner_id": "vendor-1"},
    ).status_code == 403


def test_retail_portal_token_cannot_use_supplier_offer_routes():
    engine = _engine()
    _access, retail_token = OperationalMoatService(engine).issue_partner_portal_access(
        organization_id="org-1",
        facility_id="fac-1",
        partner_id="customer-1",
        actor="admin",
    )
    client = _client(engine)
    response = client.post(f"/api/v1/commerce-portal/{retail_token}/offers", json=_offer_payload())
    assert response.status_code == 404


def test_production_fastapi_source_registers_supplier_surfaces():
    source = Path("backend/app/main.py").read_text(encoding="utf-8")
    assert (
        "from .routers.supplier_portal import router as supplier_portal_router, "
        "public_router as supplier_commerce_portal_router"
    ) in source
    assert "app.include_router(supplier_portal_router, prefix=settings.api_prefix)" in source
    assert "app.include_router(supplier_commerce_portal_router, prefix=settings.api_prefix)" in source
