"""Idempotent DoobieLogic -> QuickBooks Online accounting synchronization.

Only explicit business mappings are supported. Customers can be created/updated
from TradePartner records. Invoices require an existing customer link and an
explicit QuickBooks Item link for every local product before anything is posted.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import Product, TradePartner, utc_now
from modules.commercial_finance.models import CommercialInvoice, CommercialInvoiceLine
from modules.integrations import IntegrationConfigurationService
from modules.integrations.accounting_links import QuickBooksEntityLink
from services.quickbooks_client import QuickBooksError, quickbooks_api_request, refresh_quickbooks_token


class QuickBooksSyncError(RuntimeError):
    pass


def _json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _secret_json(service: IntegrationConfigurationService, row) -> dict[str, str]:
    try:
        parsed = json.loads(service.secret(row) or "{}")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise QuickBooksSyncError("Stored QuickBooks credentials are unreadable.") from exc
    if not isinstance(parsed, dict):
        raise QuickBooksSyncError("Stored QuickBooks credentials are unreadable.")
    return {str(key): str(value) for key, value in parsed.items()}


def _qbo_row(payload: dict[str, Any], entity: str) -> dict[str, Any]:
    row = payload.get(entity)
    if not isinstance(row, dict) or not str(row.get("Id") or "").strip():
        raise QuickBooksSyncError(f"QuickBooks did not return a valid {entity} record.")
    return row


class QuickBooksSyncService:
    def __init__(self, engine: Engine, encryption_key: str):
        self.engine = engine
        self.integrations = IntegrationConfigurationService(engine, encryption_key)

    def _connection(self, organization_id: str, facility_id: str, actor: str):
        row = self.integrations.get("facility", facility_id, "quickbooks")
        if row is None or row.organization_id != organization_id or row.facility_id != facility_id:
            raise QuickBooksSyncError("QuickBooks is not configured for the active facility.")
        if row.status != "connected":
            raise QuickBooksSyncError("Validate the QuickBooks connection before synchronizing accounting records.")
        config = self.integrations.public(row).get("configuration", {})
        secrets = _secret_json(self.integrations, row)
        missing = [key for key in ("client_id", "client_secret", "refresh_token") if not secrets.get(key)]
        if missing:
            raise QuickBooksSyncError("QuickBooks OAuth credentials are incomplete.")
        try:
            token = refresh_quickbooks_token(
                client_id=secrets["client_id"],
                client_secret=secrets["client_secret"],
                refresh_token=secrets["refresh_token"],
                token_url=str(config.get("token_url") or "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"),
            )
        except QuickBooksError as exc:
            raise QuickBooksSyncError(str(exc)) from exc
        if token.refresh_token and token.refresh_token != secrets.get("refresh_token"):
            secrets["refresh_token"] = token.refresh_token
            saved = self.integrations.save(
                scope_type="facility",
                scope_key=facility_id,
                provider="quickbooks",
                organization_id=organization_id,
                facility_id=facility_id,
                configuration=dict(config),
                secret=json.dumps(secrets, sort_keys=True),
                actor=actor,
            )
            self.integrations.validation_result(saved.id, ok=True)
        return token.access_token, config

    @staticmethod
    def _find_link(
        session: Session,
        organization_id: str,
        facility_id: str,
        local_entity_type: str,
        local_entity_id: str,
        qbo_entity_type: str,
    ) -> QuickBooksEntityLink | None:
        return session.scalar(
            select(QuickBooksEntityLink).where(
                QuickBooksEntityLink.organization_id == organization_id,
                QuickBooksEntityLink.facility_id == facility_id,
                QuickBooksEntityLink.local_entity_type == local_entity_type,
                QuickBooksEntityLink.local_entity_id == local_entity_id,
                QuickBooksEntityLink.qbo_entity_type == qbo_entity_type,
            )
        )

    @staticmethod
    def _upsert_link(
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        local_entity_type: str,
        local_entity_id: str,
        qbo_entity_type: str,
        qbo_entity_id: str,
        sync_token: str = "",
        payload_hash: str = "",
    ) -> QuickBooksEntityLink:
        existing_remote = session.scalar(
            select(QuickBooksEntityLink).where(
                QuickBooksEntityLink.organization_id == organization_id,
                QuickBooksEntityLink.facility_id == facility_id,
                QuickBooksEntityLink.qbo_entity_type == qbo_entity_type,
                QuickBooksEntityLink.qbo_entity_id == qbo_entity_id,
            )
        )
        row = QuickBooksSyncService._find_link(
            session,
            organization_id,
            facility_id,
            local_entity_type,
            local_entity_id,
            qbo_entity_type,
        )
        if existing_remote is not None and (row is None or existing_remote.id != row.id):
            raise QuickBooksSyncError("That QuickBooks record is already mapped to a different DoobieLogic record.")
        if row is None:
            row = QuickBooksEntityLink(
                organization_id=organization_id,
                facility_id=facility_id,
                local_entity_type=local_entity_type,
                local_entity_id=local_entity_id,
                qbo_entity_type=qbo_entity_type,
                qbo_entity_id=qbo_entity_id,
            )
            session.add(row)
        row.qbo_entity_id = qbo_entity_id
        row.sync_token = str(sync_token or "")
        row.payload_hash = str(payload_hash or "")
        row.last_synced_at = utc_now()
        row.last_error = ""
        session.flush()
        return row

    def list_links(self, organization_id: str, facility_id: str) -> list[QuickBooksEntityLink]:
        with Session(self.engine) as session:
            return list(
                session.scalars(
                    select(QuickBooksEntityLink)
                    .where(
                        QuickBooksEntityLink.organization_id == organization_id,
                        QuickBooksEntityLink.facility_id == facility_id,
                    )
                    .order_by(QuickBooksEntityLink.local_entity_type, QuickBooksEntityLink.local_entity_id)
                )
            )

    def map_product_item(
        self,
        *,
        organization_id: str,
        facility_id: str,
        product_id: str,
        qbo_item_id: str,
        sync_token: str = "",
    ) -> QuickBooksEntityLink:
        qbo_item_id = str(qbo_item_id or "").strip()
        if not qbo_item_id:
            raise QuickBooksSyncError("A QuickBooks Item ID is required.")
        with Session(self.engine) as session, session.begin():
            product = session.get(Product, product_id)
            if product is None or product.organization_id != organization_id:
                raise QuickBooksSyncError("Product was not found in the active organization.")
            return self._upsert_link(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                local_entity_type="product",
                local_entity_id=product_id,
                qbo_entity_type="item",
                qbo_entity_id=qbo_item_id,
                sync_token=sync_token,
            )

    def sync_customer(
        self,
        *,
        organization_id: str,
        facility_id: str,
        partner_id: str,
        actor: str,
    ) -> dict[str, Any]:
        access_token, config = self._connection(organization_id, facility_id, actor)
        with Session(self.engine) as session:
            partner = session.get(TradePartner, partner_id)
            if partner is None or partner.organization_id != organization_id or partner.partner_type not in {"customer", "both"}:
                raise QuickBooksSyncError("A customer trade partner is required for QuickBooks customer sync.")
            source_payload: dict[str, Any] = {
                "DisplayName": partner.name,
                "CompanyName": partner.name,
            }
            if partner.contact_email:
                source_payload["PrimaryEmailAddr"] = {"Address": partner.contact_email}
            if partner.contact_phone:
                source_payload["PrimaryPhone"] = {"FreeFormNumber": partner.contact_phone}
            if partner.license_or_registration:
                source_payload["Notes"] = f"Cannabis license/registration: {partner.license_or_registration}"
            payload_hash = _json_hash(source_payload)
            link = self._find_link(session, organization_id, facility_id, "partner", partner.id, "customer")
            if link is not None and link.payload_hash == payload_hash:
                return {"ok": True, "skipped": True, "local_id": partner.id, "qbo_id": link.qbo_entity_id, "entity": "customer"}
            request_payload = dict(source_payload)
            if link is not None:
                request_payload.update({"Id": link.qbo_entity_id, "SyncToken": link.sync_token, "sparse": True})
        try:
            response = quickbooks_api_request(
                access_token=access_token,
                realm_id=str(config.get("realm_id") or ""),
                environment=str(config.get("environment") or "sandbox"),
                entity="customer",
                payload=request_payload,
                api_base_url=str(config.get("api_base_url") or ""),
            )
        except QuickBooksError as exc:
            raise QuickBooksSyncError(str(exc)) from exc
        remote = _qbo_row(response, "Customer")
        with Session(self.engine) as session, session.begin():
            link = self._upsert_link(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                local_entity_type="partner",
                local_entity_id=partner_id,
                qbo_entity_type="customer",
                qbo_entity_id=str(remote.get("Id")),
                sync_token=str(remote.get("SyncToken") or ""),
                payload_hash=payload_hash,
            )
            return {"ok": True, "skipped": False, "local_id": partner_id, "qbo_id": link.qbo_entity_id, "entity": "customer"}

    def sync_invoice(
        self,
        *,
        organization_id: str,
        facility_id: str,
        invoice_id: str,
        actor: str,
    ) -> dict[str, Any]:
        access_token, config = self._connection(organization_id, facility_id, actor)
        with Session(self.engine) as session:
            invoice = session.get(CommercialInvoice, invoice_id)
            if invoice is None or invoice.organization_id != organization_id or invoice.facility_id != facility_id:
                raise QuickBooksSyncError("Invoice was not found in the active facility.")
            lines = list(
                session.scalars(
                    select(CommercialInvoiceLine)
                    .where(
                        CommercialInvoiceLine.organization_id == organization_id,
                        CommercialInvoiceLine.invoice_id == invoice.id,
                    )
                    .order_by(CommercialInvoiceLine.position)
                )
            )
            if not lines:
                raise QuickBooksSyncError("Invoice has no lines to synchronize.")
            customer_link = self._find_link(session, organization_id, facility_id, "partner", invoice.partner_id, "customer")
            if customer_link is None:
                raise QuickBooksSyncError("Synchronize the invoice customer to QuickBooks before posting this invoice.")
            item_links: dict[str, QuickBooksEntityLink] = {}
            missing_products: list[str] = []
            for line in lines:
                link = self._find_link(session, organization_id, facility_id, "product", line.product_id, "item")
                if link is None:
                    product = session.get(Product, line.product_id)
                    missing_products.append(product.sku if product and product.sku else line.product_id)
                else:
                    item_links[line.product_id] = link
            if missing_products:
                raise QuickBooksSyncError(
                    "QuickBooks Item mapping is required before invoice sync for: " + ", ".join(sorted(set(missing_products)))
                )
            source_payload: dict[str, Any] = {
                "CustomerRef": {"value": customer_link.qbo_entity_id},
                "DocNumber": invoice.invoice_number,
                "TxnDate": invoice.issue_date.isoformat(),
                "DueDate": invoice.due_date.isoformat(),
                "Line": [
                    {
                        "Amount": round(float(line.line_total_usd), 2),
                        "DetailType": "SalesItemLineDetail",
                        "Description": line.description,
                        "SalesItemLineDetail": {
                            "ItemRef": {"value": item_links[line.product_id].qbo_entity_id},
                            "Qty": float(line.quantity),
                            "UnitPrice": float(line.unit_price_usd),
                        },
                    }
                    for line in lines
                ],
            }
            if invoice.notes:
                source_payload["PrivateNote"] = invoice.notes[:4000]
            payload_hash = _json_hash(source_payload)
            invoice_link = self._find_link(session, organization_id, facility_id, "invoice", invoice.id, "invoice")
            if invoice_link is not None and invoice_link.payload_hash == payload_hash:
                return {"ok": True, "skipped": True, "local_id": invoice.id, "qbo_id": invoice_link.qbo_entity_id, "entity": "invoice"}
            request_payload = dict(source_payload)
            if invoice_link is not None:
                request_payload.update({"Id": invoice_link.qbo_entity_id, "SyncToken": invoice_link.sync_token})
        try:
            response = quickbooks_api_request(
                access_token=access_token,
                realm_id=str(config.get("realm_id") or ""),
                environment=str(config.get("environment") or "sandbox"),
                entity="invoice",
                payload=request_payload,
                api_base_url=str(config.get("api_base_url") or ""),
            )
        except QuickBooksError as exc:
            raise QuickBooksSyncError(str(exc)) from exc
        remote = _qbo_row(response, "Invoice")
        with Session(self.engine) as session, session.begin():
            link = self._upsert_link(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                local_entity_type="invoice",
                local_entity_id=invoice_id,
                qbo_entity_type="invoice",
                qbo_entity_id=str(remote.get("Id")),
                sync_token=str(remote.get("SyncToken") or ""),
                payload_hash=payload_hash,
            )
            return {"ok": True, "skipped": False, "local_id": invoice_id, "qbo_id": link.qbo_entity_id, "entity": "invoice"}
