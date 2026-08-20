"""Wholesale fulfillment, invoicing and A/R service over canonical commercial orders."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.coman.models import CommercialOrder, CommercialOrderLine, Product, TradePartner, utc_now

from .models import CommercialInvoice, CommercialInvoiceLine, CommercialPayment, CommercialShipment, CustomerPriceRule


class CommercialFinanceService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @staticmethod
    def _order(session, organization_id: str, facility_id: str, order_id: str) -> CommercialOrder:
        order = session.get(CommercialOrder, order_id)
        if not order or order.organization_id != organization_id or order.facility_id != facility_id:
            raise ValueError("Commercial order was not found in the active facility.")
        return order

    def create_invoice_from_order(
        self,
        *,
        organization_id: str,
        facility_id: str,
        order_id: str,
        invoice_number: str,
        actor: str,
        due_days: int = 30,
        discount_usd: float = 0.0,
        tax_usd: float = 0.0,
    ) -> CommercialInvoice:
        if not str(invoice_number or "").strip():
            raise ValueError("Invoice number is required.")
        if due_days < 0 or discount_usd < 0 or tax_usd < 0:
            raise ValueError("Invoice terms and amounts cannot be negative.")
        with self._sessions.begin() as session:
            order = self._order(session, organization_id, facility_id, order_id)
            if order.order_type != "sales":
                raise ValueError("Only sales orders can become customer invoices.")
            existing = session.scalar(select(CommercialInvoice).where(CommercialInvoice.organization_id == organization_id, CommercialInvoice.invoice_number == invoice_number.strip()))
            if existing:
                return existing
            lines = list(session.scalars(select(CommercialOrderLine).where(CommercialOrderLine.commercial_order_id == order.id).order_by(CommercialOrderLine.position)))
            if not lines:
                raise ValueError("Add at least one order line before invoicing.")
            subtotal = sum(float(line.quantity or 0) * float(line.unit_price or 0) for line in lines)
            total = max(0.0, subtotal - float(discount_usd) + float(tax_usd))
            invoice = CommercialInvoice(
                organization_id=organization_id,
                facility_id=facility_id,
                commercial_order_id=order.id,
                partner_id=order.partner_id,
                invoice_number=invoice_number.strip(),
                status="draft",
                issue_date=date.today(),
                due_date=date.today() + timedelta(days=int(due_days)),
                currency=order.currency or "USD",
                subtotal_usd=subtotal,
                discount_usd=float(discount_usd),
                tax_usd=float(tax_usd),
                total_usd=total,
                balance_usd=total,
                created_by=actor,
            )
            session.add(invoice); session.flush()
            for line in lines:
                session.add(CommercialInvoiceLine(
                    organization_id=organization_id,
                    invoice_id=invoice.id,
                    commercial_order_line_id=line.id,
                    product_id=line.product_id,
                    position=line.position,
                    description=line.description,
                    quantity=float(line.quantity),
                    unit=line.unit,
                    unit_price_usd=float(line.unit_price),
                    line_total_usd=float(line.quantity) * float(line.unit_price),
                ))
            order.payment_status = "draft"
            return invoice

    def send_invoice(self, *, organization_id: str, facility_id: str, invoice_id: str) -> CommercialInvoice:
        with self._sessions.begin() as session:
            invoice = session.get(CommercialInvoice, invoice_id)
            if not invoice or invoice.organization_id != organization_id or invoice.facility_id != facility_id:
                raise ValueError("Invoice was not found in the active facility.")
            if invoice.status == "void":
                raise ValueError("A void invoice cannot be sent.")
            invoice.status = "sent" if invoice.balance_usd > 0 else "paid"
            order = self._order(session, organization_id, facility_id, invoice.commercial_order_id)
            order.payment_status = invoice.status
            return invoice

    def record_payment(
        self,
        *,
        organization_id: str,
        facility_id: str,
        invoice_id: str,
        amount_usd: float,
        actor: str,
        method: str = "other",
        reference: str = "",
        payment_date: date | None = None,
        notes: str = "",
    ) -> CommercialPayment:
        if amount_usd <= 0:
            raise ValueError("Payment amount must be positive.")
        with self._sessions.begin() as session:
            invoice = session.get(CommercialInvoice, invoice_id)
            if not invoice or invoice.organization_id != organization_id or invoice.facility_id != facility_id:
                raise ValueError("Invoice was not found in the active facility.")
            if invoice.status == "void":
                raise ValueError("Payments cannot be posted to a void invoice.")
            if amount_usd > float(invoice.balance_usd or 0) + 1e-9:
                raise ValueError("Payment exceeds the remaining invoice balance.")
            payment = CommercialPayment(
                organization_id=organization_id,
                facility_id=facility_id,
                invoice_id=invoice.id,
                amount_usd=float(amount_usd),
                payment_date=payment_date or date.today(),
                method=str(method or "other"),
                reference=str(reference or ""),
                notes=str(notes or ""),
                recorded_by=actor,
            )
            session.add(payment)
            invoice.balance_usd = max(0.0, float(invoice.balance_usd or 0) - float(amount_usd))
            invoice.status = "paid" if invoice.balance_usd <= 1e-9 else "partial"
            order = self._order(session, organization_id, facility_id, invoice.commercial_order_id)
            order.payment_status = invoice.status
            return payment

    def create_shipment(
        self,
        *,
        organization_id: str,
        facility_id: str,
        order_id: str,
        shipment_number: str,
        actor: str,
        manifest_reference: str = "",
        carrier: str = "",
        tracking_reference: str = "",
    ) -> CommercialShipment:
        with self._sessions.begin() as session:
            order = self._order(session, organization_id, facility_id, order_id)
            if order.order_type != "sales":
                raise ValueError("Only sales orders can be shipped to a customer.")
            shipment = CommercialShipment(
                organization_id=organization_id,
                facility_id=facility_id,
                commercial_order_id=order.id,
                shipment_number=str(shipment_number or "").strip(),
                status="planned",
                manifest_reference=str(manifest_reference or "").strip(),
                carrier=str(carrier or "").strip(),
                tracking_reference=str(tracking_reference or "").strip(),
                created_by=actor,
            )
            if not shipment.shipment_number:
                raise ValueError("Shipment number is required.")
            session.add(shipment); session.flush(); return shipment

    def update_shipment_status(self, *, organization_id: str, facility_id: str, shipment_id: str, status: str) -> CommercialShipment:
        status = str(status or "").strip().casefold()
        allowed = {"planned","picking","packed","manifested","shipped","delivered","cancelled"}
        if status not in allowed:
            raise ValueError("Unsupported shipment status.")
        with self._sessions.begin() as session:
            shipment = session.get(CommercialShipment, shipment_id)
            if not shipment or shipment.organization_id != organization_id or shipment.facility_id != facility_id:
                raise ValueError("Shipment was not found in the active facility.")
            shipment.status = status
            if status == "shipped" and shipment.shipped_at is None:
                shipment.shipped_at = utc_now()
            if status == "delivered" and shipment.delivered_at is None:
                shipment.delivered_at = utc_now()
            return shipment

    def upsert_customer_price(
        self,
        *,
        organization_id: str,
        partner_id: str,
        product_id: str,
        actor: str,
        price_usd: float = 0.0,
        discount_pct: float = 0.0,
        notes: str = "",
    ) -> CustomerPriceRule:
        if price_usd < 0 or not 0 <= discount_pct <= 100:
            raise ValueError("Invalid customer price rule.")
        with self._sessions.begin() as session:
            partner = session.get(TradePartner, partner_id)
            product = session.get(Product, product_id)
            if not partner or partner.organization_id != organization_id or not product or product.organization_id != organization_id:
                raise ValueError("Customer/product is outside this organization.")
            row = session.scalar(select(CustomerPriceRule).where(CustomerPriceRule.partner_id == partner_id, CustomerPriceRule.product_id == product_id))
            if row is None:
                row = CustomerPriceRule(organization_id=organization_id, partner_id=partner_id, product_id=product_id, updated_by=actor)
                session.add(row)
            row.price_usd = float(price_usd)
            row.discount_pct = float(discount_pct)
            row.notes = str(notes or "")
            row.active = True
            row.updated_by = actor
            session.flush(); return row

    def resolve_customer_price(self, organization_id: str, partner_id: str, product_id: str, base_price: float) -> float:
        with self._sessions() as session:
            rule = session.scalar(select(CustomerPriceRule).where(CustomerPriceRule.organization_id == organization_id, CustomerPriceRule.partner_id == partner_id, CustomerPriceRule.product_id == product_id, CustomerPriceRule.active.is_(True)))
            if not rule:
                return float(base_price or 0)
            if float(rule.price_usd or 0) > 0:
                return float(rule.price_usd)
            return max(0.0, float(base_price or 0) * (1 - float(rule.discount_pct or 0) / 100.0))

    def ar_summary(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        today = date.today()
        with self._sessions.begin() as session:
            invoices = list(session.scalars(select(CommercialInvoice).where(CommercialInvoice.organization_id == organization_id, CommercialInvoice.facility_id == facility_id, CommercialInvoice.status.notin_(("paid","void"))).order_by(CommercialInvoice.due_date)))
            buckets = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "90_plus": 0.0}
            rows = []
            for invoice in invoices:
                if invoice.status in {"sent","partial"} and invoice.due_date < today:
                    invoice.status = "overdue"
                age = max(0, (today - invoice.due_date).days)
                balance = float(invoice.balance_usd or 0)
                if age == 0:
                    bucket = "current"
                elif age <= 30:
                    bucket = "1_30"
                elif age <= 60:
                    bucket = "31_60"
                elif age <= 90:
                    bucket = "61_90"
                else:
                    bucket = "90_plus"
                buckets[bucket] += balance
                rows.append({"invoice_id": invoice.id, "Invoice": invoice.invoice_number, "Status": invoice.status.title(), "Due": invoice.due_date, "Balance": balance, "Days Past Due": age})
            return {"total_ar": sum(buckets.values()), "buckets": buckets, "invoices": rows}

    def order_finance(self, organization_id: str, facility_id: str, order_id: str) -> dict[str, Any]:
        with self._sessions() as session:
            order = self._order(session, organization_id, facility_id, order_id)
            invoices = list(session.scalars(select(CommercialInvoice).where(CommercialInvoice.commercial_order_id == order.id).order_by(CommercialInvoice.created_at.desc())))
            shipments = list(session.scalars(select(CommercialShipment).where(CommercialShipment.commercial_order_id == order.id).order_by(CommercialShipment.created_at.desc())))
            return {"order": order, "invoices": invoices, "shipments": shipments}
