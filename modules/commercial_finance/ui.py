"""Low-click Wholesale + Finance command center."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from modules.coman.db import create_coman_engine
from modules.commercial.repository import CommercialRepository

from .service import CommercialFinanceService


def _actor() -> str:
    return str(st.session_state.get("admin_user") or st.session_state.get("user_user") or "system")


def render_wholesale_finance() -> None:
    org = str(st.session_state.get("active_organization_id") or "")
    facility = str(st.session_state.get("active_facility_id") or "")
    if not org or not facility:
        st.info("Select an organization and facility first.")
        return
    engine = create_coman_engine()
    finance = CommercialFinanceService(engine)
    commercial = CommercialRepository(engine)
    orders = [row for row in commercial.list_orders(org, facility) if row.order_type == "sales"]
    ar = finance.ar_summary(org, facility)

    st.markdown("## Wholesale + Finance")
    st.caption("Order → allocation → shipment → invoice → payment, without leaving the commercial workflow.")
    top = st.columns(5)
    top[0].metric("Sales Orders", len(orders))
    top[1].metric("A/R", f"${ar['total_ar']:,.0f}")
    top[2].metric("Current", f"${ar['buckets']['current']:,.0f}")
    top[3].metric("1–30", f"${ar['buckets']['1_30']:,.0f}")
    top[4].metric("31+", f"${ar['buckets']['31_60'] + ar['buckets']['61_90'] + ar['buckets']['90_plus']:,.0f}")
    if ar["invoices"]:
        st.dataframe(pd.DataFrame(ar["invoices"]), hide_index=True, width="stretch")
    if not orders:
        st.info("Create a sales order first.")
        return

    labels = {f"{order.order_number} · {order.status.title()} · {order.payment_status.replace('_',' ').title()}": order for order in orders}
    order = labels[st.selectbox("Open order finance", list(labels), key="wholesale_finance_order")]
    snapshot = finance.order_finance(org, facility, order.id)
    st.markdown(f"### {order.order_number}")
    c1, c2 = st.columns(2)
    with c1.popover("Shipment / manifest", use_container_width=True):
        if snapshot["shipments"]:
            st.dataframe(pd.DataFrame([{"Shipment": s.shipment_number, "Status": s.status, "Manifest": s.manifest_reference, "Carrier": s.carrier, "Tracking": s.tracking_reference} for s in snapshot["shipments"]]), hide_index=True, width="stretch")
        shipment_number = st.text_input("Shipment number", value=f"SHP-{order.order_number}", key=f"ship_no_{order.id}")
        manifest = st.text_input("State manifest reference", key=f"ship_manifest_{order.id}")
        carrier = st.text_input("Carrier / route", key=f"ship_carrier_{order.id}")
        if st.button("Create shipment", type="primary", key=f"ship_create_{order.id}"):
            finance.create_shipment(organization_id=org, facility_id=facility, order_id=order.id, shipment_number=shipment_number, actor=_actor(), manifest_reference=manifest, carrier=carrier)
            st.rerun()
        if snapshot["shipments"]:
            ship = snapshot["shipments"][0]
            status = st.selectbox("Shipment status", ["planned","picking","packed","manifested","shipped","delivered","cancelled"], index=["planned","picking","packed","manifested","shipped","delivered","cancelled"].index(ship.status), key=f"ship_status_{ship.id}")
            if st.button("Update shipment", key=f"ship_update_{ship.id}"):
                finance.update_shipment_status(organization_id=org, facility_id=facility, shipment_id=ship.id, status=status)
                st.rerun()

    with c2.popover("Invoice / payment", use_container_width=True):
        if snapshot["invoices"]:
            st.dataframe(pd.DataFrame([{"Invoice": i.invoice_number, "Status": i.status, "Total": i.total_usd, "Balance": i.balance_usd, "Due": i.due_date} for i in snapshot["invoices"]]), hide_index=True, width="stretch")
        invoice_number = st.text_input("Invoice number", value=f"INV-{order.order_number}", key=f"invoice_no_{order.id}")
        terms = st.number_input("Due in days", min_value=0, max_value=180, value=30, step=1, key=f"invoice_terms_{order.id}")
        if st.button("Create invoice from order", type="primary", key=f"invoice_create_{order.id}"):
            finance.create_invoice_from_order(organization_id=org, facility_id=facility, order_id=order.id, invoice_number=invoice_number, actor=_actor(), due_days=int(terms))
            st.rerun()
        if snapshot["invoices"]:
            invoice = snapshot["invoices"][0]
            if invoice.status == "draft" and st.button("Mark invoice sent", key=f"invoice_send_{invoice.id}"):
                finance.send_invoice(organization_id=org, facility_id=facility, invoice_id=invoice.id)
                st.rerun()
            if invoice.balance_usd > 0:
                amount = st.number_input("Payment", min_value=0.0, max_value=float(invoice.balance_usd), value=float(invoice.balance_usd), step=1.0, key=f"payment_amt_{invoice.id}")
                method = st.selectbox("Method", ["ach","check","cash","card","other"], key=f"payment_method_{invoice.id}")
                reference = st.text_input("Reference", key=f"payment_ref_{invoice.id}")
                if st.button("Post payment", type="primary", key=f"payment_post_{invoice.id}"):
                    finance.record_payment(organization_id=org, facility_id=facility, invoice_id=invoice.id, amount_usd=amount, actor=_actor(), method=method, reference=reference, payment_date=date.today())
                    st.rerun()

    with st.popover("Customer-specific pricing", use_container_width=True):
        partners = [p for p in commercial.list_trade_partners(org) if p.partner_type in {"customer","both"}]
        # Reuse products already present in order lines to keep this contextual.
        lines = commercial.list_order_lines(org, order_id=order.id)
        if partners and lines:
            partner_map = {p.name: p for p in partners}
            product_map = {}
            # product identity is enough here; descriptions are already snapshots on the order.
            from modules.coman.repository import ComanRepository
            products = {p.id: p for p in ComanRepository(engine).list_products(org)}
            for line in lines:
                if line.product_id in products:
                    product_map[f"{products[line.product_id].name} · {products[line.product_id].sku}"] = products[line.product_id]
            partner = partner_map[st.selectbox("Customer", list(partner_map), key="price_rule_partner")]
            product = product_map[st.selectbox("Product", list(product_map), key="price_rule_product")]
            price = st.number_input("Fixed wholesale price", min_value=0.0, value=0.0, step=0.5, key="price_rule_price")
            discount = st.number_input("Or discount %", min_value=0.0, max_value=100.0, value=0.0, step=0.5, key="price_rule_discount")
            if st.button("Save price rule", type="primary", key="price_rule_save"):
                finance.upsert_customer_price(organization_id=org, partner_id=partner.id, product_id=product.id, actor=_actor(), price_usd=price, discount_pct=discount)
                st.success("Customer pricing saved.")


def render_wholesale_finance_dialog() -> None:
    if hasattr(st, "dialog"):
        @st.dialog("Wholesale + Finance", width="large")
        def _dialog() -> None:
            render_wholesale_finance()
        _dialog()
    else:
        render_wholesale_finance()
