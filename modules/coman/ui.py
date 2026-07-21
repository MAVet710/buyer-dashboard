"""Streamlit workspace for durable co-manufacturing intake and tracking."""

from __future__ import annotations

from datetime import datetime, time

import pandas as pd
import streamlit as st

from .db import ComanDatabaseConfigurationError, create_coman_engine
from .repository import ComanRepository


PRODUCT_FORMATS = [
    "Pouched flower",
    "Jarred flower",
    "Pre-roll",
    "Pre-roll pack",
    "Infused pre-roll",
    "Infused pre-roll pack",
    "Other",
]


@st.cache_resource
def _repository() -> ComanRepository:
    return ComanRepository(create_coman_engine())


def _actor() -> str:
    return str(
        st.session_state.get("admin_user")
        or st.session_state.get("user_user")
        or "system"
    )


def _orders_frame(orders, customers_by_id: dict[str, object]) -> pd.DataFrame:
    rows = []
    for order in orders:
        customer = customers_by_id.get(order.customer_id)
        rows.append(
            {
                "Order": order.order_number,
                "Type": order.work_type.title(),
                "Customer": getattr(customer, "name", "Internal") if customer else "Internal",
                "Product": order.product_name,
                "Format": order.product_format,
                "Units": order.requested_units,
                "Due": order.due_at.date().isoformat() if order.due_at else "Not set",
                "Priority": order.priority.title(),
                "Status": order.status.title(),
                "Source Lot": order.source_lot_reference,
            }
        )
    return pd.DataFrame(rows)


def render_coman_workspace() -> None:
    """Render the first usable Co-Man workflow against Supabase/PostgreSQL."""
    organization_id = st.session_state.get("active_organization_id")
    facility_id = st.session_state.get("active_facility_id")
    if not organization_id or not facility_id:
        st.warning("Select an organization and facility in the sidebar before entering Co-Man work.")
        return

    try:
        repository = _repository()
        customers = repository.list_customers(organization_id)
        orders = repository.list_production_orders(organization_id, facility_id)
    except ComanDatabaseConfigurationError:
        st.error("Co-Man storage is not configured. Add COMAN_DATABASE_URL to Streamlit secrets.")
        return
    except Exception as exc:
        st.error(f"Co-Man data could not be loaded: {exc}")
        return

    customers_by_id = {customer.id: customer for customer in customers}
    open_orders = [order for order in orders if order.status not in {"complete", "cancelled"}]
    external_orders = [order for order in orders if order.work_type == "external"]
    units_due = sum(order.requested_units for order in open_orders)
    metrics = st.columns(4)
    metrics[0].metric("Open Orders", len(open_orders))
    metrics[1].metric("Units Planned", f"{units_due:,}")
    metrics[2].metric("External Jobs", len(external_orders))
    metrics[3].metric("Customers", len(customers))

    overview_tab, orders_tab, customers_tab, planning_tab = st.tabs(
        ["Overview", "Production Orders", "Customers", "Capacity Planning"]
    )

    with overview_tab:
        st.markdown("#### Current production queue")
        frame = _orders_frame(orders, customers_by_id)
        if frame.empty:
            st.info("No production orders yet. Add the first job in Production Orders.")
        else:
            st.dataframe(frame, width="stretch", hide_index=True)

    with orders_tab:
        st.markdown("#### Add production order")
        with st.form("coman_production_order_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            order_number = col1.text_input("Order number*", placeholder="COM-000001")
            work_label = col2.selectbox("Work type*", ["Internal", "External"])
            requested_units = col3.number_input("Requested units*", min_value=1, step=100)
            product_name = col1.text_input("Product name*", placeholder="House Flower 3.5g")
            product_format = col2.selectbox("Product format*", PRODUCT_FORMATS)
            sku = col3.text_input("SKU")
            customer_options = {customer.name: customer.id for customer in customers}
            customer_label = col1.selectbox(
                "Customer* (external work)",
                ["Select customer"] + list(customer_options),
                disabled=work_label == "Internal",
            )
            due_date = col2.date_input("Due date")
            priority = col3.selectbox("Priority", ["Normal", "High", "Rush", "Low"])
            source_lot = col1.text_input("Source lot / METRC package")
            material_owner = col2.selectbox("Bulk material owner", ["Internal", "Customer"])
            packaging_owner = col3.selectbox("Packaging owner", ["Internal", "Customer"])
            notes = st.text_area("Production notes", placeholder="Breakdown, weighing, tubing, stickering, casing, or special instructions")
            submitted = st.form_submit_button("Create production order", type="primary")

        if submitted:
            customer_id = customer_options.get(customer_label)
            if not order_number.strip() or not product_name.strip():
                st.error("Order number and product name are required.")
            elif work_label == "External" and not customer_id:
                st.error("Create or select a customer for external work.")
            else:
                try:
                    repository.create_production_order(
                        organization_id=organization_id,
                        facility_id=facility_id,
                        order_number=order_number,
                        work_type=work_label.lower(),
                        product_name=product_name,
                        product_format=product_format.lower(),
                        requested_units=int(requested_units),
                        actor=_actor(),
                        customer_id=customer_id,
                        due_at=datetime.combine(due_date, time.min),
                        sku=sku,
                        priority=priority.lower(),
                        source_lot_reference=source_lot,
                        material_owner=material_owner.lower(),
                        packaging_owner=packaging_owner.lower(),
                        notes=notes,
                    )
                    st.success(f"Production order {order_number.strip()} was saved.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Order could not be saved: {exc}")

    with customers_tab:
        st.markdown("#### Co-Man customers")
        st.caption("Customers are only required when your facility packages product for another company.")
        with st.form("coman_customer_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            customer_name = col1.text_input("Company name*")
            license_number = col2.text_input("License / registration")
            contact_name = col1.text_input("Contact name")
            contact_email = col2.text_input("Contact email")
            add_customer = st.form_submit_button("Add customer", type="primary")
        if add_customer:
            if not customer_name.strip():
                st.error("Company name is required.")
            else:
                try:
                    repository.create_customer(
                        organization_id,
                        customer_name,
                        license_or_registration=license_number,
                        contact_name=contact_name,
                        contact_email=contact_email,
                    )
                    st.success(f"{customer_name.strip()} was added.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Customer could not be saved: {exc}")
        if customers:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Company": customer.name,
                            "License": customer.license_or_registration,
                            "Contact": customer.contact_name,
                            "Email": customer.contact_email,
                        }
                        for customer in customers
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

    with planning_tab:
        st.info(
            "Machine rates, staffing, routing steps, and schedule optimization are the next Co-Man milestone. "
            "Orders entered here are already stored in the durable structure that planning will use."
        )
