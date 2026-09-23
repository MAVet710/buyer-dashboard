"""Read projections of the existing commercial purchase-order ledger."""
from sqlalchemy import Engine, func, or_, select
from sqlalchemy.orm import Session

from modules.coman.models import CommercialOrder, CommercialOrderLine, Facility, TradePartner
from services.purchase_order_pdf import saved_order_total


ORDER_FIELDS = ("id", "partner_id", "order_number", "order_type", "order_date", "due_at", "status", "payment_status", "currency", "external_reference", "notes")
LINE_FIELDS = ("id", "commercial_order_id", "product_id", "position", "description", "sku_snapshot", "quantity", "unit", "unit_price", "fulfilled_quantity", "notes")


def _scope(organization_id: str, facility_id: str):
    if not organization_id or not facility_id:
        raise ValueError("Choose an organization and facility before reading purchase orders.")
    return (
        CommercialOrder.organization_id == organization_id,
        CommercialOrder.facility_id == facility_id,
        CommercialOrder.order_type == "purchase",
    )


def list_saved_purchase_orders(engine: Engine, organization_id: str, facility_id: str, *, search: str = "", offset: int = 0, limit: int = 50) -> dict:
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("Invalid purchase-order page.")
    terms = list(_scope(organization_id, facility_id))
    if search.strip():
        pattern = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        terms.append(or_(CommercialOrder.order_number.ilike(pattern, escape="\\"), TradePartner.name.ilike(pattern, escape="\\")))
    joined = (TradePartner.id == CommercialOrder.partner_id) & (TradePartner.organization_id == organization_id)
    with Session(engine) as session:
        total = int(session.scalar(select(func.count()).select_from(CommercialOrder).outerjoin(TradePartner, joined).where(*terms)) or 0)
        rows = session.execute(select(CommercialOrder, TradePartner.name).outerjoin(TradePartner, joined).where(*terms).order_by(CommercialOrder.order_date.desc(), CommercialOrder.id.desc()).offset(offset).limit(limit)).all()
        items = [{**{key: getattr(order, key) for key in ORDER_FIELDS}, "partner_name": name or "Vendor unavailable"} for order, name in rows]
        return {"items": items, "total": total, "offset": offset, "limit": limit, "has_more": offset + len(items) < total}


def get_saved_purchase_order(engine: Engine, organization_id: str, facility_id: str, order_id: str) -> dict:
    with Session(engine) as session:
        order = session.scalar(select(CommercialOrder).where(*_scope(organization_id, facility_id), CommercialOrder.id == order_id))
        if order is None:
            raise ValueError("Purchase order was not found in the active facility.")
        lines = session.scalars(select(CommercialOrderLine).where(CommercialOrderLine.organization_id == organization_id, CommercialOrderLine.commercial_order_id == order.id).order_by(CommercialOrderLine.position, CommercialOrderLine.id)).all()
        partner = session.scalar(select(TradePartner).where(TradePartner.id == order.partner_id, TradePartner.organization_id == organization_id))
        facility = session.scalar(select(Facility).where(Facility.id == facility_id, Facility.organization_id == organization_id))
        line_values = [{key: getattr(line, key) for key in LINE_FIELDS} for line in lines]
        return {
            "order": {key: getattr(order, key) for key in ORDER_FIELDS},
            "lines": line_values,
            "vendor_name": partner.name if partner else "Vendor unavailable",
            "vendor_license": partner.license_or_registration if partner else "",
            "facility_name": facility.name if facility else "",
            "total": str(saved_order_total(line_values)),
        }
