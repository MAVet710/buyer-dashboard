from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.coman.models import CommercialOrder, CommercialOrderLine
from modules.doobie_actions.service import DoobieActionService
from modules.supplier_portal.buying import SupplierBuyingService
from modules.supplier_portal.service import SupplierPortalService
from tests.test_supplier_portal_buying import _setup


def test_supplier_quote_quantity_and_price_reconcile_to_exact_approved_purchase_order_value():
    engine, organization, facility, _product, vendor, offer, offer_line = _setup()
    SupplierPortalService(engine).review_offer(
        organization_id=organization.id,
        facility_id=facility.id,
        offer_id=offer.id,
        status="accepted",
        actor="functional-output-buyer",
    )

    requested_quantity = 2.0
    quoted_unit_price = 650.0
    expected_total = 1300.0
    proposal = SupplierBuyingService(engine).propose_purchase_order(
        organization_id=organization.id,
        facility_id=facility.id,
        offer_id=offer.id,
        selections=[{"line_id": offer_line.id, "quantity": requested_quantity}],
        actor="functional-output-buyer",
        order_number="FO-SUP-PO-1300",
    )

    # A proposal is not yet a PO; the dollar commitment must remain approval-gated.
    with Session(engine) as session:
        assert session.scalar(select(CommercialOrder).where(CommercialOrder.organization_id == organization.id)) is None

    actions = DoobieActionService(engine)
    actions.approve(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="functional-output-approver",
    )
    result = actions.execute(
        organization_id=organization.id,
        facility_id=facility.id,
        proposal_id=proposal.id,
        actor="functional-output-approver",
    )

    with Session(engine) as session:
        order = session.get(CommercialOrder, result["commercial_order_id"])
        assert order is not None
        assert order.order_type == "purchase"
        assert order.partner_id == vendor.id
        assert order.order_number == "FO-SUP-PO-1300"
        lines = list(session.scalars(select(CommercialOrderLine).where(CommercialOrderLine.commercial_order_id == order.id)))
        assert len(lines) == 1
        line = lines[0]
        assert float(line.quantity) == requested_quantity
        assert line.unit == "lb"
        assert float(line.unit_price) == quoted_unit_price
        assert float(line.quantity) * float(line.unit_price) == expected_total
