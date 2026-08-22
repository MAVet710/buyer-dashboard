from __future__ import annotations

import json
import math
from datetime import timedelta

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from modules.coman.models import AuditEvent, CommercialOrder, CommercialOrderLine, InventoryLot, InventoryTransaction, Product, RetailSale, TradePartner, utc_now
from modules.product_master.models import ProductMasterProfile, ProductVendorLink
from .models import RetailPlanningPolicy


class RetailPlanningService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.sessions = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def upsert_policy(self, organization_id: str, facility_id: str, product_id: str, *, actor: str, **values) -> RetailPlanningPolicy:
        numeric = ("target_doh", "safety_stock", "reorder_point", "minimum_order_quantity", "case_pack")
        for key in numeric:
            if float(values.get(key, 0)) < 0: raise ValueError("Planning quantities cannot be negative.")
        window = int(values.get("velocity_window_days", 30))
        if not 7 <= window <= 180: raise ValueError("Velocity window must be between 7 and 180 days.")
        with self.sessions.begin() as session:
            product = session.get(Product, product_id)
            if not product or product.organization_id != organization_id: raise ValueError("Product was not found in this organization.")
            vendor_id = values.get("preferred_vendor_id") or None
            if vendor_id:
                vendor = session.get(TradePartner, vendor_id)
                if not vendor or vendor.organization_id != organization_id or vendor.partner_type not in {"vendor", "both"}: raise ValueError("Preferred vendor was not found in this organization.")
            row = session.scalar(select(RetailPlanningPolicy).where(RetailPlanningPolicy.organization_id == organization_id, RetailPlanningPolicy.facility_id == facility_id, RetailPlanningPolicy.product_id == product_id))
            if row is None:
                row = RetailPlanningPolicy(organization_id=organization_id, facility_id=facility_id, product_id=product_id)
                session.add(row)
            before = {key: getattr(row, key) for key in (*numeric, "velocity_window_days", "preferred_vendor_id", "active")}
            for key in numeric: setattr(row, key, float(values.get(key, getattr(row, key))))
            row.velocity_window_days = window; row.preferred_vendor_id = vendor_id; row.active = bool(values.get("active", True))
            session.flush()
            session.add(AuditEvent(organization_id=organization_id, facility_id=facility_id, entity_type="retail_planning_policy", entity_id=row.id, action="updated", actor=actor, changes_json=json.dumps({"before": before, "after": {key: getattr(row, key) for key in before}}, sort_keys=True)))
        return row

    def workspace(self, organization_id: str, facility_id: str) -> dict:
        now = utc_now()
        with Session(self.engine) as session:
            products = list(session.scalars(select(Product).outerjoin(ProductMasterProfile, ProductMasterProfile.product_id == Product.id).where(Product.organization_id == organization_id, Product.active.is_(True), (ProductMasterProfile.retail_enabled.is_(True)) | (ProductMasterProfile.product_id.is_(None))).order_by(Product.name)))
            product_ids = [row.id for row in products]
            profiles = {row.product_id: row for row in session.scalars(select(ProductMasterProfile).where(ProductMasterProfile.product_id.in_(product_ids)))} if product_ids else {}
            policies = {row.product_id: row for row in session.scalars(select(RetailPlanningPolicy).where(RetailPlanningPolicy.organization_id == organization_id, RetailPlanningPolicy.facility_id == facility_id, RetailPlanningPolicy.active.is_(True)))}
            vendors = list(session.scalars(select(TradePartner).where(TradePartner.organization_id == organization_id, TradePartner.active.is_(True), TradePartner.partner_type.in_(["vendor", "both"])).order_by(TradePartner.name)))
            vendor_names = {row.id: row.name for row in vendors}
            primary_links = {row.product_id: row for row in session.scalars(select(ProductVendorLink).where(ProductVendorLink.organization_id == organization_id, ProductVendorLink.active.is_(True), ProductVendorLink.is_primary.is_(True)))}
            balances = dict(session.execute(select(InventoryLot.product_id, func.coalesce(func.sum(InventoryTransaction.quantity_delta), 0.0)).join(InventoryTransaction, InventoryTransaction.lot_id == InventoryLot.id).where(InventoryLot.organization_id == organization_id, InventoryLot.facility_id == facility_id).group_by(InventoryLot.product_id)).all())
            open_orders = list(session.scalars(select(CommercialOrder).where(CommercialOrder.organization_id == organization_id, CommercialOrder.facility_id == facility_id, CommercialOrder.order_type == "purchase", CommercialOrder.status.in_(["draft", "confirmed", "partially_fulfilled"]))))
            inbound: dict[str, float] = {}
            committed_orders = [row for row in open_orders if row.status in {"confirmed", "partially_fulfilled"}]
            if committed_orders:
                for line in session.scalars(select(CommercialOrderLine).where(CommercialOrderLine.commercial_order_id.in_([row.id for row in committed_orders]))): inbound[line.product_id] = inbound.get(line.product_id, 0) + max(0, float(line.quantity) - float(line.fulfilled_quantity))
            recommendations = []
            for product in products:
                policy = policies.get(product.id); window = policy.velocity_window_days if policy else 30
                sold = float(session.scalar(select(func.coalesce(func.sum(RetailSale.quantity), 0.0)).where(RetailSale.organization_id == organization_id, RetailSale.facility_id == facility_id, RetailSale.product_id == product.id, RetailSale.sold_at >= now - timedelta(days=window), RetailSale.sold_at <= now)) or 0)
                velocity = sold / window; on_hand = float(balances.get(product.id, 0)); incoming = inbound.get(product.id, 0); target_doh = policy.target_doh if policy else 30.0; safety = policy.safety_stock if policy else 0.0; reorder_point = policy.reorder_point if policy else 0.0
                raw = max(0.0, velocity * target_doh + safety - on_hand - incoming)
                moq = policy.minimum_order_quantity if policy else 0.0; case_pack = policy.case_pack if policy else 0.0
                suggested = max(raw, moq) if raw > 0 else 0.0
                if suggested > 0 and case_pack > 0: suggested = math.ceil(suggested / case_pack) * case_pack
                vendor_id = policy.preferred_vendor_id if policy and policy.preferred_vendor_id else (primary_links.get(product.id).partner_id if primary_links.get(product.id) else None)
                recommendations.append({"product_id": product.id, "sku": product.sku, "product_name": product.name, "category": profiles.get(product.id).category if profiles.get(product.id) else "", "unit": product.base_unit, "unit_cost": float(product.unit_cost or 0), "on_hand": on_hand, "inbound": incoming, "sold": sold, "daily_velocity": velocity, "days_on_hand": on_hand / velocity if velocity > 0 else None, "target_doh": target_doh, "safety_stock": safety, "reorder_point": reorder_point, "minimum_order_quantity": moq, "case_pack": case_pack, "velocity_window_days": window, "preferred_vendor_id": vendor_id, "preferred_vendor_name": vendor_names.get(vendor_id, ""), "suggested_quantity": suggested, "suggested_cost": suggested * float(product.unit_cost or 0), "needs_reorder": suggested > 0 or on_hand <= reorder_point})
            recommendations.sort(key=lambda row: (not row["needs_reorder"], -(row["suggested_cost"])))
            orders = [{"id": row.id, "order_number": row.order_number, "partner_id": row.partner_id, "partner_name": vendor_names.get(row.partner_id, "Unknown vendor"), "status": row.status, "order_date": row.order_date, "due_at": row.due_at} for row in sorted(open_orders, key=lambda item: item.created_at, reverse=True)]
            return {"recommendations": recommendations, "vendors": [{"id": row.id, "name": row.name, "license_or_registration": row.license_or_registration, "payment_terms": row.payment_terms} for row in vendors], "open_purchase_orders": orders}
