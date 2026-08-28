from pathlib import Path

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import RequestContext
from backend.app.routers.admin_storefronts import (
    StorefrontOwnershipUpdate,
    list_storefront_ownership,
    router as admin_storefronts_router,
    update_storefront_ownership,
)
from modules.coman.models import AuditEvent, Base, Facility, Organization, Product
from modules.commerce_storefronts.models import (
    CommerceStorefront,
    CommerceStorefrontOrderRequest,
    CommerceStorefrontProduct,
)


ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        old_org = Organization(id="org-old", name="Old Owner", slug="old-owner")
        cowboy_org = Organization(id="org-cowboy", name="Cowboy Kush", slug="cbk")
        old_facility = Facility(
            id="facility-old",
            organization_id=old_org.id,
            name="Old Facility",
            code="OLD",
            commercial_enabled=True,
        )
        cowboy_facility = Facility(
            id="facility-cowboy",
            organization_id=cowboy_org.id,
            name="CO-Op",
            code="CBK COOP",
            commercial_enabled=True,
        )
        noncommercial = Facility(
            id="facility-noncommercial",
            organization_id=cowboy_org.id,
            name="Cultivation Only",
            code="CBK CULT",
            commercial_enabled=False,
        )
        storefront = CommerceStorefront(
            id="storefront-cowboy",
            organization_id=old_org.id,
            facility_id=old_facility.id,
            slug="cowboykush",
            subdomain="cowboykush",
            display_name="Cowboy Kush",
            published=True,
            created_by="seed",
            updated_by="seed",
        )
        old_product = Product(
            id="product-old",
            organization_id=old_org.id,
            sku="OLD-1",
            name="Old Catalog Item",
            item_type="finished_good",
        )
        session.add_all((old_org, cowboy_org, old_facility, cowboy_facility, noncommercial, storefront, old_product))
        session.commit()
    return engine


def _dev():
    return RequestContext("dev-user", "org-old", "facility-old", "dev")


def test_dev_can_list_storefront_tenant_ownership():
    engine = _engine()
    rows = list_storefront_ownership(context=_dev(), engine=engine)
    assert len(rows) == 1
    assert rows[0]["id"] == "storefront-cowboy"
    assert rows[0]["hostname"] == "cowboykush.doobielogic.io"
    assert rows[0]["organization_id"] == "org-old"
    assert rows[0]["facility_id"] == "facility-old"
    assert rows[0]["listing_count"] == 0
    assert rows[0]["request_count"] == 0


def test_dev_can_move_clean_storefront_to_cowboy_kush_and_audit_it():
    engine = _engine()
    result = update_storefront_ownership(
        "storefront-cowboy",
        StorefrontOwnershipUpdate(organization_id="org-cowboy", facility_id="facility-cowboy"),
        context=_dev(),
        engine=engine,
    )

    assert result["organization_name"] == "Cowboy Kush"
    assert result["facility_name"] == "CO-Op"
    assert result["hostname"] == "cowboykush.doobielogic.io"
    with Session(engine) as session:
        row = session.get(CommerceStorefront, "storefront-cowboy")
        assert row.organization_id == "org-cowboy"
        assert row.facility_id == "facility-cowboy"
        event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_type == "commerce_storefront",
                AuditEvent.entity_id == "storefront-cowboy",
                AuditEvent.action == "storefront_ownership_updated",
            )
        )
        assert event is not None
        assert event.organization_id == "org-cowboy"
        assert event.facility_id == "facility-cowboy"
        assert event.actor == "dev-user"


def test_cross_org_move_requires_explicit_catalog_clear_and_never_rehomes_old_product_ids():
    engine = _engine()
    with Session(engine) as session, session.begin():
        session.add(
            CommerceStorefrontProduct(
                id="listing-old",
                organization_id="org-old",
                storefront_id="storefront-cowboy",
                product_id="product-old",
                price_usd=12.0,
            )
        )

    payload = StorefrontOwnershipUpdate(organization_id="org-cowboy", facility_id="facility-cowboy")
    try:
        update_storefront_ownership("storefront-cowboy", payload, context=_dev(), engine=engine)
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "Confirm catalog clearing" in exc.detail
    else:
        raise AssertionError("Cross-organization move unexpectedly retained a foreign catalog")

    moved = update_storefront_ownership(
        "storefront-cowboy",
        payload.model_copy(update={"clear_catalog": True}),
        context=_dev(),
        engine=engine,
    )
    assert moved["listing_count"] == 0
    with Session(engine) as session:
        assert session.get(CommerceStorefrontProduct, "listing-old") is None


def test_cross_org_move_is_blocked_when_order_request_history_exists():
    engine = _engine()
    with Session(engine) as session, session.begin():
        session.add(
            CommerceStorefrontOrderRequest(
                id="request-old",
                organization_id="org-old",
                facility_id="facility-old",
                storefront_id="storefront-cowboy",
                buyer_company="Buyer LLC",
                buyer_contact="Buyer",
                buyer_email="buyer@example.com",
            )
        )

    try:
        update_storefront_ownership(
            "storefront-cowboy",
            StorefrontOwnershipUpdate(
                organization_id="org-cowboy",
                facility_id="facility-cowboy",
                clear_catalog=True,
            ),
            context=_dev(),
            engine=engine,
        )
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "order-request history" in exc.detail
    else:
        raise AssertionError("Historical order requests unexpectedly crossed organizations")


def test_storefront_target_must_be_commercial_and_belong_to_selected_org():
    engine = _engine()
    try:
        update_storefront_ownership(
            "storefront-cowboy",
            StorefrontOwnershipUpdate(organization_id="org-cowboy", facility_id="facility-old"),
            context=_dev(),
            engine=engine,
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "does not belong" in exc.detail
    else:
        raise AssertionError("Cross-organization facility mismatch unexpectedly succeeded")

    try:
        update_storefront_ownership(
            "storefront-cowboy",
            StorefrontOwnershipUpdate(organization_id="org-cowboy", facility_id="facility-noncommercial"),
            context=_dev(),
            engine=engine,
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Commercial" in exc.detail
    else:
        raise AssertionError("Non-commercial facility unexpectedly received a storefront")


def test_non_dev_cannot_reassign_storefronts():
    engine = _engine()
    context = RequestContext("admin-user", "org-old", "facility-old", "admin")
    try:
        list_storefront_ownership(context=context, engine=engine)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Non-DEV storefront ownership listing unexpectedly succeeded")


def test_storefront_admin_router_registers_both_routes_in_isolation():
    isolated = FastAPI()
    isolated.include_router(admin_storefronts_router, prefix="/api/v1")
    names = {getattr(route, "name", "") for route in isolated.routes}
    assert "list_storefront_ownership" in names
    assert "update_storefront_ownership" in names


def test_production_app_registers_storefront_admin_router_source_contract():
    assert "from .routers.admin_storefronts import router as admin_storefronts_router" in MAIN_SOURCE
    assert "app.include_router(admin_storefronts_router, prefix=settings.api_prefix)" in MAIN_SOURCE
