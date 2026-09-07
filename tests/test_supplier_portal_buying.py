from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.schemas.inventory import InventoryReceiptCreate
from backend.app.services.inventory_receiving import InventoryReceiptBatchService
from modules.coman import ComanRepository
from modules.coman.models import Base, CommercialOrder, CommercialOrderLine, InventoryLot, InventoryTransaction, utc_now
from modules.commercial.repository import CommercialRepository
from modules.doobie_actions.models import ActionProposal
from modules.doobie_actions.service import DoobieActionService
from modules.supplier_portal.buying import SupplierBuyingService, parse_supplier_lineage_note
from modules.supplier_portal.models import SupplierOffer
from modules.supplier_portal.service import SupplierPortalService


COA_REFERENCE = "doobielogic-coa:coa-gmo-0907"


def _setup():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    coman = ComanRepository(engine)
    organization = coman.create_organization("Supplier Buying Test")
    facility = coman.create_facility(organization.id, "Buyer Facility", "BUYER")
    product = coman.create_product(
        organization.id,
        sku="GMO-BULK",
        name="GMO Bulk Flower",
        item_type="cannabis",
        base_unit="lb",
        unit_cost=0,
        retail_price=0,
        actor="buyer-1",
    )
    vendor = CommercialRepository(engine).create_trade_partner(
        organization.id,
        name="Example Licensed Supplier",
        partner_type="vendor",
        actor="buyer-1",
        license_or_registration="MP281999",
    )
    access, _grant, _token = SupplierPortalService(engine).issue_supplier_access(
        organization_id=organization.id,
        facility_id=facility.id,
        partner_id=vendor.id,
        actor="buyer-1",
    )
    offer = SupplierPortalService(engine).submit_offer(
        access=access,
        external_reference="SEP-GMO-MENU",
        promotion_terms="5% off at 10 lb",
        lead_time_days=3,
        lines=[
            {
                "product_id": product.id,
                "supplier_sku": "SUP-GMO-BULK",
                "product_name": "GMO Bulk Flower",
                "strain": "GMO",
                "form": "flower",
                "available_quantity": 12,
                "availability_unit": "lb",
                "unit_price": 650,
                "price_basis": "lb",
                "minimum_order_quantity": 1,
                "minimum_order_unit": "lb",
                "batch_lot_identifier": "GMO-SUP-0907",
                "coa_reference": COA_REFERENCE,
                "sample_status": "offered",
            }
        ],
    )
    line = SupplierPortalService(engine).list_offer_lines(organization.id, offer.id)[0]
    return engine, organization, facility, product, vendor, offer, line


def test_supplier_comparison_marks_stale_and_keeps_wholesale_price_separate_from_ma_retail(monkeypatch):
    engine, organization, facility, product, _vendor, offer, line = _setup()
    with Session(engine) as session, session.begin():
        stored = session.get(SupplierOffer, offer.id)
        stored.submitted_at = utc_now() - timedelta(days=20)

    service = SupplierBuyingService(engine)
    monkeypatch.setattr(
        service,
        "_buyer_context",
        lambda *_args, **_kwargs: {
            "status": "available",
            "summary": {"tracked_skus": 1},
            "by_category": [{"category": "flower", "units_sold": 80, "revenue": 2400}],
            "by_product": [
                {
                    "product_name": product.name,
                    "category": "flower",
                    "units_sold": 80,
                    "revenue": 2400,
                    "avg_daily_units": 2,
                    "days_of_cover": 8,
                    "risk_flag": "Reorder Risk",
                }
            ],
            "purchase_priorities": [],
            "sources": {"inventory": "inventory.xlsx", "sales": "sales.xlsx"},
        },
    )
    monkeypatch.setattr(
        service,
        "_market_context",
        lambda *_args, **_kwargs: {
            "status": "available",
            "state": "MA",
            "source": "Massachusetts CCC",
            "categories": [{"category": "Flower", "market_growth": 0.12, "signal": "BUY"}],
        },
    )

    result = service.compare_offer(
        organization.id,
        facility.id,
        offer.id,
        stale_after_days=14,
    )

    assert result["offer"]["freshness"]["state"] == "stale"
    assert result["price_context"]["basis"] == "wholesale_quote"
    assert "not directly compared" in result["price_context"]["rule"]
    compared = result["lines"][0]
    assert compared["line_id"] == line.id
    assert compared["quote"] == {"unit_price": 650.0, "price_basis": "lb", "wholesale_only": True}
    assert compared["buyer_product"]["risk_flag"] == "Reorder Risk"
    assert compared["buyer_category"]["units_sold"] == 80
    assert compared["ma_market_category"]["signal"] == "BUY"


