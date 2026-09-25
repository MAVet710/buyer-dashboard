"""Idempotent CommercialPayment -> QuickBooks Online Payment synchronization.

A local payment must already belong to a canonical DoobieLogic invoice. The
invoice and customer must both have explicit QBO identity links before a Payment
can be posted. Nothing in this service records or changes the local payment;
it only mirrors an already-recorded accounting fact into the configured QBO
company and stores the resulting provider identity in AccountingSyncLink.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from modules.commercial_finance.models import CommercialInvoice, CommercialPayment
from services.quickbooks_client import QuickBooksError, quickbooks_api_request
from services.quickbooks_sync import QuickBooksSyncError, QuickBooksSyncService, _json_hash, _qbo_row


class QuickBooksPaymentSyncService(QuickBooksSyncService):
    @staticmethod
    def _payment_type(method: str) -> str:
        clean = str(method or "").strip().casefold()
        if clean == "cash":
            return "Cash"
        if clean in {"check", "cheque"}:
            return "Check"
        if clean in {"credit_card", "credit card", "card", "debit", "debit_card", "debit card"}:
            return "CreditCard"
        return "Other"

    def sync_payment(self, *, organization_id: str, facility_id: str, payment_id: str, actor: str) -> dict[str, Any]:
        access_token, config = self._connection(organization_id, facility_id, actor)
        with Session(self.engine) as session:
            payment = session.get(CommercialPayment, payment_id)
            if payment is None or payment.organization_id != organization_id or payment.facility_id != facility_id:
                raise QuickBooksSyncError("Payment was not found in the active facility.")
            invoice = session.get(CommercialInvoice, payment.invoice_id)
            if invoice is None or invoice.organization_id != organization_id or invoice.facility_id != facility_id:
                raise QuickBooksSyncError("The payment invoice was not found in the active facility.")
            if invoice.status == "void":
                raise QuickBooksSyncError("A payment cannot be synchronized against a void invoice.")
            if str(invoice.currency or "USD").upper() != "USD":
                raise QuickBooksSyncError("QuickBooks payment sync currently requires a USD invoice; no currency conversion is inferred.")
            if float(payment.amount_usd) <= 0 or float(payment.amount_usd) > float(invoice.total_usd):
                raise QuickBooksSyncError("The recorded payment amount is outside the canonical invoice total.")

            invoice_link = self._find_link(session, organization_id, facility_id, "invoice", invoice.id)
            if invoice_link is None:
                raise QuickBooksSyncError("Synchronize the invoice to QuickBooks before posting this payment.")
            customer_link = self._find_link(session, organization_id, facility_id, "customer", invoice.partner_id)
            if customer_link is None:
                raise QuickBooksSyncError("Synchronize the invoice customer to QuickBooks before posting this payment.")

            source_payload: dict[str, Any] = {
                "CustomerRef": {"value": customer_link.external_id},
                "TxnDate": payment.payment_date.isoformat(),
                "PaymentType": self._payment_type(payment.method),
                "Line": [{"Amount": round(float(payment.amount_usd), 2), "LinkedTxn": [{"TxnId": invoice_link.external_id, "TxnType": "Invoice"}]}],
            }
            if str(payment.reference or "").strip():
                source_payload["PaymentRefNum"] = str(payment.reference).strip()[:21]
            if str(payment.notes or "").strip():
                source_payload["PrivateNote"] = str(payment.notes).strip()[:4000]

            payload_hash = _json_hash(source_payload)
            payment_link = self._find_link(session, organization_id, facility_id, "payment", payment.id)
            if payment_link is not None and payment_link.payload_hash == payload_hash:
                return {"ok": True, "skipped": True, "local_id": payment.id, "qbo_id": payment_link.external_id, "entity": "payment", "invoice_id": invoice.id, "qbo_invoice_id": invoice_link.external_id}
            if payment_link is not None:
                raise QuickBooksSyncError("This recorded payment already has a QuickBooks identity but its local accounting facts changed. Automatic Payment mutation is blocked; reconcile the existing QBO payment explicitly.")

        try:
            response = quickbooks_api_request(
                access_token=access_token,
                realm_id=str(config.get("realm_id") or ""),
                environment=str(config.get("environment") or "sandbox"),
                entity="payment",
                payload=source_payload,
                api_base_url=str(config.get("api_base_url") or ""),
            )
        except QuickBooksError as exc:
            raise QuickBooksSyncError(str(exc)) from exc
        remote = _qbo_row(response, "Payment")

        with Session(self.engine) as session, session.begin():
            current = session.get(CommercialPayment, payment_id)
            if current is None or current.organization_id != organization_id or current.facility_id != facility_id:
                raise QuickBooksSyncError("Payment disappeared before QuickBooks identity could be recorded; reconciliation is required.")
            existing = self._find_link(session, organization_id, facility_id, "payment", payment_id)
            if existing is not None:
                if existing.external_id == str(remote.get("Id")) and existing.payload_hash == payload_hash:
                    return {"ok": True, "skipped": True, "local_id": payment_id, "qbo_id": existing.external_id, "entity": "payment", "invoice_id": current.invoice_id, "qbo_invoice_id": invoice_link.external_id}
                raise QuickBooksSyncError("Payment acquired a different QuickBooks mapping while the provider request was in flight; reconciliation is required.")
            link = self._upsert_link(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="payment",
                internal_id=payment_id,
                external_id=str(remote.get("Id")),
                sync_token=str(remote.get("SyncToken") or ""),
                payload_hash=payload_hash,
                actor=actor,
            )
            return {"ok": True, "skipped": False, "local_id": payment_id, "qbo_id": link.external_id, "entity": "payment", "invoice_id": current.invoice_id, "qbo_invoice_id": invoice_link.external_id}
