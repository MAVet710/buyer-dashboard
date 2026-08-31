"""QuickBooks Online purchasing synchronization and local reconciliation.

This extends the existing accounting-link ledger rather than creating another
sync engine. DoobieLogic commercial records remain the operational source of
truth; QuickBooks IDs and SyncTokens are external accounting metadata.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.coman.models import CommercialOrder, CommercialOrderLine, Product, TradePartner
from modules.integrations.accounting_links import AccountingSyncLink
from services.quickbooks_client import QuickBooksError, quickbooks_api_request
from services.quickbooks_sync import QuickBooksSyncError, QuickBooksSyncService, _json_hash, _qbo_row


class QuickBooksPurchasingSyncService(QuickBooksSyncService):
    @staticmethod
    def _vendor_payload(partner: TradePartner) -> dict[str, Any]:
        payload: dict[str, Any] = {"DisplayName": partner.name, "CompanyName": partner.name}
        if partner.contact_email:
            payload["PrimaryEmailAddr"] = {"Address": partner.contact_email}
        if partner.contact_phone:
            payload["PrimaryPhone"] = {"FreeFormNumber": partner.contact_phone}
        if partner.license_or_registration:
            payload["Notes"] = f"Cannabis license/registration: {partner.license_or_registration}"
        return payload

    def sync_vendor(self, *, organization_id: str, facility_id: str, partner_id: str, actor: str) -> dict[str, Any]:
        access_token, config = self._connection(organization_id, facility_id, actor)
        with Session(self.engine) as session:
            partner = session.get(TradePartner, partner_id)
            if partner is None or partner.organization_id != organization_id or partner.partner_type not in {"vendor", "both"}:
                raise QuickBooksSyncError("A vendor trade partner is required for QuickBooks vendor sync.")
            source_payload = self._vendor_payload(partner)
            payload_hash = _json_hash(source_payload)
            link = self._find_link(session, organization_id, facility_id, "vendor", partner.id)
            if link is not None and link.payload_hash == payload_hash:
                return {"ok": True, "skipped": True, "local_id": partner.id, "qbo_id": link.external_id, "entity": "vendor"}
            request_payload = dict(source_payload)
            if link is not None:
                request_payload.update({"Id": link.external_id, "SyncToken": link.sync_token, "sparse": True})
        try:
            response = quickbooks_api_request(
                access_token=access_token,
                realm_id=str(config.get("realm_id") or ""),
                environment=str(config.get("environment") or "sandbox"),
                entity="vendor",
                payload=request_payload,
                api_base_url=str(config.get("api_base_url") or ""),
            )
        except QuickBooksError as exc:
            raise QuickBooksSyncError(str(exc)) from exc
        remote = _qbo_row(response, "Vendor")
        with Session(self.engine) as session, session.begin():
            link = self._upsert_link(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="vendor",
                internal_id=partner_id,
                external_id=str(remote.get("Id")),
                sync_token=str(remote.get("SyncToken") or ""),
                payload_hash=payload_hash,
                actor=actor,
            )
            return {"ok": True, "skipped": False, "local_id": partner_id, "qbo_id": link.external_id, "entity": "vendor"}

    @staticmethod
    def _purchase_order_payload(
        order: CommercialOrder,
        lines: list[CommercialOrderLine],
        vendor_link: AccountingSyncLink,
        item_links: dict[str, AccountingSyncLink],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "VendorRef": {"value": vendor_link.external_id},
            "DocNumber": order.order_number,
            "TxnDate": order.order_date.isoformat(),
            "Line": [
                {
                    "Amount": round(float(line.quantity) * float(line.unit_price), 2),
                    "DetailType": "ItemBasedExpenseLineDetail",
                    "Description": line.description,
                    "ItemBasedExpenseLineDetail": {
                        "ItemRef": {"value": item_links[line.product_id].external_id},
                        "Qty": float(line.quantity),
                        "UnitPrice": float(line.unit_price),
                    },
                }
                for line in lines
            ],
        }
        notes = " · ".join(value for value in (order.external_reference.strip(), order.notes.strip()) if value)
        if notes:
            payload["PrivateNote"] = notes[:4000]
        return payload

    def _purchase_order_state(
        self,
        session: Session,
        *,
        organization_id: str,
        facility_id: str,
        order_id: str,
    ) -> tuple[CommercialOrder, list[CommercialOrderLine], AccountingSyncLink, dict[str, AccountingSyncLink], dict[str, Any]]:
        order = session.get(CommercialOrder, order_id)
        if order is None or order.organization_id != organization_id or order.facility_id != facility_id or order.order_type != "purchase":
            raise QuickBooksSyncError("Purchase order was not found in the active facility.")
        if order.status not in {"confirmed", "fulfilled"}:
            raise QuickBooksSyncError("Confirm the purchase order in DoobieLogic before synchronizing it to QuickBooks.")
        lines = list(session.scalars(select(CommercialOrderLine).where(
            CommercialOrderLine.organization_id == organization_id,
            CommercialOrderLine.commercial_order_id == order.id,
        ).order_by(CommercialOrderLine.position)))
        if not lines:
            raise QuickBooksSyncError("Purchase order has no lines to synchronize.")
        vendor_link = self._find_link(session, organization_id, facility_id, "vendor", order.partner_id)
        if vendor_link is None:
            raise QuickBooksSyncError("Synchronize the purchase-order vendor to QuickBooks before posting this purchase order.")
        item_links: dict[str, AccountingSyncLink] = {}
        missing_products: list[str] = []
        for line in lines:
            link = self._find_link(session, organization_id, facility_id, "item", line.product_id)
            if link is None:
                product = session.get(Product, line.product_id)
                missing_products.append(product.sku if product and product.sku else line.product_id)
            else:
                item_links[line.product_id] = link
        if missing_products:
            raise QuickBooksSyncError("QuickBooks Item mapping is required before purchase-order sync for: " + ", ".join(sorted(set(missing_products))))
        payload = self._purchase_order_payload(order, lines, vendor_link, item_links)
        return order, lines, vendor_link, item_links, payload

    def sync_purchase_order(self, *, organization_id: str, facility_id: str, order_id: str, actor: str) -> dict[str, Any]:
        access_token, config = self._connection(organization_id, facility_id, actor)
        with Session(self.engine) as session:
            order, _lines, _vendor_link, _item_links, source_payload = self._purchase_order_state(
                session, organization_id=organization_id, facility_id=facility_id, order_id=order_id
            )
            payload_hash = _json_hash(source_payload)
            link = self._find_link(session, organization_id, facility_id, "purchase_order", order.id)
            if link is not None and link.payload_hash == payload_hash:
                return {"ok": True, "skipped": True, "local_id": order.id, "qbo_id": link.external_id, "entity": "purchase_order"}
            request_payload = dict(source_payload)
            if link is not None:
                request_payload.update({"Id": link.external_id, "SyncToken": link.sync_token})
        try:
            response = quickbooks_api_request(
                access_token=access_token,
                realm_id=str(config.get("realm_id") or ""),
                environment=str(config.get("environment") or "sandbox"),
                entity="purchaseorder",
                payload=request_payload,
                api_base_url=str(config.get("api_base_url") or ""),
            )
        except QuickBooksError as exc:
            raise QuickBooksSyncError(str(exc)) from exc
        remote = _qbo_row(response, "PurchaseOrder")
        with Session(self.engine) as session, session.begin():
            link = self._upsert_link(
                session,
                organization_id=organization_id,
                facility_id=facility_id,
                entity_type="purchase_order",
                internal_id=order_id,
                external_id=str(remote.get("Id")),
                sync_token=str(remote.get("SyncToken") or ""),
                payload_hash=payload_hash,
                actor=actor,
            )
            return {"ok": True, "skipped": False, "local_id": order_id, "qbo_id": link.external_id, "entity": "purchase_order"}

    def reconciliation_snapshot(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        integration = self.integrations.get("facility", facility_id, "quickbooks")
        connected = bool(integration is not None and integration.organization_id == organization_id and integration.facility_id == facility_id and integration.status == "connected")
        with Session(self.engine) as session:
            links = list(session.scalars(select(AccountingSyncLink).where(
                AccountingSyncLink.provider == "quickbooks",
                AccountingSyncLink.organization_id == organization_id,
                AccountingSyncLink.facility_id == facility_id,
            )))
            by_key = {(row.entity_type, row.internal_id): row for row in links}
            vendors = list(session.scalars(select(TradePartner).where(
                TradePartner.organization_id == organization_id,
                TradePartner.active.is_(True),
                TradePartner.partner_type.in_(["vendor", "both"]),
            ).order_by(TradePartner.name)))
            orders = list(session.scalars(select(CommercialOrder).where(
                CommercialOrder.organization_id == organization_id,
                CommercialOrder.facility_id == facility_id,
                CommercialOrder.order_type == "purchase",
                CommercialOrder.status != "cancelled",
            ).order_by(CommercialOrder.order_date.desc(), CommercialOrder.order_number)))

            vendor_rows: list[dict[str, Any]] = []
            for partner in vendors:
                link = by_key.get(("vendor", partner.id))
                current_hash = _json_hash(self._vendor_payload(partner))
                status = "never_synced" if link is None else "synced" if link.payload_hash == current_hash else "local_changes_pending"
                vendor_rows.append({"partner_id": partner.id, "name": partner.name, "status": status, "qbo_id": link.external_id if link else "", "last_synced_at": link.last_synced_at if link else None})

            po_rows: list[dict[str, Any]] = []
            for order in orders:
                lines = list(session.scalars(select(CommercialOrderLine).where(
                    CommercialOrderLine.organization_id == organization_id,
                    CommercialOrderLine.commercial_order_id == order.id,
                ).order_by(CommercialOrderLine.position)))
                vendor_link = by_key.get(("vendor", order.partner_id))
                missing_item_ids = [line.product_id for line in lines if ("item", line.product_id) not in by_key]
                link = by_key.get(("purchase_order", order.id))
                if order.status not in {"confirmed", "fulfilled"}:
                    status = "awaiting_confirmation"
                elif vendor_link is None:
                    status = "blocked_vendor_mapping"
                elif missing_item_ids:
                    status = "blocked_item_mapping"
                else:
                    item_links = {line.product_id: by_key[("item", line.product_id)] for line in lines}
                    current_hash = _json_hash(self._purchase_order_payload(order, lines, vendor_link, item_links))
                    status = "never_synced" if link is None else "synced" if link.payload_hash == current_hash else "local_changes_pending"
                po_rows.append({
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "order_status": order.status,
                    "sync_status": status,
                    "qbo_id": link.external_id if link else "",
                    "missing_item_mappings": len(missing_item_ids),
                    "last_synced_at": link.last_synced_at if link else None,
                })

        attention = sum(row["status"] != "synced" for row in vendor_rows) + sum(row["sync_status"] != "synced" for row in po_rows)
        return {
            "provider": "quickbooks",
            "facility_id": facility_id,
            "connected": connected,
            "read_only": True,
            "summary": {
                "vendor_count": len(vendor_rows),
                "purchase_order_count": len(po_rows),
                "synced_vendor_count": sum(row["status"] == "synced" for row in vendor_rows),
                "synced_purchase_order_count": sum(row["sync_status"] == "synced" for row in po_rows),
                "attention_count": attention,
            },
            "vendors": vendor_rows,
            "purchase_orders": po_rows,
            "message": "Local QuickBooks reconciliation compares current DoobieLogic records with the last successfully synchronized payload. It does not claim remote provider verification.",
        }
