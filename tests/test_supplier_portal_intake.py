from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from modules.coman.models import Facility, Organization, TradePartner
from modules.operational_moats.models import PartnerPortalAccess
from modules.operational_moats.service import OperationalMoatService
from modules.supplier_portal.models import SupplierOffer, SupplierOfferLine, SupplierPortalGrant
from modules.supplier_portal.service import SupplierPortalService


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Organization.__table__.create(engine)
    Facility.__table__.create(engine)
    TradePartner.__table__.create(engine)
    PartnerPortalAccess.__table__.create(engine)
    SupplierPortalGrant.__table__.create(engine)
    SupplierOffer.__table__.create(engine)
    SupplierOfferLine.__table__.create(engine)
    with Session(engine) as session:
        session.add(Organization(id="org-1", name="Demo", slug="demo"))
        session.add(Facility(id="fac-1", organization_id="org-1", name="Store", code="STORE"))
        session.add(TradePartner(id="vendor-1", organization_id="org-1", name="Vendor One", partner_type="vendor"))
        session.add(TradePartner(id="customer-1", organization_id="org-1", name="Retailer One", partner_type="customer"))
        session.commit()
    return engine


def _line(price: float = 700.0):
    return {
        "supplier_sku": "GMO-BULK",
        "product_name": "GMO Bulk Flower",
        "strain": "GMO",
        "form": "flower",
        "available_quantity": 12.0,
        "availability_unit": "lb",
        "unit_price": price,
        "price_basis": "lb",
        "minimum_order_quantity": 1.0,
        "minimum_order_unit": "lb",
        "batch_lot_identifier": "LOT-GMO-1",
        "coa_reference": "supplier-coa-123",
        "sample_status": "offered",
        "promotion_terms": "10+ lb: 5% off",
    }


def test_supplier_access_reuses_partner_portal_identity_but_not_retailer_token_namespace():
    engine = _engine()
    service = SupplierPortalService(engine)

    access, grant, token = service.issue_supplier_access(
        organization_id="org-1",
        facility_id="fac-1",
        partner_id="vendor-1",
        actor="buyer-admin",
    )
    resolved, resolved_grant = service.resolve_supplier_access(token, permission="offer:submit")
    assert resolved.id == access.id
    assert resolved_grant.id == grant.id
    assert resolved.partner_id == "vendor-1"

    # The same raw token must fail on the pre-existing retailer portal resolver;
    # supplier endpoints add the private supplier scope before resolving it.
    try:
        OperationalMoatService(engine).resolve_partner_portal(token)
    except ValueError as exc:
        assert "invalid or expired" in str(exc)
    else:
        raise AssertionError("Supplier credentials must not resolve on retailer portal routes.")

    offer = service.submit_offer(
        access=resolved,
        lines=[_line()],
        external_reference="September menu",
        promotion_terms="Fall wholesale pricing",
        lead_time_days=3,
    )
    assert offer.status == "submitted"
    assert offer.revision == 1
    lines = service.list_offer_lines("org-1", offer.id)
    assert len(lines) == 1
    assert lines[0].strain == "GMO"
    assert lines[0].unit_price == 700.0
    assert lines[0].coa_reference == "supplier-coa-123"

    # This foundation intentionally works without creating ERP order/inventory
    # tables, proving supplier submission is staging data rather than a mutation.
    table_names = set(inspect(engine).get_table_names())
    assert "commercial_orders" not in table_names
    assert "coman_inventory_transactions" not in table_names


def test_existing_retailer_portal_token_does_not_gain_supplier_permissions():
    engine = _engine()
    retail_access, retail_token = OperationalMoatService(engine).issue_partner_portal_access(
        organization_id="org-1",
        facility_id="fac-1",
        partner_id="customer-1",
        actor="admin",
    )
    assert retail_access.partner_id == "customer-1"

    service = SupplierPortalService(engine)
    try:
        service.resolve_supplier_access(retail_token, permission="offer:read")
    except ValueError as exc:
        assert "invalid or expired" in str(exc) or "does not have supplier access" in str(exc)
    else:
        raise AssertionError("Retailer portal access must not inherit supplier permissions.")


def test_supplier_offer_revision_is_durable_and_supersedes_prior_revision():
    engine = _engine()
    service = SupplierPortalService(engine)
    access, _grant, token = service.issue_supplier_access(
        organization_id="org-1",
        facility_id="fac-1",
        partner_id="vendor-1",
        actor="admin",
    )
    access, _grant = service.resolve_supplier_access(token, permission="offer:submit")
    first = service.submit_offer(access=access, lines=[_line(700.0)], external_reference="MENU-1")
    second = service.revise_offer(
        access=access,
        offer_id=first.id,
        lines=[_line(675.0)],
        external_reference="MENU-1-R2",
    )

    assert second.offer_group_id == first.offer_group_id
    assert second.revision == 2
    assert second.supersedes_offer_id == first.id
    with Session(engine) as session:
        persisted_first = session.get(SupplierOffer, first.id)
        assert persisted_first is not None
        assert persisted_first.status == "superseded"
    assert service.list_offer_lines("org-1", second.id)[0].unit_price == 675.0


def test_supplier_token_permissions_fail_closed():
    engine = _engine()
    service = SupplierPortalService(engine)
    access, _grant, token = service.issue_supplier_access(
        organization_id="org-1",
        facility_id="fac-1",
        partner_id="vendor-1",
        actor="admin",
        permissions=["offer:read"],
    )
    resolved, _grant = service.resolve_supplier_access(token, permission="offer:read")
    try:
        service.submit_offer(access=resolved, lines=[_line()])
    except ValueError as exc:
        assert "does not allow offer submission" in str(exc)
    else:
        raise AssertionError("Read-only supplier access must not submit offers.")
