"""Read-only Wholesale Accounting control-plane snapshot.

The accounting hub joins canonical commercial A/R, invoices, payments, sales-order
payment state, and durable QuickBooks identity/sync metadata. It never reaches out
to QuickBooks and never posts accounting mutations.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.coman.models import CommercialOrder, CommercialOrderLine, TradePartner
from modules.commercial_finance.models import CommercialInvoice, CommercialPayment
from modules.commercial_finance.service import CommercialFinanceService
from modules.integrations.accounting_links import AccountingSyncLink
from services.quickbooks_purchasing import QuickBooksPurchasingSyncService


def _unavailable_qbo_purchasing(message: str) -> dict[str, Any]:
    return {
        "provider": "quickbooks",
        "facility_id": "",
        "connected": False,
        "read_only": True,
        "summary": {
            "vendor_count": 0,
            "purchase_order_count": 0,
            "synced_vendor_count": 0,
            "synced_purchase_order_count": 0,
            "attention_count": 0,
        },
        "vendors": [],
        "purchase_orders": [],
        "message": message,
    }


class WholesaleAccountingService:
    def __init__(self, engine, encryption_key: str):
        self.engine = engine
        self.encryption_key = encryption_key

    def snapshot(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        ar = CommercialFinanceService(self.engine).ar_summary(organization_id, facility_id)
        if str(self.encryption_key or "").strip():
            try:
                qbo_purchasing = QuickBooksPurchasingSyncService(self.engine, self.encryption_key).reconciliation_snapshot(
                    organization_id, facility_id
                )
            except RuntimeError as exc:
                qbo_purchasing = _unavailable_qbo_purchasing(f"QuickBooks reconciliation is unavailable: {exc}")
        else:
            qbo_purchasing = _unavailable_qbo_purchasing(
                "QuickBooks is not configured for this runtime. Local wholesale accounting remains available."
            )
        qbo_purchasing["facility_id"] = facility_id

        with Session(self.engine) as session:
            partners = list(session.scalars(select(TradePartner).where(TradePartner.organization_id == organization_id)))
            partner_by_id = {row.id: row for row in partners}
            orders = list(session.scalars(select(CommercialOrder).where(
                CommercialOrder.organization_id == organization_id,
                CommercialOrder.facility_id == facility_id,
            ).order_by(CommercialOrder.created_at.desc())))
            order_by_id = {row.id: row for row in orders}
            lines = list(session.scalars(select(CommercialOrderLine).where(
                CommercialOrderLine.organization_id == organization_id,
                CommercialOrderLine.commercial_order_id.in_([row.id for row in orders] or ["__none__"]),
            )))
            order_value: dict[str, float] = {}
            for line in lines:
                order_value[line.commercial_order_id] = order_value.get(line.commercial_order_id, 0.0) + float(line.quantity or 0) * float(line.unit_price or 0)

            invoices = list(session.scalars(select(CommercialInvoice).where(
                CommercialInvoice.organization_id == organization_id,
                CommercialInvoice.facility_id == facility_id,
            ).order_by(CommercialInvoice.issue_date.desc(), CommercialInvoice.invoice_number.desc())))
            invoice_by_id = {row.id: row for row in invoices}
            payments = list(session.scalars(select(CommercialPayment).where(
                CommercialPayment.organization_id == organization_id,
                CommercialPayment.facility_id == facility_id,
            ).order_by(CommercialPayment.payment_date.desc(), CommercialPayment.recorded_at.desc()).limit(100)))
            links = list(session.scalars(select(AccountingSyncLink).where(
                AccountingSyncLink.provider == "quickbooks",
                AccountingSyncLink.organization_id == organization_id,
                AccountingSyncLink.facility_id == facility_id,
            )))
            link_by_key = {(row.entity_type, row.internal_id): row for row in links}

        invoice_rows = []
        for invoice in invoices:
            order = order_by_id.get(invoice.commercial_order_id)
            partner = partner_by_id.get(invoice.partner_id)
            link = link_by_key.get(("invoice", invoice.id))
            invoice_rows.append({
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "customer": getattr(partner, "name", "Unknown customer"),
                "order_number": getattr(order, "order_number", ""),
                "status": invoice.status,
                "issue_date": invoice.issue_date,
                "due_date": invoice.due_date,
                "total_usd": float(invoice.total_usd or 0),
                "balance_usd": float(invoice.balance_usd or 0),
                "qbo_link_status": link.status if link else "not_linked",
                "qbo_id": link.external_id if link else "",
                "last_synced_at": link.last_synced_at if link else None,
            })

        payment_rows = []
        for payment in payments:
            invoice = invoice_by_id.get(payment.invoice_id)
            partner = partner_by_id.get(invoice.partner_id) if invoice else None
            payment_rows.append({
                "id": payment.id,
                "invoice_number": getattr(invoice, "invoice_number", "Unknown invoice"),
                "customer": getattr(partner, "name", "Unknown customer"),
                "amount_usd": float(payment.amount_usd or 0),
                "payment_date": payment.payment_date,
                "method": payment.method,
                "reference": payment.reference,
                "recorded_by": payment.recorded_by,
            })

        sales_orders = []
        for order in orders:
            if order.order_type != "sales" or order.status == "cancelled":
                continue
            partner = partner_by_id.get(order.partner_id)
            sales_orders.append({
                "id": order.id,
                "order_number": order.order_number,
                "customer": getattr(partner, "name", "Unknown customer"),
                "status": order.status,
                "payment_status": order.payment_status,
                "order_total": order_value.get(order.id, 0.0),
                "due_at": order.due_at,
            })

        qbo_link_counts = Counter(row.entity_type for row in links if row.status == "synced")
        payment_status_counts = Counter(row["payment_status"] for row in sales_orders)
        overdue_ar = sum(float(ar["buckets"].get(key, 0.0)) for key in ("1_30", "31_60", "61_90", "90_plus"))
        cutoff = date.today() - timedelta(days=30)
        payments_30d = sum(row["amount_usd"] for row in payment_rows if row["payment_date"] >= cutoff)

        return {
            "read_only": True,
            "summary": {
                "total_ar": float(ar["total_ar"]),
                "current_ar": float(ar["buckets"].get("current", 0.0)),
                "overdue_ar": overdue_ar,
                "open_invoice_count": sum(row["status"] not in {"paid", "void"} for row in invoice_rows),
                "payments_30d": payments_30d,
                "open_sales_order_value": sum(row["order_total"] for row in sales_orders if row["status"] not in {"fulfilled", "cancelled"}),
                "qbo_connected": bool(qbo_purchasing["connected"]),
                "qbo_attention_count": int(qbo_purchasing["summary"]["attention_count"]),
            },
            "ar": ar,
            "invoices": invoice_rows,
            "recent_payments": payment_rows,
            "sales_orders": sales_orders,
            "sales_payment_status_counts": dict(payment_status_counts),
            "quickbooks": {
                "connected": bool(qbo_purchasing["connected"]),
                "linked_entities": dict(qbo_link_counts),
                "purchasing_reconciliation": qbo_purchasing,
                "message": "QuickBooks status shown here is durable local synchronization metadata. It does not claim a fresh remote-provider readback.",
            },
        }
