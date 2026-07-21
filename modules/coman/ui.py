"""Streamlit workspace for durable co-manufacturing intake and tracking."""

from __future__ import annotations

from datetime import date, datetime, time

import altair as alt
import pandas as pd
import streamlit as st

from .db import ComanDatabaseConfigurationError, create_coman_engine
from .planning import (
    estimate_hand_labor_job,
    estimate_machine_job,
    recommend_weight_allocation,
    weight_to_grams,
)
from .repository import ComanRepository


PRODUCT_FORMATS = [
    "Pouched flower - 3.5 g",
    "Pouched flower - 7 g",
    "Pouched flower - 14 g",
    "Pouched flower - 1 oz (28 g)",
    "Jarred flower",
    "Pre-roll",
    "Pre-roll pack",
    "Infused pre-roll",
    "Infused pre-roll pack",
    "Other",
]

DEFAULT_OPTIMIZER_PRODUCTS = [
    {"eligible": True, "product": "3.5 g flower pouch", "format": "Pouched flower - 3.5 g", "unit_size_g": 3.5, "revenue_per_unit": 18.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 0.75, "other_cost_per_unit": 0.10, "machine_units_per_hour": 900.0, "machine_crew": 3, "machine_cost_per_hour": 35.0, "units_per_case": 50, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "7 g flower pouch", "format": "Pouched flower - 7 g", "unit_size_g": 7.0, "revenue_per_unit": 32.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 0.85, "other_cost_per_unit": 0.12, "machine_units_per_hour": 750.0, "machine_crew": 3, "machine_cost_per_hour": 35.0, "units_per_case": 30, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "14 g flower pouch", "format": "Pouched flower - 14 g", "unit_size_g": 14.0, "revenue_per_unit": 58.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 0.95, "other_cost_per_unit": 0.15, "machine_units_per_hour": 600.0, "machine_crew": 3, "machine_cost_per_hour": 35.0, "units_per_case": 20, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "1 oz flower pouch", "format": "Pouched flower - 1 oz (28 g)", "unit_size_g": 28.0, "revenue_per_unit": 105.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 1.10, "other_cost_per_unit": 0.18, "machine_units_per_hour": 450.0, "machine_crew": 3, "machine_cost_per_hour": 35.0, "units_per_case": 12, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "3.5 g flower jar", "format": "Jarred flower", "unit_size_g": 3.5, "revenue_per_unit": 20.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 1.15, "other_cost_per_unit": 0.10, "machine_units_per_hour": 500.0, "machine_crew": 4, "machine_cost_per_hour": 25.0, "units_per_case": 48, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "1 g pre-roll", "format": "Pre-roll", "unit_size_g": 1.0, "revenue_per_unit": 6.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 0.35, "other_cost_per_unit": 0.08, "machine_units_per_hour": 1200.0, "machine_crew": 4, "machine_cost_per_hour": 45.0, "units_per_case": 100, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "5-pack pre-roll", "format": "Pre-roll pack", "unit_size_g": 2.5, "revenue_per_unit": 16.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 0.90, "other_cost_per_unit": 0.12, "machine_units_per_hour": 350.0, "machine_crew": 5, "machine_cost_per_hour": 45.0, "units_per_case": 40, "max_allocation_pct": 100.0},
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
        machine_models = repository.list_machine_models()
        facility_machines = repository.list_facility_machines(organization_id, facility_id)
        hand_area = repository.ensure_primary_hand_labor_area(organization_id, facility_id)
        actuals = repository.list_production_actuals(organization_id, facility_id)
        crew_availability = repository.list_crew_availability(organization_id, facility_id, date.today())
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

    overview_tab, orders_tab, planning_tab, resources_tab, customers_tab, performance_tab = st.tabs(
        ["Dashboard", "New Job", "Schedule", "Resources", "Customers", "Performance"]
    )

    with overview_tab:
        st.markdown("#### Setup readiness")
        readiness = pd.DataFrame(
            [
                {"Requirement": "Facility selected", "Status": "Ready"},
                {"Requirement": "Hand-labor rates", "Status": "Ready" if all([hand_area.sticker_units_per_person_hour > 0, hand_area.case_pack_units_per_person_hour > 0, hand_area.final_cases_per_person_hour > 0]) else "Needs setup"},
                {"Requirement": "Facility machine", "Status": "Ready" if facility_machines else "Needs setup"},
                {"Requirement": "Production queue", "Status": "Ready" if orders else "No jobs yet"},
            ]
        )
        st.dataframe(readiness, width="stretch", hide_index=True)
        st.markdown("#### Current production queue")
        filter1, filter2, filter3 = st.columns(3)
        status_filter = filter1.selectbox("Status filter", ["All"] + sorted({order.status.title().replace("_", " ") for order in orders}))
        priority_filter = filter2.selectbox("Priority filter", ["All"] + sorted({order.priority.title() for order in orders}))
        format_filter = filter3.selectbox("Format filter", ["All"] + sorted({order.product_format.title() for order in orders}))
        filtered_orders = [order for order in orders if (status_filter == "All" or order.status.replace("_", " ").title() == status_filter) and (priority_filter == "All" or order.priority.title() == priority_filter) and (format_filter == "All" or order.product_format.title() == format_filter)]
        frame = _orders_frame(filtered_orders, customers_by_id)
        if frame.empty:
            st.info("No production orders yet. Add the first job in Production Orders.")
        else:
            st.dataframe(frame, width="stretch", hide_index=True)
            st.markdown("#### Queue actions")
            order_actions = {f"{order.order_number} â€” {order.product_name}": order for order in orders}
            action_col1, action_col2 = st.columns(2)
            selected_action_order = order_actions[action_col1.selectbox("Order", list(order_actions), key="coman_action_order")]
            status_label = action_col2.selectbox("New status", ["Draft", "Scheduled", "In Progress", "On Hold", "Complete", "Cancelled"])
            action_btn1, action_btn2 = st.columns(2)
            if action_btn1.button("Update status", type="primary", width="stretch"):
                try:
                    repository.update_production_order_status(selected_action_order.id, organization_id=organization_id, facility_id=facility_id, status=status_label.lower().replace(" ", "_"), actor=_actor())
                    st.success("Order status updated.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Status could not be updated: {exc}")
            with action_btn2.popover("Duplicate recurring job", width="stretch"):
                duplicate_number = st.text_input("New order number", key="coman_duplicate_number")
                if st.button("Create duplicate", key="coman_duplicate_btn"):
                    try:
                        repository.duplicate_production_order(selected_action_order.id, organization_id=organization_id, facility_id=facility_id, new_order_number=duplicate_number, actor=_actor())
                        st.success("Recurring job duplicated.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Order could not be duplicated: {exc}")

    with orders_tab:
        st.markdown("#### Weight-based production recommendation")
        st.caption(
            "Enter the bulk available, then compare finished-product uses by contribution profit. "
            "Recommendations are advisory until you create a committed production order below."
        )
        weight1, weight2, weight3, weight4 = st.columns(4)
        bulk_weight = weight1.number_input("Available bulk weight", min_value=0.0, value=10.0, step=1.0)
        bulk_unit = weight2.selectbox("Weight unit", ["Pounds", "Grams", "Kilograms"])
        expected_loss_pct = weight3.number_input("Expected process loss %", min_value=0.0, max_value=50.0, value=5.0, step=0.5)
        optimization_goal = weight4.selectbox("Optimization goal", ["Maximum total profit", "Maximum profit per labor hour"])
        econ1, econ2, econ3 = st.columns(3)
        optimizer_work_type = econ1.selectbox("Economics", ["Internal / owned product", "External co-man service"])
        labor_rate = econ2.number_input("Loaded labor cost $/hour", min_value=0.0, value=22.0, step=1.0)
        usable_weight_g = weight_to_grams(float(bulk_weight), bulk_unit) * (1 - float(expected_loss_pct) / 100)
        econ3.metric("Usable weight after loss", f"{usable_weight_g:,.1f} g")
        if optimizer_work_type.startswith("External"):
            st.info("For customer-owned bulk, set Bulk Cost $/g to $0 and enter your packaging/service fee as Revenue/Unit.")
        else:
            st.info("For owned product, Revenue/Unit is expected wholesale or transfer revenue and Bulk Cost $/g is your cannabis cost basis.")

        optimizer_products = st.data_editor(
            pd.DataFrame(DEFAULT_OPTIMIZER_PRODUCTS),
            key="coman_optimizer_products",
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "eligible": st.column_config.CheckboxColumn("Use"),
                "product": st.column_config.TextColumn("Product / SKU", required=True),
                "format": st.column_config.SelectboxColumn("Format", options=PRODUCT_FORMATS, required=True),
                "unit_size_g": st.column_config.NumberColumn("Grams/Unit", min_value=0.01, format="%.2f"),
                "revenue_per_unit": st.column_config.NumberColumn("Revenue/Unit", min_value=0.0, format="$%.2f"),
                "bulk_cost_per_g": st.column_config.NumberColumn("Bulk Cost $/g", min_value=0.0, format="$%.2f"),
                "packaging_cost_per_unit": st.column_config.NumberColumn("Packaging/Unit", min_value=0.0, format="$%.2f"),
                "other_cost_per_unit": st.column_config.NumberColumn("Other Cost/Unit", min_value=0.0, format="$%.2f"),
                "machine_units_per_hour": st.column_config.NumberColumn("Machine Units/Hr", min_value=0.0, format="%.0f"),
                "machine_crew": st.column_config.NumberColumn("Machine Crew", min_value=0, step=1),
                "machine_cost_per_hour": st.column_config.NumberColumn("Machine $/Hr", min_value=0.0, format="$%.2f"),
                "units_per_case": st.column_config.NumberColumn("Units/Case", min_value=1, step=1),
                "max_allocation_pct": st.column_config.NumberColumn("Max Allocation %", min_value=0.0, max_value=100.0, format="%.0f%%"),
            },
        )
        rates_ready_for_optimizer = all(
            [
                hand_area.sticker_units_per_person_hour > 0,
                hand_area.case_pack_units_per_person_hour > 0,
                hand_area.final_cases_per_person_hour > 0,
            ]
        )
        if not rates_ready_for_optimizer:
            st.warning("Set all hand-labor rates in Resources for a complete profit recommendation. Missing rates currently contribute zero labor time.")
        recommendations = recommend_weight_allocation(
            weight_to_grams(float(bulk_weight), bulk_unit),
            optimizer_products.to_dict("records"),
            loss_pct=float(expected_loss_pct),
            labor_rate=float(labor_rate),
            sticker_units_per_person_hour=float(hand_area.sticker_units_per_person_hour),
            case_pack_units_per_person_hour=float(hand_area.case_pack_units_per_person_hour),
            final_cases_per_person_hour=float(hand_area.final_cases_per_person_hour),
            optimization_goal=optimization_goal,
        )
        if not recommendations:
            st.info("Enter bulk weight and at least one eligible product with a valid grams-per-unit value.")
        else:
            total_profit = sum(row["profit"] for row in recommendations)
            total_revenue = sum(row["revenue"] for row in recommendations)
            total_labor = sum(row["total_labor_hours"] for row in recommendations)
            allocated_g = sum(row["allocated_g"] for row in recommendations)
            result_metrics = st.columns(4)
            result_metrics[0].metric("Recommended Profit", f"${total_profit:,.2f}")
            result_metrics[1].metric("Contribution Margin", f"{(total_profit / total_revenue * 100) if total_revenue else 0:.1f}%")
            result_metrics[2].metric("Labor Required", f"{total_labor:,.1f} hr")
            result_metrics[3].metric("Bulk Allocated", f"{allocated_g:,.1f} g")
            recommendation_frame = pd.DataFrame(
                [
                    {
                        "Rank": index,
                        "Product": row["product"],
                        "Format": row["format"],
                        "Units": row["units"],
                        "Bulk Grams": round(row["allocated_g"], 1),
                        "Cases": row["cases"],
                        "Revenue": round(row["revenue"], 2),
                        "Total Cost": round(row["total_cost"], 2),
                        "Profit": round(row["profit"], 2),
                        "Margin %": round(row["margin_pct"], 1),
                        "Profit/Input Lb": round(row["profit_per_input_lb"], 2),
                        "Profit/Labor Hr": round(row["profit_per_labor_hour"], 2),
                        "Machine Hours": round(row["machine_hours"], 1),
                        "Hand Labor Hours": round(row["hand_labor_hours"], 1),
                    }
                    for index, row in enumerate(recommendations, start=1)
                ]
            )
            st.dataframe(recommendation_frame, width="stretch", hide_index=True)
            remaining_g = max(0.0, usable_weight_g - allocated_g)
            st.caption(
                f"Remaining usable bulk: {remaining_g:,.1f} g. Use Max Allocation % to reserve demand or split bulk across products. "
                "Final case pack, case pack, and stickering are included from the facility's Resources rates."
            )

        st.divider()
        st.markdown("#### Committed production order")
        st.caption("Use this path when a customer or internal plan already requires a specific finished-unit quantity.")
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

    with resources_tab:
        st.markdown("#### Facility equipment and observed rates")
        st.caption(
            "Published specifications are a starting reference. Effective rate should be what this facility "
            "can repeatedly achieve with its product, operators, setup, and quality requirements."
        )
        if not machine_models:
            st.warning("No machine benchmark models are loaded yet.")
        else:
            model_options = {
                f"{model.manufacturer} â€” {model.model} ({model.category})": model
                for model in machine_models
            }
            with st.form("coman_facility_machine_form", clear_on_submit=True):
                model_label = st.selectbox("Machine model*", list(model_options))
                selected_model = model_options[model_label]
                st.caption(
                    f"Published maximum: {selected_model.published_max_rate:g} "
                    f"{selected_model.rate_unit}; planning reference utilization: "
                    f"{selected_model.planning_utilization_pct:g}%"
                )
                col1, col2, col3 = st.columns(3)
                asset_code = col1.text_input("Asset code*", placeholder="PR-01")
                display_name = col2.text_input("Facility name*", value=selected_model.model)
                effective_rate = col3.number_input(
                    "Observed effective rate (units/hour)*", min_value=0.1, value=100.0, step=10.0
                )
                crew_size = col1.number_input("Preferred crew", min_value=1, value=1, step=1)
                setup_minutes = col2.number_input("Setup minutes", min_value=0, value=30, step=5)
                cleanup_minutes = col3.number_input("Cleanup minutes", min_value=0, value=30, step=5)
                save_machine = st.form_submit_button("Add facility machine", type="primary")
            if save_machine:
                if not asset_code.strip() or not display_name.strip():
                    st.error("Asset code and facility name are required.")
                else:
                    try:
                        repository.create_facility_machine(
                            organization_id=organization_id,
                            facility_id=facility_id,
                            machine_model_id=selected_model.id,
                            asset_code=asset_code,
                            display_name=display_name,
                            effective_rate=float(effective_rate),
                            preferred_crew_size=int(crew_size),
                            setup_minutes=int(setup_minutes),
                            cleanup_minutes=int(cleanup_minutes),
                            actor=_actor(),
                        )
                        st.success(f"{display_name.strip()} was added to this facility.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Machine could not be saved: {exc}")
        if facility_machines:
            models_by_id = {model.id: model for model in machine_models}
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Asset": machine.asset_code,
                            "Machine": machine.display_name,
                            "Model": getattr(models_by_id.get(machine.machine_model_id), "model", "Unknown"),
                            "Observed Units/Hour": machine.effective_rate,
                            "Crew": machine.preferred_crew_size,
                            "Setup Min": machine.setup_minutes,
                            "Cleanup Min": machine.cleanup_minutes,
                        }
                        for machine in facility_machines
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

    with resources_tab:
        st.divider()
        st.markdown("#### Required hand-labor area")
        st.caption("Stickering, case packing, and final case packing are included for every facility. Enter repeatable per-person rates from your operation.")
        with st.form("coman_hand_labor_form"):
            col1, col2, col3 = st.columns(3)
            hand_crew = col1.number_input("Default hand-labor crew", min_value=1, value=max(1, hand_area.default_crew_size), step=1)
            sticker_rate = col1.number_input("Stickering units/person/hour*", min_value=0.0, value=float(hand_area.sticker_units_per_person_hour), step=10.0)
            case_rate = col2.number_input("Case-pack units/person/hour*", min_value=0.0, value=float(hand_area.case_pack_units_per_person_hour), step=10.0)
            final_case_rate = col3.number_input("Final cases/person/hour*", min_value=0.0, value=float(hand_area.final_cases_per_person_hour), step=1.0)
            hand_setup = col2.number_input("Area setup minutes", min_value=0, value=hand_area.setup_minutes, step=5)
            hand_cleanup = col3.number_input("Area cleanup minutes", min_value=0, value=hand_area.cleanup_minutes, step=5)
            save_hand_area = st.form_submit_button("Save hand-labor rates", type="primary")
        if save_hand_area:
            try:
                repository.update_hand_labor_area(hand_area.id, organization_id=organization_id, facility_id=facility_id, default_crew_size=int(hand_crew), sticker_units_per_person_hour=float(sticker_rate), case_pack_units_per_person_hour=float(case_rate), final_cases_per_person_hour=float(final_case_rate), setup_minutes=int(hand_setup), cleanup_minutes=int(hand_cleanup), actor=_actor())
                st.success("Hand-labor rates were saved.")
                st.rerun()
            except Exception as exc:
                st.error(f"Hand-labor rates could not be saved: {exc}")

    with planning_tab:
        st.markdown("#### Crew availability")
        with st.form("coman_crew_availability_form", clear_on_submit=True):
            crew1, crew2, crew3, crew4 = st.columns(4)
            crew_date = crew1.date_input("Work date", value=date.today())
            crew_shift = crew2.selectbox("Shift", ["Day", "Evening", "Night", "Weekend"])
            available_people = crew3.number_input("People available", min_value=0, value=1, step=1)
            crew_shift_hours = crew4.number_input("Shift hours", min_value=1.0, value=8.0, step=0.5)
            crew_notes = st.text_input("Crew notes", placeholder="Callouts, training, restricted assignments")
            save_crew = st.form_submit_button("Save crew capacity", type="primary")
        if save_crew:
            try:
                repository.set_crew_availability(organization_id=organization_id, facility_id=facility_id, work_date=crew_date, shift_name=crew_shift, available_people=int(available_people), shift_hours=float(crew_shift_hours), actor=_actor(), notes=crew_notes)
                st.success("Crew availability saved.")
                st.rerun()
            except Exception as exc:
                st.error(f"Crew availability could not be saved: {exc}")
        if crew_availability:
            st.dataframe(pd.DataFrame([{"Date": record.work_date, "Shift": record.shift_name, "People": record.available_people, "Hours": record.shift_hours, "Available Labor-Hours": record.available_people * record.shift_hours, "Notes": record.notes} for record in crew_availability]), width="stretch", hide_index=True)

        st.markdown("#### Machine capacity estimate")
        if not open_orders or not facility_machines:
            st.info("Add at least one production order and one facility machine to calculate capacity.")
        else:
            order_options = {
                f"{order.order_number} â€” {order.product_name} ({order.requested_units:,} units)": order
                for order in open_orders
            }
            machine_options = {
                f"{machine.asset_code} â€” {machine.display_name}": machine
                for machine in facility_machines
            }
            col1, col2, col3 = st.columns(3)
            planning_order = order_options[col1.selectbox("Production order", list(order_options))]
            planning_machine = machine_options[col2.selectbox("Facility machine", list(machine_options))]
            shift_hours = col3.number_input("Shift length (hours)", min_value=1.0, value=8.0, step=0.5)
            estimate = estimate_machine_job(
                planning_order.requested_units,
                planning_machine.effective_rate,
                planning_machine.preferred_crew_size,
                planning_machine.setup_minutes,
                planning_machine.cleanup_minutes,
                shift_hours,
            )
            results = st.columns(4)
            results[0].metric("Machine Run", f"{estimate['run_hours']:.1f} hr")
            results[1].metric("Elapsed Time", f"{estimate['elapsed_hours']:.1f} hr")
            results[2].metric("Labor Required", f"{estimate['labor_hours']:.1f} labor hr")
            results[3].metric("Shifts Required", int(estimate["shifts"]))
            st.caption(
                "This is a single-machine estimate using your observed rate. Labor routing for breakdown, "
                "weighing, tubing, stickering, casing, packing, QA, and sanitation comes next."
            )
            st.markdown("#### Required downstream hand labor")
            units_per_case = st.number_input("Finished units per final case", min_value=1, value=100, step=1)
            rates_ready = all([hand_area.sticker_units_per_person_hour > 0, hand_area.case_pack_units_per_person_hour > 0, hand_area.final_cases_per_person_hour > 0])
            if not rates_ready:
                st.warning("Configure all three observed rates in Hand Labor to include downstream completion time.")
            else:
                hand_estimate = estimate_hand_labor_job(planning_order.requested_units, hand_area.default_crew_size, hand_area.sticker_units_per_person_hour, hand_area.case_pack_units_per_person_hour, hand_area.final_cases_per_person_hour, int(units_per_case), hand_area.setup_minutes, hand_area.cleanup_minutes)
                hand_metrics = st.columns(4)
                hand_metrics[0].metric("Hand-Labor Elapsed", f"{hand_estimate['elapsed_hours']:.1f} hr")
                hand_metrics[1].metric("Hand Labor Required", f"{hand_estimate['labor_hours']:.1f} labor hr")
                hand_metrics[2].metric("Final Cases", int(hand_estimate["cases"]))
                hand_metrics[3].metric("Hand-Labor Bottleneck", str(hand_estimate["bottleneck"]))
                total_elapsed = float(estimate["elapsed_hours"]) + float(hand_estimate["elapsed_hours"])
                st.success(f"Estimated end-to-end completion time: {total_elapsed:.1f} hours, including the machine and required hand-labor stages.")
                if crew_availability:
                    selected_capacity = crew_availability[0]
                    available_labor_hours = selected_capacity.available_people * selected_capacity.shift_hours
                    required_labor_hours = float(estimate["labor_hours"]) + float(hand_estimate["labor_hours"])
                    delta = available_labor_hours - required_labor_hours
                    if delta >= 0:
                        st.success(f"Crew capacity check: {available_labor_hours:.1f} labor-hours available; {required_labor_hours:.1f} required.")
                    else:
                        st.warning(f"Crew shortage: {required_labor_hours:.1f} labor-hours required versus {available_labor_hours:.1f} available ({abs(delta):.1f} short).")
                else:
                    st.warning("Add crew availability above to check whether the scheduled shift can support this job.")

    with performance_tab:
        st.markdown("#### Record completed-job actuals")
        if not orders:
            st.info("Create a production order before recording performance.")
        else:
            performance_orders = {f"{order.order_number} â€” {order.product_name}": order for order in orders}
            with st.form("coman_actuals_form", clear_on_submit=True):
                actual_order_label = st.selectbox("Production order", list(performance_orders))
                actual_order = performance_orders[actual_order_label]
                col1, col2, col3 = st.columns(3)
                actual_units = col1.number_input("Good finished units", min_value=0, value=actual_order.requested_units, step=100)
                scrap_units = col2.number_input("Scrap units", min_value=0, value=0, step=1)
                rework_units = col3.number_input("Rework units", min_value=0, value=0, step=1)
                machine_hours = col1.number_input("Actual machine hours", min_value=0.0, value=0.0, step=0.25)
                labor_hours = col2.number_input("Actual labor-hours", min_value=0.0, value=0.0, step=0.25)
                actual_notes = st.text_area("Completion notes")
                save_actual = st.form_submit_button("Complete job and save actuals", type="primary")
            if save_actual:
                try:
                    repository.record_production_actual(actual_order.id, organization_id=organization_id, facility_id=facility_id, actual_units=int(actual_units), scrap_units=int(scrap_units), rework_units=int(rework_units), actual_machine_hours=float(machine_hours), actual_labor_hours=float(labor_hours), actor=_actor(), notes=actual_notes)
                    st.success("Actual performance saved and order marked complete.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Actual performance could not be saved: {exc}")
        if actuals:
            orders_by_id = {order.id: order for order in orders}
            performance_rows = []
            for actual in actuals:
                order = orders_by_id.get(actual.production_order_id)
                planned = order.requested_units if order else 0
                yield_pct = (actual.actual_units / planned * 100) if planned else 0
                performance_rows.append({"Order": order.order_number if order else actual.production_order_id, "Product": order.product_name if order else "Unknown", "Planned Units": planned, "Actual Units": actual.actual_units, "Attainment %": round(yield_pct, 1), "Scrap": actual.scrap_units, "Rework": actual.rework_units, "Machine Hours": actual.actual_machine_hours, "Labor Hours": actual.actual_labor_hours, "Completed": actual.completed_at})
            performance_df = pd.DataFrame(performance_rows)
            st.dataframe(performance_df, width="stretch", hide_index=True)
            summary = st.columns(4)
            summary[0].metric("Completed Jobs", len(performance_df))
            summary[1].metric("Average Attainment", f"{performance_df['Attainment %'].mean():.1f}%")
            summary[2].metric("Total Scrap", f"{performance_df['Scrap'].sum():,.0f}")
            summary[3].metric("Actual Labor-Hours", f"{performance_df['Labor Hours'].sum():,.1f}")

            st.markdown("#### Performance visuals")
            st.caption("Output, attainment, and hours use the app's orange, green, and blue accents.")
            chart_source = performance_df.copy()
            chart_source["Job"] = chart_source["Order"].astype(str) + " - " + chart_source["Product"].astype(str)
            output_long = chart_source.melt(id_vars=["Job"], value_vars=["Planned Units", "Actual Units"], var_name="Measure", value_name="Units")
            output_chart = (
                alt.Chart(output_long)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(
                    x=alt.X("Job:N", sort=None, title=None, axis=alt.Axis(labelAngle=-25)),
                    y=alt.Y("Units:Q", title="Finished units"),
                    color=alt.Color("Measure:N", scale=alt.Scale(domain=["Planned Units", "Actual Units"], range=["#ff9a3c", "#4cd388"]), legend=alt.Legend(orient="top", title=None)),
                    xOffset="Measure:N",
                    tooltip=["Job:N", "Measure:N", alt.Tooltip("Units:Q", format=",")],
                )
                .properties(height=310, title="Planned vs. actual output")
            )
            attainment_chart = (
                alt.Chart(chart_source)
                .mark_bar(cornerRadiusEnd=5)
                .encode(
                    y=alt.Y("Job:N", sort="-x", title=None),
                    x=alt.X("Attainment %:Q", title="Attainment %"),
                    color=alt.condition("datum['Attainment %'] >= 100", alt.value("#4cd388"), alt.value("#ff9a3c")),
                    tooltip=["Job:N", alt.Tooltip("Attainment %:Q", format=".1f")],
                )
                .properties(height=max(220, len(chart_source) * 38), title="Job attainment")
            )
            hours_long = chart_source.melt(id_vars=["Job"], value_vars=["Machine Hours", "Labor Hours"], var_name="Hour Type", value_name="Hours")
            hours_chart = (
                alt.Chart(hours_long)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(
                    x=alt.X("Job:N", sort=None, title=None, axis=alt.Axis(labelAngle=-25)),
                    y=alt.Y("Hours:Q", title="Hours"),
                    color=alt.Color("Hour Type:N", scale=alt.Scale(domain=["Machine Hours", "Labor Hours"], range=["#5aa8ff", "#4cd388"]), legend=alt.Legend(orient="top", title=None)),
                    xOffset="Hour Type:N",
                    tooltip=["Job:N", "Hour Type:N", alt.Tooltip("Hours:Q", format=".1f")],
                )
                .properties(height=310, title="Machine and labor hours")
            )
            chart_theme = {
                "background": "transparent",
                "axis": {"labelColor": "#b8b8b8", "titleColor": "#ffffff", "gridColor": "#343434"},
                "legend": {"labelColor": "#b8b8b8", "titleColor": "#ffffff"},
                "title": {"color": "#ffffff", "fontSize": 16, "anchor": "start"},
                "view": {"stroke": "transparent"},
            }
            visual1, visual2 = st.columns(2)
            visual1.altair_chart(output_chart.configure(**chart_theme), width="stretch")
            visual2.altair_chart(attainment_chart.configure(**chart_theme), width="stretch")
            st.altair_chart(hours_chart.configure(**chart_theme), width="stretch")

