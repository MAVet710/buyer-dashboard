"""Governed, read-only data feeds for the DoobieLogic Wholesale Agent.

This module intentionally projects only operational business fields needed for
wholesale analysis. Customer contact PII, free-text notes, secrets, and mutation
capabilities are never exposed to the model.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from modules.coman.models import Product, TradePartner
from modules.commerce_storefronts.intelligence import StorefrontWholesaleIntelligenceService
from modules.commerce_storefronts.wholesale_service import WholesaleCommerceStorefrontService
from modules.commercial.repository import CommercialRepository
from modules.commercial_finance.models import CommercialInvoice, CustomerPriceRule
from services.ai.datasets import DatasetAccessContext, DatasetRegistry, DatasetSpec, LoadedDataset


WHOLESALE_AGENT = "wholesale"
WHOLESALE_CAPABILITY = ("commercial",)


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _age_days(value: Any) -> int | None:
    if value in (None, ""):
        return None
    moment: datetime | None = None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        moment = datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    else:
        raw = _text(value).replace("Z", "+00:00")
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - moment.astimezone(timezone.utc)).total_seconds() // 86400))


def _margin_pct(price: float, cost: float) -> float | None:
    if price <= 0 or cost < 0:
        return None
    return round(((price - cost) / price) * 100.0, 2)


def _read_ar_rows(engine: Any, organization_id: str, facility_id: str) -> list[dict[str, Any]]:
    """Read A/R without invoking finance service methods that may update status."""
    today = date.today()
    with Session(engine) as session:
        rows = session.execute(
            select(CommercialInvoice, TradePartner)
            .join(TradePartner, TradePartner.id == CommercialInvoice.partner_id)
            .where(
                CommercialInvoice.organization_id == organization_id,
                CommercialInvoice.facility_id == facility_id,
                CommercialInvoice.status.notin_(("paid", "void")),
                TradePartner.organization_id == organization_id,
            )
            .order_by(CommercialInvoice.due_date)
        ).all()
    return [
        {
            "partner_id": invoice.partner_id,
            "customer": partner.name,
            "license_or_registration": partner.license_or_registration,
            "invoice_status": invoice.status,
            "due_date": invoice.due_date,
            "balance_usd": _float(invoice.balance_usd),
            "days_past_due": max(0, (today - invoice.due_date).days),
        }
        for invoice, partner in rows
    ]


def _read_customer_price_rows(engine: Any, organization_id: str) -> list[dict[str, Any]]:
    """Read active customer-specific price rules with business identity only."""
    with Session(engine) as session:
        rows = session.execute(
            select(CustomerPriceRule, TradePartner, Product)
            .join(TradePartner, TradePartner.id == CustomerPriceRule.partner_id)
            .join(Product, Product.id == CustomerPriceRule.product_id)
            .where(
                CustomerPriceRule.organization_id == organization_id,
                CustomerPriceRule.active.is_(True),
                TradePartner.organization_id == organization_id,
                Product.organization_id == organization_id,
                Product.active.is_(True),
            )
        ).all()
    output: list[dict[str, Any]] = []
    for rule, partner, product in rows:
        base_price = _float(product.retail_price)
        explicit_price = _float(rule.price_usd)
        discount_pct = _float(rule.discount_pct)
        effective_price = explicit_price if explicit_price > 0 else max(0.0, base_price * (1.0 - discount_pct / 100.0))
        cost = _float(product.unit_cost)
        output.append({
            "partner_id": partner.id,
            "customer": partner.name,
            "license_or_registration": partner.license_or_registration,
            "product_id": product.id,
            "sku": product.sku,
            "product_name": product.name,
            "unit": product.base_unit,
            "unit_cost": cost,
            "base_price_usd": base_price,
            "explicit_customer_price_usd": explicit_price,
            "discount_pct": discount_pct,
            "effective_customer_price_usd": round(effective_price, 4),
            "customer_gross_margin_pct": _margin_pct(effective_price, cost),
        })
    return output


def load_wholesale_datasets(access: DatasetAccessContext) -> dict[str, LoadedDataset]:
    """Return sanitized wholesale-only datasets for one trusted tenant/facility."""
    if access.engine is None:
        return {}

    registry = DatasetRegistry()
    storefront = WholesaleCommerceStorefrontService(access.engine)
    intelligence = StorefrontWholesaleIntelligenceService(access.engine)
    commercial = CommercialRepository(access.engine)
    cache: dict[str, Any] = {}

    def inventory_snapshot() -> dict[str, Any]:
        if "inventory" not in cache:
            cache["inventory"] = storefront.wholesale_inventory(access.organization_id, access.facility_id)
        return cache["inventory"]

    def catalog_rows() -> list[dict[str, Any]]:
        if "catalog" not in cache:
            cache["catalog"] = storefront.list_catalog_options(access.organization_id, access.facility_id)
        return cache["catalog"]

    def storefront_snapshot() -> dict[str, Any]:
        if "intelligence" not in cache:
            cache["intelligence"] = intelligence.snapshot(access.organization_id, access.facility_id)
        return cache["intelligence"]

    def commercial_rows() -> tuple[list[Any], list[Any], dict[str, Any]]:
        if "commercial" not in cache:
            orders = [row for row in commercial.list_orders(access.organization_id, access.facility_id) if _text(getattr(row, "order_type", "")).casefold() == "sales"]
            order_ids = {row.id for row in orders}
            lines = [row for row in commercial.list_order_lines(access.organization_id) if getattr(row, "commercial_order_id", None) in order_ids]
            partners = {row.id: row for row in commercial.list_trade_partners(access.organization_id) if _text(getattr(row, "partner_type", "")).casefold() in {"customer", "both"}}
            cache["commercial"] = (orders, lines, partners)
        return cache["commercial"]

    def ar_rows() -> list[dict[str, Any]]:
        if "ar" not in cache:
            cache["ar"] = _read_ar_rows(access.engine, access.organization_id, access.facility_id)
        return cache["ar"]

    def customer_price_rows() -> list[dict[str, Any]]:
        if "customer_prices" not in cache:
            cache["customer_prices"] = _read_customer_price_rows(access.engine, access.organization_id)
        return cache["customer_prices"]

    def sellable_inventory(_access: DatasetAccessContext) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for item in inventory_snapshot().get("items") or []:
            price = _float(item.get("suggested_price_usd")); cost = _float(item.get("unit_cost"))
            rows.append({
                "lot_id": item.get("lot_id"), "package_id": item.get("package_id"), "lot_code": item.get("lot_code"), "batch_name": item.get("batch_name"),
                "product_id": item.get("product_id"), "sku": item.get("sku"), "name": item.get("name"), "item_type": item.get("item_type"), "inventory_type": item.get("inventory_type"),
                "usable_quantity": _float(item.get("usable")), "reserved_quantity": _float(item.get("reserved")), "production_reserved_quantity": _float(item.get("production_reserved")),
                "wholesale_reserved_quantity": _float(item.get("wholesale_reserved")), "wholesale_committed_quantity": _float(item.get("wholesale_committed")), "unit": item.get("unit"),
                "location": item.get("location"), "status": item.get("status"), "lab_testing_state": item.get("lab_testing_state"), "coa_reference": item.get("coa_reference"), "coa_url": item.get("coa_url"),
                "thca_percent": item.get("thca_percent"), "tac_percent": item.get("tac_percent"), "terpenes_percent": item.get("terpenes_percent"), "harvested_at": item.get("harvested_at"),
                "produced_at": item.get("produced_at"), "received_at": item.get("received_at"), "expiration_at": item.get("expiration_at"), "age_days": _age_days(item.get("received_at")),
                "unit_cost": cost, "suggested_price_usd": price, "suggested_gross_margin_pct": _margin_pct(price, cost),
            })
        return pd.DataFrame(rows)

    def catalog(_access: DatasetAccessContext) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for item in catalog_rows():
            labs = item.get("lab_stats") or {}; thca = labs.get("thca") or {}; tac = labs.get("tac") or {}; terps = labs.get("terpenes") or {}; batch = item.get("primary_batch") or {}
            rows.append({
                "product_id": item.get("product_id"), "sku": item.get("sku"), "name": item.get("name"), "brand": item.get("brand"), "category": item.get("category"),
                "subcategory": item.get("subcategory"), "strain": item.get("strain"), "product_format": item.get("product_format"), "inventory_type": item.get("inventory_type"),
                "available": _float(item.get("available")), "unit": item.get("unit"), "suggested_price_usd": _float(item.get("suggested_price_usd")), "orderable": bool(item.get("orderable")),
                "test_preview": bool(item.get("test_preview")), "thca_min_percent": thca.get("minimum"), "thca_max_percent": thca.get("maximum"), "tac_min_percent": tac.get("minimum"),
                "tac_max_percent": tac.get("maximum"), "terpenes_min_percent": terps.get("minimum"), "terpenes_max_percent": terps.get("maximum"), "primary_lot_code": batch.get("lot_code"),
                "primary_package_id": batch.get("package_id"), "primary_coa_reference": batch.get("coa_reference"), "primary_coa_url": batch.get("coa_url"),
                "primary_batch_available": _float(batch.get("available")), "primary_received_at": batch.get("received_at"), "primary_expiration_at": batch.get("expiration_at"),
            })
        return pd.DataFrame(rows)

    def operational_summary(_access: DatasetAccessContext) -> pd.DataFrame:
        return pd.DataFrame([{**(inventory_snapshot().get("summary") or {}), **(storefront_snapshot().get("summary") or {})}])

    def pending_orders(_access: DatasetAccessContext) -> pd.DataFrame:
        safe: list[dict[str, Any]] = []
        for row in storefront_snapshot().get("orders_needing_approval") or []:
            lines = row.get("lines") if isinstance(row, dict) else []; lines = lines if isinstance(lines, list) else []
            safe.append({
                "request_id": row.get("id"), "status": row.get("status"), "buyer_company": row.get("buyer_company"), "buyer_license": row.get("buyer_license"),
                "purchase_order_reference": row.get("purchase_order_reference"), "requested_delivery_date": row.get("requested_delivery_date"), "requested_delivery_window": row.get("requested_delivery_window"),
                "estimated_subtotal": _float(row.get("estimated_subtotal")), "line_count": len(lines),
                "requested_quantity": round(sum(_float(line.get("quantity")) for line in lines if isinstance(line, dict)), 4),
                "products": ", ".join(_text(line.get("name")) for line in lines[:10] if isinstance(line, dict) and _text(line.get("name"))),
            })
        return pd.DataFrame(safe)

    def order_blockers(_access: DatasetAccessContext) -> pd.DataFrame:
        return pd.DataFrame([{"request_id": row.get("request_id"), "buyer_company": row.get("buyer_company"), "ready_for_review": bool(row.get("ready_for_review")), "blockers": "; ".join(_text(value) for value in row.get("reasons") or [] if _text(value))} for row in storefront_snapshot().get("order_blockers") or [] if isinstance(row, dict)])

    def account_history(_access: DatasetAccessContext) -> pd.DataFrame:
        orders, lines, partners = commercial_rows(); lines_by_order: dict[str, list[Any]] = defaultdict(list)
        for line in lines: lines_by_order[line.commercial_order_id].append(line)
        accounts: dict[str, dict[str, Any]] = {}
        for order in orders:
            partner = partners.get(order.partner_id)
            if partner is None: continue
            order_lines = lines_by_order.get(order.id, []); order_value = sum(_float(line.quantity) * _float(line.unit_price) for line in order_lines); quantity = sum(_float(line.quantity) for line in order_lines)
            row = accounts.setdefault(order.partner_id, {"partner_id": order.partner_id, "customer": partner.name, "license_or_registration": partner.license_or_registration, "payment_terms": partner.payment_terms, "order_count": 0, "open_order_count": 0, "fulfilled_order_count": 0, "total_order_value_usd": 0.0, "total_order_quantity": 0.0, "last_order_date": None, "last_order_status": "", "payment_attention_orders": 0})
            row["order_count"] += 1; row["open_order_count"] += int(_text(order.status).casefold() in {"draft", "confirmed", "allocated", "partially_fulfilled"}); row["fulfilled_order_count"] += int(_text(order.status).casefold() == "fulfilled")
            row["total_order_value_usd"] += order_value; row["total_order_quantity"] += quantity; row["payment_attention_orders"] += int(_text(getattr(order, "payment_status", "")).casefold() in {"overdue", "partial"})
            order_date = getattr(order, "order_date", None) or getattr(order, "created_at", None)
            if row["last_order_date"] is None or str(order_date or "") > str(row["last_order_date"] or ""): row["last_order_date"] = order_date; row["last_order_status"] = order.status
        output = []
        for row in accounts.values():
            count = int(row["order_count"] or 0); row["average_order_value_usd"] = round(_float(row["total_order_value_usd"]) / count, 2) if count else 0.0; row["total_order_value_usd"] = round(_float(row["total_order_value_usd"]), 2); row["total_order_quantity"] = round(_float(row["total_order_quantity"]), 4); row["days_since_last_order"] = _age_days(row["last_order_date"]); output.append(row)
        output.sort(key=lambda row: (_float(row.get("total_order_value_usd")), int(row.get("order_count") or 0)), reverse=True); return pd.DataFrame(output)

    def product_demand(_access: DatasetAccessContext) -> pd.DataFrame:
        orders, lines, _partners = commercial_rows(); order_by_id = {row.id: row for row in orders}; demand: dict[str, dict[str, Any]] = {}
        for line in lines:
            order = order_by_id.get(line.commercial_order_id)
            if order is None: continue
            key = _text(line.product_id) or _text(line.sku_snapshot) or _text(line.description)
            row = demand.setdefault(key, {"product_id": line.product_id, "sku": line.sku_snapshot, "description": line.description, "order_count": 0, "ordered_quantity": 0.0, "fulfilled_quantity": 0.0, "sales_value_usd": 0.0, "last_order_date": None})
            row["order_count"] += 1; row["ordered_quantity"] += _float(line.quantity); row["fulfilled_quantity"] += _float(line.fulfilled_quantity); row["sales_value_usd"] += _float(line.quantity) * _float(line.unit_price)
            order_date = getattr(order, "order_date", None) or getattr(order, "created_at", None)
            if row["last_order_date"] is None or str(order_date or "") > str(row["last_order_date"] or ""): row["last_order_date"] = order_date
        output = []
        for row in demand.values():
            row["ordered_quantity"] = round(_float(row["ordered_quantity"]), 4); row["fulfilled_quantity"] = round(_float(row["fulfilled_quantity"]), 4); row["outstanding_quantity"] = round(max(0.0, row["ordered_quantity"] - row["fulfilled_quantity"]), 4); row["sales_value_usd"] = round(_float(row["sales_value_usd"]), 2); row["days_since_last_order"] = _age_days(row["last_order_date"]); output.append(row)
        output.sort(key=lambda row: (_float(row.get("sales_value_usd")), _float(row.get("ordered_quantity"))), reverse=True); return pd.DataFrame(output)

    def ar_summary(_access: DatasetAccessContext) -> pd.DataFrame:
        buckets = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "90_plus": 0.0}
        for row in ar_rows():
            age = int(row.get("days_past_due") or 0); bucket = "current" if age == 0 else "1_30" if age <= 30 else "31_60" if age <= 60 else "61_90" if age <= 90 else "90_plus"; buckets[bucket] += _float(row.get("balance_usd"))
        return pd.DataFrame([{"total_ar_usd": round(sum(buckets.values()), 2), "current_usd": round(buckets["current"], 2), "past_due_1_30_usd": round(buckets["1_30"], 2), "past_due_31_60_usd": round(buckets["31_60"], 2), "past_due_61_90_usd": round(buckets["61_90"], 2), "past_due_90_plus_usd": round(buckets["90_plus"], 2), "open_invoice_count": len(ar_rows())}])

    def account_ar(_access: DatasetAccessContext) -> pd.DataFrame:
        accounts: dict[str, dict[str, Any]] = {}
        for invoice in ar_rows():
            partner_id = _text(invoice.get("partner_id")); row = accounts.setdefault(partner_id, {"partner_id": partner_id, "customer": invoice.get("customer"), "license_or_registration": invoice.get("license_or_registration"), "open_invoice_count": 0, "total_balance_usd": 0.0, "overdue_balance_usd": 0.0, "max_days_past_due": 0, "oldest_due_date": None})
            balance = _float(invoice.get("balance_usd")); age = int(invoice.get("days_past_due") or 0); row["open_invoice_count"] += 1; row["total_balance_usd"] += balance; row["overdue_balance_usd"] += balance if age > 0 else 0.0; row["max_days_past_due"] = max(int(row["max_days_past_due"]), age); due = invoice.get("due_date")
            if row["oldest_due_date"] is None or str(due or "") < str(row["oldest_due_date"] or ""): row["oldest_due_date"] = due
        output = list(accounts.values())
        for row in output: row["total_balance_usd"] = round(_float(row["total_balance_usd"]), 2); row["overdue_balance_usd"] = round(_float(row["overdue_balance_usd"]), 2)
        output.sort(key=lambda row: (_float(row.get("overdue_balance_usd")), _float(row.get("total_balance_usd"))), reverse=True); return pd.DataFrame(output)

    def customer_prices(_access: DatasetAccessContext) -> pd.DataFrame:
        return pd.DataFrame(customer_price_rows())

    specs = (
        DatasetSpec(key="wholesale_sellable_inventory", domain="wholesale", description="Released, passed-COA, positive-uncommitted wholesale lots with safe lab, aging, reservation, cost and suggested-margin fields", loader=sellable_inventory, allowed_agents=(WHOLESALE_AGENT,), required_capabilities=WHOLESALE_CAPABILITY, allowed_columns=("lot_id", "package_id", "lot_code", "batch_name", "product_id", "sku", "name", "item_type", "inventory_type", "usable_quantity", "reserved_quantity", "production_reserved_quantity", "wholesale_reserved_quantity", "wholesale_committed_quantity", "unit", "location", "status", "lab_testing_state", "coa_reference", "coa_url", "thca_percent", "tac_percent", "terpenes_percent", "harvested_at", "produced_at", "received_at", "expiration_at", "age_days", "unit_cost", "suggested_price_usd", "suggested_gross_margin_pct"), freshness="live canonical wholesale inventory projection", max_tool_rows=75),
        DatasetSpec(key="wholesale_catalog", domain="wholesale", description="Wholesale catalog products with availability, strain/category metadata and verified lab ranges", loader=catalog, allowed_agents=(WHOLESALE_AGENT,), required_capabilities=WHOLESALE_CAPABILITY, allowed_columns=("product_id", "sku", "name", "brand", "category", "subcategory", "strain", "product_format", "inventory_type", "available", "unit", "suggested_price_usd", "orderable", "test_preview", "thca_min_percent", "thca_max_percent", "tac_min_percent", "tac_max_percent", "terpenes_min_percent", "terpenes_max_percent", "primary_lot_code", "primary_package_id", "primary_coa_reference", "primary_coa_url", "primary_batch_available", "primary_received_at", "primary_expiration_at"), freshness="live wholesale storefront catalog projection", max_tool_rows=75),
        DatasetSpec(key="wholesale_operations_summary", domain="wholesale", description="Deterministic Wholesale Ops counts covering sellable inventory, customer approvals, open orders and manifest state", loader=operational_summary, allowed_agents=(WHOLESALE_AGENT,), required_capabilities=WHOLESALE_CAPABILITY, allow_business_columns=True, freshness="live Wholesale Ops intelligence", max_tool_rows=5),
        DatasetSpec(key="wholesale_pending_orders", domain="wholesale", description="Approval-gated storefront order requests without customer contact PII or free-text notes", loader=pending_orders, allowed_agents=(WHOLESALE_AGENT,), required_capabilities=WHOLESALE_CAPABILITY, allowed_columns=("request_id", "status", "buyer_company", "buyer_license", "purchase_order_reference", "requested_delivery_date", "requested_delivery_window", "estimated_subtotal", "line_count", "requested_quantity", "products"), freshness="live customer storefront order queue", max_tool_rows=50),
        DatasetSpec(key="wholesale_order_blockers", domain="wholesale", description="Deterministic inventory/license readiness blockers for submitted storefront orders", loader=order_blockers, allowed_agents=(WHOLESALE_AGENT,), required_capabilities=WHOLESALE_CAPABILITY, allowed_columns=("request_id", "buyer_company", "ready_for_review", "blockers"), freshness="live Wholesale Ops validation", max_tool_rows=50),
        DatasetSpec(key="wholesale_account_history", domain="wholesale", description="Facility sales-order history aggregated by licensed trade partner for account targeting and cadence analysis", loader=account_history, allowed_agents=(WHOLESALE_AGENT,), required_capabilities=WHOLESALE_CAPABILITY, allowed_columns=("partner_id", "customer", "license_or_registration", "payment_terms", "order_count", "open_order_count", "fulfilled_order_count", "total_order_value_usd", "average_order_value_usd", "total_order_quantity", "last_order_date", "last_order_status", "days_since_last_order", "payment_attention_orders"), freshness="live commercial order ledger aggregated by account", max_tool_rows=75),
        DatasetSpec(key="wholesale_product_demand", domain="wholesale", description="Historical sales-order demand aggregated by product for evidence-based wholesale targeting", loader=product_demand, allowed_agents=(WHOLESALE_AGENT,), required_capabilities=WHOLESALE_CAPABILITY, allowed_columns=("product_id", "sku", "description", "order_count", "ordered_quantity", "fulfilled_quantity", "outstanding_quantity", "sales_value_usd", "last_order_date", "days_since_last_order"), freshness="live commercial sales-order ledger aggregated by product", max_tool_rows=75),
        DatasetSpec(key="wholesale_customer_prices", domain="wholesale_finance", description="Active customer-specific wholesale price rules with effective price and margin calculations, excluding notes and contact PII", loader=customer_prices, allowed_agents=(WHOLESALE_AGENT,), required_capabilities=WHOLESALE_CAPABILITY, allowed_columns=("partner_id", "customer", "license_or_registration", "product_id", "sku", "product_name", "unit", "unit_cost", "base_price_usd", "explicit_customer_price_usd", "discount_pct", "effective_customer_price_usd", "customer_gross_margin_pct"), freshness="live customer price rules", max_tool_rows=75),
        DatasetSpec(key="wholesale_ar_summary", domain="wholesale_finance", description="Read-only facility A/R aging totals for working-capital awareness without customer contact or payment-detail PII", loader=ar_summary, allowed_agents=(WHOLESALE_AGENT,), required_capabilities=WHOLESALE_CAPABILITY, allowed_columns=("total_ar_usd", "current_usd", "past_due_1_30_usd", "past_due_31_60_usd", "past_due_61_90_usd", "past_due_90_plus_usd", "open_invoice_count"), freshness="live commercial invoice ledger", max_tool_rows=5),
        DatasetSpec(key="wholesale_account_ar", domain="wholesale_finance", description="Read-only A/R exposure aggregated by licensed account for sales-risk awareness", loader=account_ar, allowed_agents=(WHOLESALE_AGENT,), required_capabilities=WHOLESALE_CAPABILITY, allowed_columns=("partner_id", "customer", "license_or_registration", "open_invoice_count", "total_balance_usd", "overdue_balance_usd", "max_days_past_due", "oldest_due_date"), freshness="live commercial invoice ledger aggregated by account", max_tool_rows=75),
    )
    for spec in specs: registry.register(spec)
    return registry.load_for_agent(WHOLESALE_AGENT, access)
