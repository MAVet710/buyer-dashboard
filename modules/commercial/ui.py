"""Professional Streamlit workspace for commercial orders and fulfillment."""

from __future__ import annotations

from datetime import date, timedelta
import html

import pandas as pd
import streamlit as st

from modules.coman.db import ComanDatabaseConfigurationError, create_coman_engine
from modules.coman.repository import ComanRepository
from modules.inventory_audit.repository import InventoryAuditRepository
from modules.inventory_audit.ui import render_inventory_audits

from .analytics import (
    commercial_dashboard_metrics,
    fulfillment_by_order,
    order_status_label,
    order_value_by_id,
)
from .repository import CommercialRepository


_CACHE_VERSION = "commercial-orders-audits-v2"
_OPEN_STATUSES = {"draft", "confirmed", "allocated", "partially_fulfilled"}


@st.cache_resource
def _repositories(
    cache_version: str,
) -> tuple[CommercialRepository, ComanRepository, InventoryAuditRepository]:
    del cache_version
    engine = create_coman_engine()
    return CommercialRepository(engine), ComanRepository(engine), InventoryAuditRepository(engine)


def _actor() -> str:
    return str(
        st.session_state.get("admin_user")
        or st.session_state.get("user_user")
        or "system"
    )


def _money(value: float) -> str:
    return f"${float(value):,.2f}"


