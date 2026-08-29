"""Deterministic Doobie Agent intelligence for wholesale/customer storefront operations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine

from modules.commercial.repository import CommercialRepository
from modules.traceability.backoffice import TraceabilityBackofficeRepository

from .wholesale_service import WholesaleCommerceStorefrontService


class StorefrontWholesaleIntelligenceService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.storefront = WholesaleCommerceStorefrontService(engine)

    def snapshot(self, organization_id: str, facility_id: str) -> dict[str, Any]:
        admin = self.storefront.admin_snapshot(organization_id, facility_id)
        requests = admin.get("pending_orders", [])
        submitted = [row for row in requests if row.get("status") == "submitted"]
        approved = [row for row in requests if row.get("status") == "approved"]
        rejected = [row for row in requests if row.get("status") == "rejected"]
        listings = {row["product_id"]: row for row in admin.get("products", [])}
        catalog = self.storefront.list_catalog_options(organization_id, facility_id)
        by_product = {row["product_id"]: row for row in catalog}

        low_stock = []
        for row in catalog:
            rule = listings.get(row["product_id"], {})
            floor = max(float(rule.get("minimum_quantity") or 1) * 2, float(rule.get("case_quantity") or 1) * 2)
            if row.get("orderable") and float(row.get("available") or 0) <= floor:
                low_stock.append({"product_id": row["product_id"], "name": row["name"], "available": row["available"], "unit": row["unit"], "reorder_attention_below": floor})
        low_stock.sort(key=lambda row: float(row["available"]))

        terpene_rank = []
        for row in catalog:
            maximum = ((row.get("lab_stats") or {}).get("terpenes") or {}).get("maximum")
            if maximum is not None:
                terpene_rank.append({"product_id": row["product_id"], "name": row["name"], "terpenes_percent": float(maximum), "available": row["available"], "unit": row["unit"]})
        terpene_rank.sort(key=lambda row: row["terpenes_percent"], reverse=True)

        blocked_orders = []
        for request in submitted:
            reasons: list[str] = []
            if not str(request.get("buyer_license") or "").strip():
                reasons.append("customer license number is missing")
            for line in request.get("lines", []):
                current = by_product.get(line.get("product_id"))
                if not current or not current.get("orderable"):
                    reasons.append(f"{line.get('name') or 'product'} is not currently orderable")
                elif float(line.get("quantity") or 0) > float(current.get("available") or 0):
                    reasons.append(f"{line.get('name') or 'product'} exceeds current sellable inventory")
            blocked_orders.append({"request_id": request["id"], "buyer_company": request["buyer_company"], "reasons": sorted(set(reasons)), "ready_for_review": not reasons})

        transactions = TraceabilityBackofficeRepository(self.engine).list_transactions(organization_id, facility_id, limit=1000)
        manifest_transactions = [row for row in transactions if str(row.operation_type or "").casefold() == "transfer_template_create"]
        manifest_awaiting_verification = [row for row in manifest_transactions if row.status in {"queued", "submitted", "accepted"}]
        manifest_reconciliation = [row for row in manifest_transactions if row.status in {"rejected", "reconciliation_required"}]

        orders = CommercialRepository(self.engine).list_orders(organization_id, facility_id)
        ready_orders = [row for row in orders if row.order_type == "sales" and row.status in {"confirmed", "allocated", "partially_fulfilled"}]

        return {
            "summary": {
                "awaiting_customer_order_approval": len(submitted),
                "approved_storefront_orders": len(approved),
                "rejected_storefront_orders": len(rejected),
                "operational_sales_orders_open": len(ready_orders),
                "low_stock_products": len(low_stock),
                "manifests_awaiting_verification": len(manifest_awaiting_verification),
                "manifest_reconciliation_required": len(manifest_reconciliation),
            },
            "orders_needing_approval": submitted[:20],
            "order_blockers": blocked_orders[:20],
            "low_stock": low_stock[:20],
            "strongest_terpene_products": terpene_rank[:20],
            "manifests_awaiting_verification": [{"transaction_id": row.id, "entity_id": row.entity_id, "status": row.status, "external_reference": row.external_reference} for row in manifest_awaiting_verification[:20]],
            "manifest_reconciliation": [{"transaction_id": row.id, "entity_id": row.entity_id, "status": row.status, "error_message": row.error_message} for row in manifest_reconciliation[:20]],
            "operational_sales_orders": [{"order_id": row.id, "order_number": row.order_number, "status": row.status, "due_at": row.due_at} for row in ready_orders[:20]],
        }

    def answer(self, organization_id: str, facility_id: str, question: str) -> dict[str, Any]:
        data = self.snapshot(organization_id, facility_id)
        q = str(question or "").strip().casefold()
        if not q:
            return {"answer": "Choose a wholesale question to inspect current operational data.", "kind": "summary", "data": data["summary"]}
        if "approval" in q or "waiting on me" in q or "customer order" in q:
            rows = data["orders_needing_approval"]
            return {"answer": f"{len(rows)} storefront order request(s) are waiting for employee review.", "kind": "orders_needing_approval", "data": rows}
        if "stopping" in q or "block" in q or "ship" in q:
            blocked = [row for row in data["order_blockers"] if row["reasons"]]
            ready = data["operational_sales_orders"]
            return {"answer": f"{len(ready)} sales order(s) are operationally open for fulfillment; {len(blocked)} submitted storefront request(s) have a deterministic blocker. Regulatory manifest readiness remains a separate controlled check.", "kind": "shipping_readiness", "data": {"ready_orders": ready, "blocked_requests": blocked}}
        if "low" in q or "inventory" in q:
            rows = data["low_stock"]
            return {"answer": f"{len(rows)} listed product(s) are at or below two minimum/case increments of sellable inventory.", "kind": "low_stock", "data": rows}
        if "terp" in q or "strongest" in q:
            rows = data["strongest_terpene_products"]
            top = rows[0] if rows else None
            answer = f"{top['name']} currently has the strongest verified sellable-batch terpene result at up to {top['terpenes_percent']:g}%." if top else "No sellable passed-COA batch currently exposes a verified total-terpene value."
            return {"answer": answer, "kind": "terpenes", "data": rows}
        if "manifest" in q or "metrc" in q or "verification" in q:
            waiting = data["manifests_awaiting_verification"]
            recon = data["manifest_reconciliation"]
            return {"answer": f"{len(waiting)} manifest transaction(s) are awaiting provider verification and {len(recon)} require reconciliation.", "kind": "manifest_verification", "data": {"awaiting_verification": waiting, "reconciliation_required": recon}}
        return {"answer": "I can deterministically review customer approvals, shipping blockers, low inventory, verified terpene strength, and manifest verification state from Wholesale Ops.", "kind": "summary", "data": data["summary"]}
