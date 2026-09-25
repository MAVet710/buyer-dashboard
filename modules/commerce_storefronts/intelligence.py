"""Deterministic Doobie Agent intelligence for wholesale/customer storefront operations."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import json
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from modules.coman.models import InventoryLot, Product
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.models import CommercialInvoice, CommercialShipment
from modules.traceability.backoffice import TraceabilityBackofficeRepository

from .wholesale_service import WholesaleCommerceStorefrontService


_LOW_MARGIN_FLOOR_PCT = 20.0
_ACTIVE_ALLOCATION_STATUSES = {"reserved", "partial"}
_MANIFESTED_SHIPMENT_STATUSES = {"manifested", "shipped", "delivered"}


def _key(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _manifest_order_id(transaction: Any, orders_by_number: dict[str, Any]) -> str:
    try:
        payload = json.loads(str(getattr(transaction, "request_payload_json", "") or "{}"))
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    candidates = [payload]
    nested = payload.get("request_payload")
    if isinstance(nested, dict):
        candidates.append(nested)
    for candidate in candidates:
        value = str(candidate.get("commercial_order_id") or "").strip()
        if value:
            return value
    entity_id = _key(getattr(transaction, "entity_id", ""))
    order = orders_by_number.get(entity_id)
    return str(getattr(order, "id", "") or "")


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

        commercial = CommercialRepository(self.engine)
        orders = commercial.list_orders(organization_id, facility_id)
        ready_orders = [row for row in orders if row.order_type == "sales" and row.status in {"confirmed", "allocated", "partially_fulfilled"}]
        continuity = self._order_to_cash(
            organization_id=organization_id,
            facility_id=facility_id,
            submitted=submitted,
            orders=orders,
            manifest_transactions=manifest_transactions,
        )

        return {
            "summary": {
                "awaiting_customer_order_approval": len(submitted),
                "approved_storefront_orders": len(approved),
                "rejected_storefront_orders": len(rejected),
                "operational_sales_orders_open": len(ready_orders),
                "low_stock_products": len(low_stock),
                "manifests_awaiting_verification": len(manifest_awaiting_verification),
                "manifest_reconciliation_required": len(manifest_reconciliation),
                **continuity["summary"],
            },
            "orders_needing_approval": submitted[:20],
            "order_blockers": blocked_orders[:20],
            "low_stock": low_stock[:20],
            "strongest_terpene_products": terpene_rank[:20],
            "manifests_awaiting_verification": [{"transaction_id": row.id, "entity_id": row.entity_id, "status": row.status, "external_reference": row.external_reference} for row in manifest_awaiting_verification[:20]],
            "manifest_reconciliation": [{"transaction_id": row.id, "entity_id": row.entity_id, "status": row.status, "error_message": row.error_message} for row in manifest_reconciliation[:20]],
            "operational_sales_orders": [{"order_id": row.id, "order_number": row.order_number, "status": row.status, "due_at": row.due_at} for row in ready_orders[:20]],
            "order_to_cash_exceptions": continuity["exceptions"][:50],
            "order_to_cash": continuity,
        }

    def _order_to_cash(
        self,
        *,
        organization_id: str,
        facility_id: str,
        submitted: list[dict[str, Any]],
        orders: list[Any],
        manifest_transactions: list[Any],
    ) -> dict[str, Any]:
        commercial = CommercialRepository(self.engine)
        sales_orders = [row for row in orders if row.order_type == "sales" and row.status != "cancelled"]
        order_ids = {row.id for row in sales_orders}
        orders_by_number = {_key(row.order_number): row for row in sales_orders}
        lines = [row for row in commercial.list_order_lines(organization_id) if row.commercial_order_id in order_ids]
        allocations = commercial.list_allocations(organization_id, facility_id)
        partners = commercial.list_trade_partners(organization_id, active_only=False)
        partner_by_id = {row.id: row for row in partners}
        partner_by_license = {_key(row.license_or_registration): row for row in partners if _key(row.license_or_registration)}
        partner_by_name = {_key(row.name): row for row in partners if _key(row.name)}

        with Session(self.engine) as session:
            products = {row.id: row for row in session.scalars(select(Product).where(Product.organization_id == organization_id))}
            lots = {row.id: row for row in session.scalars(select(InventoryLot).where(InventoryLot.organization_id == organization_id, InventoryLot.facility_id == facility_id))}
            invoices = list(session.scalars(select(CommercialInvoice).where(CommercialInvoice.organization_id == organization_id, CommercialInvoice.facility_id == facility_id)))
            shipments = list(session.scalars(select(CommercialShipment).where(CommercialShipment.organization_id == organization_id, CommercialShipment.facility_id == facility_id)))

        lines_by_order: dict[str, list[Any]] = defaultdict(list)
        for line in lines:
            lines_by_order[line.commercial_order_id].append(line)
        allocations_by_order: dict[str, list[Any]] = defaultdict(list)
        for allocation in allocations:
            if allocation.commercial_order_id in order_ids:
                allocations_by_order[allocation.commercial_order_id].append(allocation)
        invoices_by_order: dict[str, list[Any]] = defaultdict(list)
        for invoice in invoices:
            invoices_by_order[invoice.commercial_order_id].append(invoice)
        shipments_by_order: dict[str, list[Any]] = defaultdict(list)
        for shipment in shipments:
            shipments_by_order[shipment.commercial_order_id].append(shipment)

        manifest_state_by_order: dict[str, str] = {}
        for transaction in manifest_transactions:
            order_id = _manifest_order_id(transaction, orders_by_number)
            if order_id in order_ids:
                manifest_state_by_order[order_id] = str(transaction.status or "")

        open_ar_by_partner: dict[str, float] = defaultdict(float)
        overdue_ar_by_partner: dict[str, float] = defaultdict(float)
        today = date.today()
        for invoice in invoices:
            if invoice.status in {"paid", "void"} or float(invoice.balance_usd or 0) <= 1e-9:
                continue
            balance = float(invoice.balance_usd or 0)
            open_ar_by_partner[invoice.partner_id] += balance
            if invoice.status == "overdue" or invoice.due_date < today:
                overdue_ar_by_partner[invoice.partner_id] += balance

        exceptions: list[dict[str, Any]] = []

        for request in submitted:
            partner = partner_by_id.get(str(request.get("partner_id") or ""))
            if partner is None:
                partner = partner_by_license.get(_key(request.get("buyer_license"))) or partner_by_name.get(_key(request.get("buyer_company")))
            if partner is None:
                continue
            open_ar = open_ar_by_partner.get(partner.id, 0.0)
            overdue_ar = overdue_ar_by_partner.get(partner.id, 0.0)
            if open_ar > 1e-9:
                exceptions.append({
                    "kind": "customer_ar_pending_order",
                    "severity": "high" if overdue_ar > 1e-9 else "warning",
                    "request_id": request.get("id"),
                    "order_id": "",
                    "order_number": "",
                    "customer": request.get("buyer_company") or partner.name,
                    "message": f"New storefront request while this customer has USD {open_ar:,.2f} open A/R" + (f", including USD {overdue_ar:,.2f} overdue." if overdue_ar > 1e-9 else "."),
                    "next_action": "Review customer A/R and payment terms before approving new demand.",
                    "amount_usd": round(open_ar, 2),
                    "overdue_usd": round(overdue_ar, 2),
                })

        for order in sales_orders:
            if order.status not in {"draft", "confirmed", "allocated", "partially_fulfilled"}:
                continue
            order_lines = lines_by_order.get(order.id, [])
            revenue = sum(float(line.quantity or 0) * float(line.unit_price or 0) for line in order_lines)
            estimated_cost = sum(float(line.quantity or 0) * float(getattr(products.get(line.product_id), "unit_cost", 0) or 0) for line in order_lines)
            if revenue > 1e-9 and estimated_cost > 1e-9:
                margin_pct = ((revenue - estimated_cost) / revenue) * 100.0
                if margin_pct < _LOW_MARGIN_FLOOR_PCT:
                    partner = partner_by_id.get(order.partner_id)
                    exceptions.append({
                        "kind": "low_margin_order",
                        "severity": "warning",
                        "order_id": order.id,
                        "order_number": order.order_number,
                        "customer": getattr(partner, "name", "Unknown customer"),
                        "message": f"Estimated gross margin is {margin_pct:.1f}% against a {_LOW_MARGIN_FLOOR_PCT:.0f}% attention floor.",
                        "next_action": "Review pricing, discounts, and current product cost before fulfillment.",
                        "order_value_usd": round(revenue, 2),
                        "estimated_cost_usd": round(estimated_cost, 2),
                        "estimated_gross_margin_pct": round(margin_pct, 2),
                    })

        for order in sales_orders:
            if order.status in {"fulfilled", "cancelled"}:
                continue
            held = []
            for allocation in allocations_by_order.get(order.id, []):
                if str(allocation.status or "").casefold() not in _ACTIVE_ALLOCATION_STATUSES:
                    continue
                if float(allocation.quantity or 0) - float(allocation.fulfilled_quantity or 0) <= 1e-9:
                    continue
                lot = lots.get(allocation.lot_id)
                if lot is not None and str(lot.status or "").casefold() not in {"available", "released"}:
                    held.append(lot)
            if held:
                partner = partner_by_id.get(order.partner_id)
                exceptions.append({
                    "kind": "qa_hold",
                    "severity": "high",
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "customer": getattr(partner, "name", "Unknown customer"),
                    "message": f"{len(held)} allocated lot(s) are no longer released for shipment.",
                    "next_action": "Resolve the QA or inventory hold before warehouse fulfillment.",
                    "lots": [{"lot_id": lot.id, "lot_code": lot.lot_code, "status": lot.status} for lot in held],
                })

        for order in sales_orders:
            if order.status not in {"allocated", "partially_fulfilled"}:
                continue
            order_lines = lines_by_order.get(order.id, [])
            remaining = sum(max(0.0, float(line.quantity or 0) - float(line.fulfilled_quantity or 0)) for line in order_lines)
            if remaining <= 1e-9:
                continue
            active_allocations = [
                row for row in allocations_by_order.get(order.id, [])
                if str(row.status or "").casefold() in _ACTIVE_ALLOCATION_STATUSES
                and float(row.quantity or 0) - float(row.fulfilled_quantity or 0) > 1e-9
            ]
            allocated_remaining = sum(max(0.0, float(row.quantity or 0) - float(row.fulfilled_quantity or 0)) for row in active_allocations)
            regulated = any(str(getattr(lots.get(row.lot_id), "compliance_package_id", "") or "").strip() for row in active_allocations)
            if not regulated or allocated_remaining + 1e-9 < remaining:
                continue
            shipment_ready = any(
                str(row.manifest_reference or "").strip()
                and str(row.status or "").casefold() in _MANIFESTED_SHIPMENT_STATUSES
                for row in shipments_by_order.get(order.id, [])
            )
            if not shipment_ready:
                partner = partner_by_id.get(order.partner_id)
                manifest_state = manifest_state_by_order.get(order.id, "not_started")
                exceptions.append({
                    "kind": "waiting_manifest",
                    "severity": "high",
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "customer": getattr(partner, "name", "Unknown customer"),
                    "message": f"Order is fully allocated with regulated package inventory, but no manifested shipment is attached. Manifest workflow state: {manifest_state}.",
                    "next_action": "Complete manifest verification and attach the manifest reference before shipping.",
                    "manifest_state": manifest_state,
                })

        for order in sales_orders:
            if order.status in {"fulfilled", "cancelled"} or order.due_at is None:
                continue
            if order.due_at.date() < today:
                partner = partner_by_id.get(order.partner_id)
                exceptions.append({
                    "kind": "late_fulfillment",
                    "severity": "high",
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "customer": getattr(partner, "name", "Unknown customer"),
                    "message": f"Order was due {order.due_at.date().isoformat()} and is still {order.status.replace('_', ' ')}.",
                    "next_action": "Review inventory, manifest, and warehouse blockers, then reset the customer commitment if needed.",
                    "due_date": order.due_at.date().isoformat(),
                })

        for order in sales_orders:
            if order.status != "fulfilled":
                continue
            order_invoices = invoices_by_order.get(order.id, [])
            active_receivable = [row for row in order_invoices if row.status not in {"draft", "void"}]
            if not order_invoices or not active_receivable:
                partner = partner_by_id.get(order.partner_id)
                state = "no invoice" if not order_invoices else "draft invoice not sent"
                exceptions.append({
                    "kind": "invoice_ar_handoff",
                    "severity": "high" if not order_invoices else "warning",
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "customer": getattr(partner, "name", "Unknown customer"),
                    "message": f"Fulfillment is complete, but the A/R handoff is incomplete: {state}.",
                    "next_action": "Create or send the customer invoice so the balance enters A/R tracking.",
                    "payment_status": order.payment_status,
                })

        flow_rows: list[dict[str, Any]] = []
        for order in sales_orders:
            order_lines = lines_by_order.get(order.id, [])
            order_allocations = allocations_by_order.get(order.id, [])
            remaining = sum(max(0.0, float(line.quantity or 0) - float(line.fulfilled_quantity or 0)) for line in order_lines)
            revenue = sum(float(line.quantity or 0) * float(line.unit_price or 0) for line in order_lines)
            estimated_cost = sum(float(line.quantity or 0) * float(getattr(products.get(line.product_id), "unit_cost", 0) or 0) for line in order_lines)
            margin_usd = revenue - estimated_cost
            margin_pct = (margin_usd / revenue * 100.0) if revenue > 1e-9 else None
            active_allocations = [
                row for row in order_allocations
                if str(row.status or "").casefold() in _ACTIVE_ALLOCATION_STATUSES
                and float(row.quantity or 0) - float(row.fulfilled_quantity or 0) > 1e-9
            ]
            allocated_remaining = sum(max(0.0, float(row.quantity or 0) - float(row.fulfilled_quantity or 0)) for row in active_allocations)
            regulated = any(str(getattr(lots.get(row.lot_id), "compliance_package_id", "") or "").strip() for row in active_allocations)
            order_shipments = sorted(shipments_by_order.get(order.id, []), key=lambda row: row.created_at, reverse=True)
            latest_shipment = order_shipments[0] if order_shipments else None
            active_invoices = [row for row in invoices_by_order.get(order.id, []) if str(row.status or "").casefold() != "void"]
            active_invoices.sort(key=lambda row: row.created_at, reverse=True)
            latest_invoice = active_invoices[0] if active_invoices else None
            open_balance = sum(max(0.0, float(row.balance_usd or 0)) for row in active_invoices)

            if order.status == "fulfilled":
                if not active_invoices:
                    stage = "invoice_required"
                elif all(str(row.status or "").casefold() == "draft" for row in active_invoices):
                    stage = "invoice_send_required"
                elif open_balance > 1e-9:
                    stage = "ar_open"
                else:
                    stage = "paid"
            elif order.status == "draft":
                stage = "confirmation_required"
            elif remaining > 1e-9 and allocated_remaining + 1e-9 < remaining:
                stage = "allocation_required"
            elif latest_shipment is None:
                stage = "shipment_setup_required"
            else:
                shipment_status = str(latest_shipment.status or "").casefold()
                if shipment_status in {"planned", "picking"}:
                    stage = "pick_pack"
                elif shipment_status == "packed" and regulated:
                    stage = "manifest_required"
                elif shipment_status == "packed":
                    stage = "ready_to_ship"
                elif shipment_status == "manifested":
                    stage = "fulfillment_in_progress" if order.status == "partially_fulfilled" else "ready_to_ship"
                elif shipment_status in {"shipped", "delivered"} and remaining > 1e-9:
                    stage = "fulfillment_reconciliation"
                else:
                    stage = "shipment_setup_required"

            next_action = {
                "confirmation_required": "Confirm the sales order before allocating inventory.",
                "allocation_required": "Reserve released inventory against the remaining order quantity.",
                "shipment_setup_required": "Create the shipment record and begin warehouse picking.",
                "pick_pack": "Complete scan-verified picking and mark the shipment packed.",
                "manifest_required": "Attach the state manifest reference and mark the shipment manifested.",
                "ready_to_ship": "Post the scan-verified inventory shipment.",
                "fulfillment_in_progress": "Finish the remaining scan-verified fulfillment quantity.",
                "fulfillment_reconciliation": "Reconcile shipment status against the remaining inventory fulfillment.",
                "invoice_required": "Create the customer invoice from the fulfilled order.",
                "invoice_send_required": "Send the draft invoice so the balance enters A/R.",
                "ar_open": "Collect or record payment against the open customer balance.",
                "paid": "Order-to-cash is complete.",
            }[stage]
            partner = partner_by_id.get(order.partner_id)
            flow_rows.append({
                "order_id": order.id,
                "order_number": order.order_number,
                "customer": getattr(partner, "name", "Unknown customer"),
                "order_status": order.status,
                "payment_status": order.payment_status,
                "stage": stage,
                "next_action": next_action,
                "order_value_usd": round(revenue, 2),
                "estimated_cost_usd": round(estimated_cost, 2),
                "estimated_gross_margin_usd": round(margin_usd, 2),
                "estimated_gross_margin_pct": round(margin_pct, 2) if margin_pct is not None else None,
                "remaining_quantity": round(remaining, 4),
                "allocated_remaining_quantity": round(allocated_remaining, 4),
                "shipment_id": str(getattr(latest_shipment, "id", "") or ""),
                "shipment_status": str(getattr(latest_shipment, "status", "") or ""),
                "manifest_reference": str(getattr(latest_shipment, "manifest_reference", "") or ""),
                "invoice_id": str(getattr(latest_invoice, "id", "") or ""),
                "invoice_status": str(getattr(latest_invoice, "status", "") or ""),
                "invoice_balance_usd": round(open_balance, 2),
            })

        stage_rank = {
            "confirmation_required": 0,
            "allocation_required": 1,
            "shipment_setup_required": 2,
            "pick_pack": 3,
            "manifest_required": 4,
            "ready_to_ship": 5,
            "fulfillment_in_progress": 6,
            "fulfillment_reconciliation": 7,
            "invoice_required": 8,
            "invoice_send_required": 9,
            "ar_open": 10,
            "paid": 11,
        }
        flow_rows.sort(key=lambda row: (stage_rank.get(str(row["stage"]), 99), str(row["order_number"])))
        stage_counts = Counter(str(row["stage"]) for row in flow_rows)
        severity_rank = {"high": 0, "warning": 1}
        exceptions.sort(key=lambda row: (severity_rank.get(str(row.get("severity")), 9), str(row.get("kind")), str(row.get("order_number") or row.get("request_id") or "")))
        counts = Counter(str(row["kind"]) for row in exceptions)
        return {
            "summary": {
                "order_to_cash_exceptions": len(exceptions),
                "qa_hold_orders": counts["qa_hold"],
                "customer_ar_pending_orders": counts["customer_ar_pending_order"],
                "low_margin_orders": counts["low_margin_order"],
                "orders_waiting_manifest": counts["waiting_manifest"],
                "late_fulfillment_orders": counts["late_fulfillment"],
                "invoice_ar_handoff_orders": counts["invoice_ar_handoff"],
            },
            "exceptions": exceptions,
            "orders": flow_rows,
            "stage_counts": dict(stage_counts),
            "policy": {
                "low_margin_attention_floor_pct": _LOW_MARGIN_FLOOR_PCT,
                "regulated_package_fulfillment_requires_manifested_shipment": True,
                "sales_fulfillment_rechecks_lot_release_status": True,
                "invoice_creation_remains_human_controlled": True,
            },
        }

    def answer(self, organization_id: str, facility_id: str, question: str) -> dict[str, Any]:
        data = self.snapshot(organization_id, facility_id)
        q = str(question or "").strip().casefold()
        exceptions = data["order_to_cash_exceptions"]
        if not q:
            return {"answer": "Choose a wholesale question to inspect current operational data.", "kind": "summary", "data": data["summary"]}
        if "unpaid" in q or "accounts receivable" in q or q == "ar" or "a/r" in q:
            rows = [row for row in exceptions if row["kind"] == "customer_ar_pending_order"]
            return {"answer": f"{len(rows)} new storefront request(s) are tied to customers with open A/R.", "kind": "customer_ar_pending_orders", "data": rows}
        if "margin" in q:
            rows = [row for row in exceptions if row["kind"] == "low_margin_order"]
            return {"answer": f"{len(rows)} open sales order(s) are below the configured gross-margin attention floor.", "kind": "low_margin_orders", "data": rows}
        if "late" in q or "overdue order" in q:
            rows = [row for row in exceptions if row["kind"] == "late_fulfillment"]
            return {"answer": f"{len(rows)} sales order(s) are past their due date and not fulfilled.", "kind": "late_fulfillment", "data": rows}
        if "invoice" in q or "handoff" in q:
            rows = [row for row in exceptions if row["kind"] == "invoice_ar_handoff"]
            return {"answer": f"{len(rows)} fulfilled sales order(s) still need invoice/A/R handoff work.", "kind": "invoice_ar_handoff", "data": rows}
        if "exception" in q or "attention" in q or "order to cash" in q or "order-to-cash" in q:
            return {"answer": f"{len(exceptions)} order-to-cash exception(s) currently need attention.", "kind": "order_to_cash_exceptions", "data": exceptions}
        if "approval" in q or "waiting on me" in q or "customer order" in q:
            rows = data["orders_needing_approval"]
            return {"answer": f"{len(rows)} storefront order request(s) are waiting for employee review.", "kind": "orders_needing_approval", "data": rows}
        if "stopping" in q or "block" in q or "ship" in q:
            blocked = [row for row in data["order_blockers"] if row["reasons"]]
            shipping = [row for row in exceptions if row["kind"] in {"qa_hold", "waiting_manifest", "late_fulfillment"}]
            ready = data["operational_sales_orders"]
            return {"answer": f"{len(ready)} sales order(s) are operationally open; {len(shipping)} order-to-cash shipping exception(s) and {len(blocked)} submitted request blocker(s) need attention.", "kind": "shipping_readiness", "data": {"ready_orders": ready, "shipping_exceptions": shipping, "blocked_requests": blocked}}
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
            order_waiting = [row for row in exceptions if row["kind"] == "waiting_manifest"]
            return {"answer": f"{len(waiting)} manifest transaction(s) await provider verification, {len(recon)} require reconciliation, and {len(order_waiting)} fully allocated order(s) still lack a manifested shipment handoff.", "kind": "manifest_verification", "data": {"awaiting_verification": waiting, "reconciliation_required": recon, "orders_waiting_manifest": order_waiting}}
        return {"answer": "I can deterministically review approvals, order-to-cash exceptions, customer A/R, margin, shipping blockers, low inventory, verified terpene strength, and manifest state from Wholesale Ops.", "kind": "summary", "data": data["summary"]}