def _commercial_css() -> None:
    st.markdown(
        """
        <style>
        .commercial-header {
            display:flex; align-items:flex-end; justify-content:space-between;
            gap:1rem; margin:.25rem 0 1.1rem;
        }
        .commercial-eyebrow {
            color:var(--dl-copper)!important; font-size:.68rem; font-weight:850;
            letter-spacing:.15em; text-transform:uppercase;
        }
        .commercial-title {
            margin:.18rem 0 0; color:var(--dl-text)!important;
            font-size:clamp(1.65rem,3vw,2.35rem); font-weight:800;
            letter-spacing:-.045em; line-height:1.05;
        }
        .commercial-subtitle {
            margin:.45rem 0 0; color:var(--dl-text-soft)!important; font-size:.9rem;
        }
        .commercial-live {
            display:inline-flex; align-items:center; gap:.45rem; padding:.38rem .66rem;
            color:var(--dl-green)!important; background:rgba(88,214,141,.08);
            border:1px solid rgba(88,214,141,.18); border-radius:999px;
            font-size:.7rem; font-weight:750; white-space:nowrap;
        }
        .commercial-live:before {
            width:7px; height:7px; content:""; background:var(--dl-green);
            border-radius:50%; box-shadow:0 0 0 4px rgba(88,214,141,.10);
        }
        .commercial-kpi {
            min-height:112px; padding:1rem 1.05rem; margin-bottom:.4rem;
            background:linear-gradient(145deg,var(--dl-surface-raised),var(--dl-surface));
            border:1px solid var(--dl-border); border-radius:16px;
            box-shadow:0 12px 34px rgba(0,0,0,.16);
        }
        .commercial-kpi__label {
            color:var(--dl-text-soft)!important; font-size:.7rem; font-weight:760;
            letter-spacing:.06em; text-transform:uppercase;
        }
        .commercial-kpi__value {
            margin:.45rem 0 .1rem; color:var(--dl-text)!important;
            font-size:1.55rem; font-weight:820; letter-spacing:-.045em;
        }
        .commercial-kpi__meta {color:var(--dl-text-faint)!important;font-size:.7rem}
        .commercial-panel-title {
            margin:.5rem 0 .1rem; font-size:1rem; font-weight:800;
            letter-spacing:-.02em;
        }
        .commercial-panel-note {
            min-height:1.1rem; margin-bottom:.55rem;
            color:var(--dl-text-soft)!important; font-size:.72rem;
        }
        .commercial-order-card {
            margin:.5rem 0; padding:.85rem .9rem;
            background:var(--dl-surface); border:1px solid var(--dl-border);
            border-radius:14px;
        }
        .commercial-order-card__top {
            display:flex; justify-content:space-between; gap:.75rem; font-weight:780;
        }
        .commercial-order-card__partner {
            margin:.28rem 0; color:var(--dl-text-soft)!important; font-size:.78rem;
        }
        .commercial-order-card__meta {
            color:var(--dl-text-faint)!important; font-size:.7rem;
        }
        .commercial-status {
            padding:.16rem .42rem; border-radius:999px; font-size:.6rem;
            color:var(--dl-copper-bright)!important; background:rgba(231,152,78,.10);
            border:1px solid rgba(231,152,78,.18); text-transform:uppercase;
            letter-spacing:.06em; white-space:nowrap;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _kpi(label: str, value: str, meta: str) -> None:
    st.markdown(
        f"""
        <div class="commercial-kpi">
            <div class="commercial-kpi__label">{html.escape(label)}</div>
            <div class="commercial-kpi__value">{html.escape(value)}</div>
            <div class="commercial-kpi__meta">{html.escape(meta)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _order_card(order, partner_name: str, value: float, fulfilled: tuple[float, float]) -> None:
    due = order.due_at.date().strftime("%b %d") if order.due_at else "No due date"
    requested, shipped = fulfilled
    st.markdown(
        f"""
        <div class="commercial-order-card">
            <div class="commercial-order-card__top">
                <span>{html.escape(order.order_number)}</span>
                <span class="commercial-status">{html.escape(order_status_label(order.status))}</span>
            </div>
            <div class="commercial-order-card__partner">{html.escape(partner_name)}</div>
            <div class="commercial-order-card__meta">
                {_money(value)} · Due {html.escape(due)} · {shipped:,.0f} / {requested:,.0f} fulfilled
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _dashboard(
    commercial: CommercialRepository,
    coman: ComanRepository,
    organization_id: str,
    facility_id: str,
    partners,
    orders,
    lines,
    products,
    lots,
) -> None:
    partners_by_id = {partner.id: partner for partner in partners}
    products_by_id = {product.id: product for product in products}
    values = order_value_by_id(lines)
    fulfillment = fulfillment_by_order(lines)

    balances: dict[str, float] = {}
    inventory_value = 0.0
    inventory_exceptions: list[tuple[object, float, str]] = []
    for lot in lots:
        balance = coman.inventory_balance(organization_id, lot.id)
        balances[lot.id] = balance
        product = products_by_id.get(lot.product_id)
        inventory_value += max(0.0, balance) * float(getattr(product, "unit_cost", 0.0) or 0.0)
        if balance <= 0 or lot.status not in {"available", "released"}:
            inventory_exceptions.append((lot, balance, getattr(product, "name", "Unknown product")))

    metrics = commercial_dashboard_metrics(
        orders,
        lines,
        inventory_value=inventory_value,
    )
    open_orders = [order for order in orders if order.status in _OPEN_STATUSES]
    sales = [order for order in open_orders if order.order_type == "sales"]
    purchases = [order for order in open_orders if order.order_type == "purchase"]

    kpi_cols = st.columns(5)
    with kpi_cols[0]:
        _kpi("Active inventory", _money(metrics["inventory_value"]), f"{len(lots)} tracked lots")
    with kpi_cols[1]:
        _kpi("Open sales", _money(metrics["open_sales_value"]), f"{len(sales)} orders")
    with kpi_cols[2]:
        _kpi("Open purchases", _money(metrics["open_purchase_value"]), f"{len(purchases)} orders")
    with kpi_cols[3]:
        _kpi("Fill rate", f"{metrics['fill_rate_pct']:.1f}%", "Across all order lines")
    with kpi_cols[4]:
        _kpi("Exceptions", str(metrics["overdue_orders"] + len(inventory_exceptions)), f"{metrics['overdue_orders']} overdue")

    search = st.text_input(
        "Search orders",
        placeholder="Order number, partner, reference, or status",
        key="commercial_order_search",
    ).strip().lower()
    if search:
        open_orders = [
            order
            for order in open_orders
            if search
            in " ".join(
                [
                    order.order_number,
                    order.external_reference,
                    order.status,
                    getattr(partners_by_id.get(order.partner_id), "name", ""),
                ]
            ).lower()
        ]
        sales = [order for order in open_orders if order.order_type == "sales"]
        purchases = [order for order in open_orders if order.order_type == "purchase"]

    incoming, outgoing, exceptions = st.columns([1, 1, 1])
    with incoming:
        st.markdown('<div class="commercial-panel-title">Incoming purchase orders</div>', unsafe_allow_html=True)
        st.markdown('<div class="commercial-panel-note">Receipts expected from vendors</div>', unsafe_allow_html=True)
        if not purchases:
            st.info("No open purchase orders.")
        for order in purchases[:8]:
            partner = partners_by_id.get(order.partner_id)
            _order_card(
                order,
                getattr(partner, "name", "Unknown vendor"),
                values.get(str(order.id), 0.0),
                fulfillment.get(str(order.id), (0.0, 0.0)),
            )
    with outgoing:
        st.markdown('<div class="commercial-panel-title">Outgoing sales orders</div>', unsafe_allow_html=True)
        st.markdown('<div class="commercial-panel-note">Customer demand awaiting shipment</div>', unsafe_allow_html=True)
        if not sales:
            st.info("No open sales orders.")
        for order in sales[:8]:
            partner = partners_by_id.get(order.partner_id)
            _order_card(
                order,
                getattr(partner, "name", "Unknown customer"),
                values.get(str(order.id), 0.0),
                fulfillment.get(str(order.id), (0.0, 0.0)),
            )
    with exceptions:
        st.markdown('<div class="commercial-panel-title">Inventory & due-date exceptions</div>', unsafe_allow_html=True)
        st.markdown('<div class="commercial-panel-note">Items needing an operator decision</div>', unsafe_allow_html=True)
        overdue = [
            order
            for order in open_orders
            if order.due_at and order.due_at.date() < date.today()
        ]
        if not overdue and not inventory_exceptions:
            st.success("No active exceptions.")
        for order in overdue[:5]:
            partner = partners_by_id.get(order.partner_id)
            _order_card(
                order,
                getattr(partner, "name", "Unknown partner"),
                values.get(str(order.id), 0.0),
                fulfillment.get(str(order.id), (0.0, 0.0)),
            )
        for lot, balance, product_name in inventory_exceptions[:5]:
            st.warning(f"{product_name} · lot {lot.lot_code} · {balance:,.2f} on hand")


def _new_order(
    commercial: CommercialRepository,
    organization_id: str,
    facility_id: str,
    partners,
    products,
) -> None:
    st.subheader("Create an order")
    st.caption("Capture the header and line items together. The order remains a draft until you confirm it.")
    if not partners or not products:
        st.info("Create at least one trade partner and one product before entering an order.")
        return

    with st.form("commercial_new_order", clear_on_submit=True):
        h1, h2, h3 = st.columns(3)
        with h1:
            order_type = st.selectbox("Order type", ["Sales", "Purchase"])
        eligible = [
            partner
            for partner in partners
            if partner.partner_type
            in ({"customer", "both"} if order_type == "Sales" else {"vendor", "both"})
        ]
        with h2:
            partner = st.selectbox(
                "Customer" if order_type == "Sales" else "Vendor",
                eligible,
                format_func=lambda row: row.name,
            ) if eligible else None
        prefix = "SO" if order_type == "Sales" else "PO"
        with h3:
            order_number = st.text_input(
                "Order number",
                value=f"{prefix}-{date.today():%y%m%d}-",
            )
        d1, d2, d3 = st.columns(3)
        with d1:
            order_date = st.date_input("Order date", value=date.today())
        with d2:
            due_date = st.date_input("Due date", value=date.today() + timedelta(days=7))
        with d3:
            external_reference = st.text_input("External reference", placeholder="METRC, vendor, or customer ref")

        seed_product = products[0]
        default_lines = pd.DataFrame(
            [
                {
                    "Product": f"{seed_product.sku} · {seed_product.name}",
                    "Quantity": 1.0,
                    "Unit Price": float(seed_product.unit_cost or 0.0),
                    "Notes": "",
                }
            ]
        )
        product_labels = [f"{product.sku} · {product.name}" for product in products]
        line_editor = st.data_editor(
            default_lines,
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            column_config={
                "Product": st.column_config.SelectboxColumn("Product", options=product_labels, required=True),
                "Quantity": st.column_config.NumberColumn("Quantity", min_value=0.01, step=1.0, required=True),
                "Unit Price": st.column_config.NumberColumn("Unit Price", min_value=0.0, format="$%.2f", required=True),
                "Notes": st.column_config.TextColumn("Line notes"),
            },
        )
        notes = st.text_area("Order notes", placeholder="Shipping requirements, terms, or internal handoff notes")
        submitted = st.form_submit_button("Create draft order", type="primary", width="stretch")

    if submitted:
        if partner is None:
            st.error(f"No eligible {'customer' if order_type == 'Sales' else 'vendor'} exists.")
            return
        by_label = {f"{product.sku} · {product.name}": product for product in products}
        payload = []
        for row in line_editor.to_dict("records"):
            product = by_label.get(str(row.get("Product") or ""))
            if product:
                payload.append(
                    {
                        "product_id": product.id,
                        "quantity": row.get("Quantity"),
                        "unit_price": row.get("Unit Price"),
                        "unit": product.base_unit,
                        "notes": row.get("Notes") or "",
                    }
                )
        try:
            commercial.create_order(
                organization_id=organization_id,
                facility_id=facility_id,
                partner_id=partner.id,
                order_number=order_number,
                order_type=order_type.lower(),
                order_date=order_date,
                due_date=due_date,
                lines=payload,
                actor=_actor(),
                external_reference=external_reference,
                notes=notes,
            )
        except Exception as exc:
            st.error(f"Order could not be created: {exc}")
        else:
            st.success(f"{order_number.strip().upper()} was created as a draft.")
            st.rerun()


def _execution(
    commercial: CommercialRepository,
    coman: ComanRepository,
    organization_id: str,
    facility_id: str,
    orders,
    lines,
    products,
    lots,
) -> None:
    open_orders = [order for order in orders if order.status in _OPEN_STATUSES]
    if not open_orders:
        st.info("There are no open orders to fulfill.")
        return
    order = st.selectbox(
        "Open order",
        open_orders,
        format_func=lambda row: f"{row.order_number} · {row.order_type.title()} · {order_status_label(row.status)}",
    )
    order_lines = [line for line in lines if line.commercial_order_id == order.id]
    products_by_id = {product.id: product for product in products}
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Line": line.position,
                    "Product": getattr(products_by_id.get(line.product_id), "name", line.description),
                    "Ordered": line.quantity,
                    "Fulfilled": line.fulfilled_quantity,
                    "Remaining": max(0.0, line.quantity - line.fulfilled_quantity),
                    "Unit": line.unit,
                    "Price": line.unit_price,
                }
                for line in order_lines
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    a1, a2, a3 = st.columns([1, 1, 1])
    with a1:
        if order.status == "draft" and st.button("Confirm order", type="primary", width="stretch"):
            try:
                commercial.confirm_order(order.id, organization_id=organization_id, facility_id=facility_id, actor=_actor())
                st.success("Order confirmed.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with a2:
        payment = st.selectbox(
            "Payment",
            ["not_invoiced", "draft", "sent", "partial", "paid", "overdue"],
            index=["not_invoiced", "draft", "sent", "partial", "paid", "overdue"].index(order.payment_status),
            format_func=order_status_label,
        )
        if payment != order.payment_status:
            if st.button("Update payment", width="stretch"):
                commercial.set_payment_status(order.id, organization_id=organization_id, facility_id=facility_id, payment_status=payment, actor=_actor())
                st.rerun()
    with a3:
        if st.button("Cancel order", width="stretch"):
            try:
                commercial.cancel_order(order.id, organization_id=organization_id, facility_id=facility_id, actor=_actor())
                st.warning("Order cancelled and active reservations released.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    if order.status == "draft":
        st.info("Confirm this order to allocate or fulfill it.")
        return

    remaining_lines = [line for line in order_lines if line.fulfilled_quantity < line.quantity - 1e-9]
    if not remaining_lines:
        st.success("All order lines are fulfilled.")
        return
    line = st.selectbox(
        "Line to process",
        remaining_lines,
        format_func=lambda row: f"{row.position}. {getattr(products_by_id.get(row.product_id), 'name', row.description)} · {row.quantity - row.fulfilled_quantity:,.2f} remaining",
    )
    matching_lots = [lot for lot in lots if lot.product_id == line.product_id]
    product = products_by_id.get(line.product_id)

    if order.order_type == "purchase" and not matching_lots:
        with st.form("commercial_quick_lot"):
            st.markdown("**Create the receiving lot**")
            lot_code = st.text_input("Lot / package code")
            location = st.text_input("Location", value="RECEIVING")
            create_lot = st.form_submit_button("Create receiving lot")
        if create_lot:
            try:
                coman.create_inventory_lot(
                    organization_id,
                    facility_id,
                    product_id=line.product_id,
                    lot_code=lot_code,
                    actor=_actor(),
                    opening_quantity=0,
                    location_code=location,
                    unit=line.unit,
                )
                st.success("Receiving lot created.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        return
    if not matching_lots:
        st.warning("No matching inventory lot is available for this product.")
        return

    lot = st.selectbox(
        "Inventory lot",
        matching_lots,
        format_func=lambda row: f"{row.lot_code} · {coman.inventory_balance(organization_id, row.id):,.2f} {line.unit} on hand",
    )
    quantity = st.number_input(
        "Quantity",
        min_value=0.0001,
        max_value=float(max(0.0001, line.quantity - line.fulfilled_quantity)),
        value=float(min(1.0, line.quantity - line.fulfilled_quantity)),
    )
    reference = st.text_input("Fulfillment reference", value=order.external_reference or order.order_number)

    if order.order_type == "sales":
        allocations = commercial.list_allocations(
            organization_id,
            facility_id,
            order_id=order.id,
        )
        reserved = sum(
            allocation.quantity - allocation.fulfilled_quantity
            for allocation in allocations
            if allocation.commercial_order_line_id == line.id
            and allocation.lot_id == lot.id
            and allocation.status in {"reserved", "partial"}
        )
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Reserve lot", type="primary", width="stretch"):
                try:
                    commercial.allocate_lot(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        order_line_id=line.id,
                        lot_id=lot.id,
                        quantity=quantity,
                        actor=_actor(),
                    )
                    st.success("Inventory reserved.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        with b2:
            if st.button("Post shipment", width="stretch", disabled=reserved + 1e-9 < quantity):
                try:
                    commercial.post_fulfillment(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        order_line_id=line.id,
                        lot_id=lot.id,
                        quantity=quantity,
                        actor=_actor(),
                        reference=reference,
                    )
                    st.success("Shipment posted to the immutable inventory ledger.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        st.caption(f"{reserved:,.2f} {line.unit} currently reserved from this lot.")
    elif st.button("Post receipt", type="primary", width="stretch"):
        try:
            commercial.post_fulfillment(
                organization_id=organization_id,
                facility_id=facility_id,
                order_line_id=line.id,
                lot_id=lot.id,
                quantity=quantity,
                actor=_actor(),
                reference=reference,
            )
            st.success("Receipt posted to inventory.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def _partners(commercial: CommercialRepository, organization_id: str, partners) -> None:
    left, right = st.columns([1, 1.65])
    with left:
        st.subheader("Add trade partner")
        with st.form("commercial_partner", clear_on_submit=True):
            name = st.text_input("Business name")
            partner_type = st.selectbox("Relationship", ["Customer", "Vendor", "Both"])
            license_number = st.text_input("License / registration")
            contact_name = st.text_input("Primary contact")
            contact_email = st.text_input("Email")
            contact_phone = st.text_input("Phone")
            payment_terms = st.selectbox("Default terms", ["Due on receipt", "Net 7", "Net 15", "Net 30", "Net 45", "Net 60"])
            submitted = st.form_submit_button("Create partner", type="primary", width="stretch")
        if submitted:
            try:
                commercial.create_trade_partner(
                    organization_id,
                    name=name,
                    partner_type=partner_type.lower(),
                    actor=_actor(),
                    license_or_registration=license_number,
                    contact_name=contact_name,
                    contact_email=contact_email,
                    contact_phone=contact_phone,
                    payment_terms=payment_terms,
                )
                st.success(f"{name.strip()} was added.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    with right:
        st.subheader("Partner directory")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Business": partner.name,
                        "Type": partner.partner_type.title(),
                        "License": partner.license_or_registration,
                        "Contact": partner.contact_name,
                        "Email": partner.contact_email,
                        "Phone": partner.contact_phone,
                        "Terms": partner.payment_terms,
                    }
                    for partner in partners
                ]
            ),
            width="stretch",
            hide_index=True,
        )


def _ledger(commercial, organization_id, facility_id, orders, lines, products, lots) -> None:
    orders_by_id = {order.id: order for order in orders}
    lines_by_id = {line.id: line for line in lines}
    products_by_id = {product.id: product for product in products}
    lots_by_id = {lot.id: lot for lot in lots}
    transactions = commercial.list_commercial_transactions(organization_id, facility_id)
    rows = []
    for transaction in transactions:
        order = orders_by_id.get(transaction.commercial_order_id)
        line = lines_by_id.get(transaction.commercial_order_line_id)
        product = products_by_id.get(getattr(line, "product_id", ""))
        lot = lots_by_id.get(transaction.lot_id)
        rows.append(
            {
                "Occurred": transaction.occurred_at,
                "Order": getattr(order, "order_number", transaction.reference),
                "Type": transaction.transaction_type.title(),
                "Product Name": getattr(product, "name", "Unknown"),
                "Lot": getattr(lot, "lot_code", transaction.lot_id),
                "Quantity": transaction.quantity_delta,
                "Unit": transaction.unit,
                "Reference": transaction.reference,
                "Actor": transaction.actor,
            }
        )
    st.subheader("Commercial inventory ledger")
    st.caption("Receipts and shipments are append-only. Inventory is derived from these signed movements.")
    if rows:
        frame = pd.DataFrame(rows)
        st.dataframe(frame, width="stretch", hide_index=True)
        st.download_button(
            "Export ledger CSV",
            data=frame.to_csv(index=False).encode("utf-8"),
            file_name=f"commercial_ledger_{date.today():%Y-%m-%d}.csv",
            mime="text/csv",
        )
    else:
        st.info("No commercial receipts or shipments have been posted yet.")


def render_commercial_workspace() -> None:
    """Render the organization-scoped commercial command center."""

    _commercial_css()
    organization_id = st.session_state.get("active_organization_id")
    facility_id = st.session_state.get("active_facility_id")
    if not organization_id or not facility_id:
        st.warning("Select an organization and facility before opening Commercial Ops.")
        return

    st.markdown(
        f"""
        <div class="commercial-header">
            <div>
                <div class="commercial-eyebrow">Commercial operations</div>
                <div class="commercial-title">Orders, inventory, and fulfillment</div>
                <div class="commercial-subtitle">One durable flow from purchase order to receipt, reservation, shipment, and payment.</div>
            </div>
            <div class="commercial-live">{html.escape(str(st.session_state.get("active_facility_name") or "Active facility"))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        commercial, coman, inventory_audits = _repositories(_CACHE_VERSION)
        partners = commercial.list_trade_partners(organization_id)
        orders = commercial.list_orders(organization_id, facility_id)
        lines = commercial.list_order_lines(organization_id)
        products = coman.list_products(organization_id)
        lots = coman.list_inventory_lots(organization_id, facility_id)
    except ComanDatabaseConfigurationError:
        st.error("Supabase is not configured. Add COMAN_DATABASE_URL to the Streamlit app secrets.")
        return
    except Exception as exc:
        message = str(exc)
        if "inventory_audits" in message or "inventory_audit_lines" in message:
            st.error("Inventory Audits needs database migration 0012 before Commercial Ops can load.")
            st.code("migrations/versions/0012_inventory_audits.sql")
        elif "commercial_trade_partners" in message or "commercial_orders" in message:
            st.error("Commercial Ops needs database migration 0011 before it can load.")
            st.code("migrations/versions/0011_commercial_order_fulfillment.sql")
        else:
            st.error(f"Commercial data could not be loaded: {exc}")
        return

    tabs = st.tabs(
        [
            "Command Center",
            "New Order",
            "Allocate & Fulfill",
            "Trade Partners",
            "Inventory Audits",
            "Inventory Ledger",
        ]
    )
    with tabs[0]:
        _dashboard(
            commercial,
            coman,
            organization_id,
            facility_id,
            partners,
            orders,
            lines,
            products,
            lots,
        )
    with tabs[1]:
        _new_order(commercial, organization_id, facility_id, partners, products)
    with tabs[2]:
        _execution(
            commercial,
            coman,
            organization_id,
            facility_id,
            orders,
            lines,
            products,
            lots,
        )
    with tabs[3]:
        _partners(commercial, organization_id, partners)
    with tabs[4]:
        render_inventory_audits(
            inventory_audits,
            organization_id,
            facility_id,
            products,
            lots,
        )
    with tabs[5]:
        _ledger(
            commercial,
            organization_id,
            facility_id,
            orders,
            lines,
            products,
            lots,
        )