def test_selected_supplier_lines_require_human_approval_then_preserve_lineage_through_receiving():
    engine, organization, facility, product, vendor, offer, offer_line = _setup()
    SupplierPortalService(engine).review_offer(
        organization_id=organization.id,
        facility_id=facility.id,
        offer_id=offer.id,
        status="accepted",
        actor="buyer-1",
    )

    buying = SupplierBuyingService(engine)
    proposal = buying.propose_purchase_order(
        organization_id=organization.id,
        facility_id=facility.id,
        offer_id=offer.id,
        selections=[{"line_id": offer_line.id, "quantity": 2}],
        actor="buyer-1",
        order_number="SUP-PO-1001",
    )

    assert proposal.action_type == "create_purchase_order"
    assert proposal.status == "proposed"
    assert proposal.source_type == "supplier_portal"
    assert proposal.source_id == offer.id
    with Session(engine) as session:
        assert session.scalar(select(CommercialOrder).where(CommercialOrder.organization_id == organization.id)) is None
        stored_proposal = session.get(ActionProposal, proposal.id)
        assert stored_proposal is not None
        assert stored_proposal.status == "proposed"

    actions = DoobieActionService(engine)
    actions.approve(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="buyer-approver",
    )
    result = actions.execute(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="buyer-approver",
    )
    order_id = result["commercial_order_id"]

    with Session(engine) as session:
        order = session.get(CommercialOrder, order_id)
        assert order is not None
        assert order.order_type == "purchase"
        assert order.partner_id == vendor.id
        order_line = session.scalar(
            select(CommercialOrderLine).where(CommercialOrderLine.commercial_order_id == order.id)
        )
        assert order_line is not None
        lineage = parse_supplier_lineage_note(order_line.notes)
        assert lineage["source"] == "supplier_portal"
        assert lineage["partner_id"] == vendor.id
        assert lineage["supplier_offer_id"] == offer.id
        assert lineage["supplier_offer_line_id"] == offer_line.id
        assert lineage["batch_lot_identifier"] == "GMO-SUP-0907"
        assert lineage["coa_reference"] == COA_REFERENCE
        order_line_id = order_line.id

    receipt = InventoryReceiptBatchService(engine).post(
        organization.id,
        facility.id,
        operation="production",
        actor="receiver-1",
        rows=[
            InventoryReceiptCreate(
                product_id=product.id,
                lot_code="GMO-RECEIVED-0907",
                package_id="1A4000000000000000009090",
                quantity=2,
                unit="lb",
                location="RECEIVING",
                source_name=vendor.name,
                manifest_reference="MANIFEST-SUP-0907",
                lab_testing_state="TestPassed",
                coa_reference=COA_REFERENCE,
                commercial_order_id=order_id,
                commercial_order_line_id=order_line_id,
                notes="Received from approved supplier offer.",
            )
        ],
    )[0]

    with Session(engine) as session:
        transaction = session.get(InventoryTransaction, receipt.transaction_id)
        lot = session.get(InventoryLot, receipt.lot_id)
        order_line = session.get(CommercialOrderLine, order_line_id)
        order = session.get(CommercialOrder, order_id)
        assert transaction is not None and lot is not None and order_line is not None and order is not None
        assert transaction.commercial_order_id == order_id
        assert transaction.commercial_order_line_id == order_line_id
        assert order.partner_id == vendor.id
        lineage = parse_supplier_lineage_note(order_line.notes)
        assert lineage["supplier_offer_id"] == offer.id
        assert lineage["supplier_offer_line_id"] == offer_line.id
        assert lineage["coa_reference"] == COA_REFERENCE
        assert COA_REFERENCE in lot.notes
        assert "MANIFEST-SUP-0907" in lot.notes
