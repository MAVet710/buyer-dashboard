"""Streamlit workspace for durable co-manufacturing intake and tracking."""

from __future__ import annotations

from datetime import date, datetime, time

import altair as alt
import pandas as pd
import streamlit as st

from reports.coman_report import _build_coman_executive_report_pdf

from .db import ComanDatabaseConfigurationError, create_coman_engine
from .order_prefill import build_recommended_order_prefill
from .planning import (
    estimate_hand_labor_job,
    estimate_machine_job,
    recommend_weight_allocation,
    weight_to_grams,
)
from .repository import ComanRepository


PRODUCT_FORMATS = [
    "Pouched flower — 3.5 g",
    "Pouched flower — 7 g",
    "Pouched flower — 14 g",
    "Pouched flower — 1 oz (28 g)",
    "Jarred flower",
    "Pre-roll",
    "Pre-roll pack",
    "Infused pre-roll",
    "Infused pre-roll pack",
    "Other",
]

ORDER_WIDGET_KEYS = {
    "order_number": "coman_order_number_input",
    "work_type": "coman_order_work_type_input",
    "requested_units": "coman_order_units_input",
    "product_name": "coman_order_product_name_input",
    "product_format": "coman_order_product_format_input",
    "sku": "coman_order_sku_input",
    "due_date": "coman_order_due_date_input",
    "priority": "coman_order_priority_input",
    "source_lot": "coman_order_source_lot_input",
    "material_owner": "coman_order_material_owner_input",
    "packaging_owner": "coman_order_packaging_owner_input",
    "notes": "coman_order_notes_input",
}

DEFAULT_OPTIMIZER_PRODUCTS = [
    {"eligible": True, "product": "3.5 g flower pouch", "format": "Pouched flower — 3.5 g", "unit_size_g": 3.5, "revenue_per_unit": 18.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 0.75, "other_cost_per_unit": 0.10, "machine_units_per_hour": 900.0, "machine_crew": 3, "machine_cost_per_hour": 35.0, "units_per_case": 50, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "7 g flower pouch", "format": "Pouched flower — 7 g", "unit_size_g": 7.0, "revenue_per_unit": 32.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 0.85, "other_cost_per_unit": 0.12, "machine_units_per_hour": 750.0, "machine_crew": 3, "machine_cost_per_hour": 35.0, "units_per_case": 30, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "14 g flower pouch", "format": "Pouched flower — 14 g", "unit_size_g": 14.0, "revenue_per_unit": 58.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 0.95, "other_cost_per_unit": 0.15, "machine_units_per_hour": 600.0, "machine_crew": 3, "machine_cost_per_hour": 35.0, "units_per_case": 20, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "1 oz flower pouch", "format": "Pouched flower — 1 oz (28 g)", "unit_size_g": 28.0, "revenue_per_unit": 105.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 1.10, "other_cost_per_unit": 0.18, "machine_units_per_hour": 450.0, "machine_crew": 3, "machine_cost_per_hour": 35.0, "units_per_case": 12, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "3.5 g flower jar", "format": "Jarred flower", "unit_size_g": 3.5, "revenue_per_unit": 20.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 1.15, "other_cost_per_unit": 0.10, "machine_units_per_hour": 500.0, "machine_crew": 4, "machine_cost_per_hour": 25.0, "units_per_case": 48, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "1 g pre-roll", "format": "Pre-roll", "unit_size_g": 1.0, "revenue_per_unit": 6.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 0.35, "other_cost_per_unit": 0.08, "machine_units_per_hour": 1200.0, "machine_crew": 4, "machine_cost_per_hour": 45.0, "units_per_case": 100, "max_allocation_pct": 100.0},
    {"eligible": True, "product": "5-pack pre-roll", "format": "Pre-roll pack", "unit_size_g": 2.5, "revenue_per_unit": 16.0, "bulk_cost_per_g": 1.5, "packaging_cost_per_unit": 0.90, "other_cost_per_unit": 0.12, "machine_units_per_hour": 350.0, "machine_crew": 5, "machine_cost_per_hour": 45.0, "units_per_case": 40, "max_allocation_pct": 100.0},
]


_REPOSITORY_CACHE_VERSION = "inventory-bom-v1"


@st.cache_resource
def _repository(cache_version: str) -> ComanRepository:
    # The explicit version prevents Streamlit Cloud from reusing a repository
    # instance created from an older class definition during a hot deployment.
    del cache_version
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


def _actuals_frame(actuals, orders_by_id: dict[str, object]) -> pd.DataFrame:
    rows = []
    for actual in actuals:
        order = orders_by_id.get(actual.production_order_id)
        planned = order.requested_units if order else 0
        rows.append(
            {
                "Order": order.order_number if order else actual.production_order_id,
                "Product": order.product_name if order else "Unknown",
                "Planned Units": planned,
                "Actual Units": actual.actual_units,
                "Attainment %": round((actual.actual_units / planned * 100) if planned else 0, 1),
                "Scrap": actual.scrap_units,
                "Rework": actual.rework_units,
                "Machine Hours": actual.actual_machine_hours,
                "Labor Hours": actual.actual_labor_hours,
                "Completed": actual.completed_at,
            }
        )
    return pd.DataFrame(rows)


def _machines_frame(machines) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Asset": machine.asset_code,
                "Machine": machine.display_name,
                "Effective Rate": machine.effective_rate,
                "Rate Unit": machine.rate_unit,
                "Preferred Crew": machine.preferred_crew_size,
                "Setup Minutes": machine.setup_minutes,
                "Cleanup Minutes": machine.cleanup_minutes,
                "Active": machine.active,
            }
            for machine in machines
        ]
    )


def _crew_frame(crew_availability) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Date": record.work_date,
                "Shift": record.shift_name,
                "People": record.available_people,
                "Shift Hours": record.shift_hours,
                "Available Labor Hours": record.available_people * record.shift_hours,
                "Notes": record.notes,
            }
            for record in crew_availability
        ]
    )


def _customers_frame(customers) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Customer": customer.name,
                "License / Registration": customer.license_or_registration,
                "Contact": customer.contact_name,
                "Email": customer.contact_email,
                "Active": customer.active,
            }
            for customer in customers
        ]
    )


def render_coman_workspace() -> None:
    """Render the first usable Co-Man workflow against Supabase/PostgreSQL."""
    organization_id = st.session_state.get("active_organization_id")
    facility_id = st.session_state.get("active_facility_id")
    if not organization_id or not facility_id:
        st.warning("Select an organization and facility in the sidebar before entering Co-Man work.")
        return

    try:
        repository = _repository(_REPOSITORY_CACHE_VERSION)
        customers = repository.list_customers(organization_id)
        orders = repository.list_production_orders(organization_id, facility_id)
        machine_models = repository.list_machine_models()
        facility_machines = repository.list_facility_machines(organization_id, facility_id)
        hand_area = repository.ensure_primary_hand_labor_area(organization_id, facility_id)
        actuals = repository.list_production_actuals(organization_id, facility_id)
        crew_availability = repository.list_crew_availability(organization_id, facility_id, date.today())
        products = repository.list_products(organization_id)
        inventory_lots = repository.list_inventory_lots(organization_id, facility_id)
        inventory_transactions = repository.list_inventory_transactions(organization_id, facility_id)
        material_reservations = repository.list_material_reservations(organization_id, facility_id)
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

    overview_tab, orders_tab, planning_tab, resources_tab, inventory_tab, customers_tab, performance_tab = st.tabs(
        ["Dashboard", "New Job", "Schedule", "Resources", "Inventory & BOM", "Customers", "Performance"]
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
            order_actions = {f"{order.order_number} — {order.product_name}": order for order in orders}
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
                        "Profit/Input Lb": round(row["profit_per_input_lb"], 2…5986 tokens truncated…          st.success("Inventory movement posted.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Movement could not be posted: {exc}")

        with reservation_panel:
            st.markdown("##### Reserve material for a job")
            if not open_orders or not inventory_lots:
                st.caption("An open production order and an available lot are required.")
            else:
                reservation_orders = {f"{order.order_number} — {order.product_name}": order for order in open_orders}
                with st.form("coman_reservation_form", clear_on_submit=True):
                    reservation_order_label = st.selectbox("Production order", list(reservation_orders), key="coman_res_order")
                    reservation_lot_label = st.selectbox("Material lot", list(lot_options), key="coman_res_lot")
                    reservation_quantity = st.number_input("Quantity to reserve", min_value=0.01, value=1.0, step=1.0)
                    save_reservation = st.form_submit_button("Reserve material", type="primary")
                if save_reservation:
                    try:
                        selected_order = reservation_orders[reservation_order_label]
                        selected_lot = lot_options[reservation_lot_label]
                        selected_product = products_by_id[selected_lot.product_id]
                        repository.reserve_material(
                            organization_id,
                            facility_id,
                            production_order_id=selected_order.id,
                            lot_id=selected_lot.id,
                            quantity=float(reservation_quantity),
                            unit=selected_product.base_unit,
                            actor=_actor(),
                        )
                        st.success("Material reserved for the job.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Material could not be reserved: {exc}")

        st.markdown("#### Bill of materials")
        finished_products = [product for product in products if product.item_type in {"wip", "finished_good"}]
        component_products = [product for product in products if product.item_type in {"cannabis", "packaging", "wip"}]
        if not finished_products or not component_products:
            st.info("Add at least one finished-good or WIP product and one cannabis, packaging, or WIP component to build a BOM.")
        else:
            finished_options = {f"{product.sku} — {product.name}": product for product in finished_products}
            component_options = {f"{product.sku} — {product.name}": product for product in component_products}
            bom_col1, bom_col2, bom_col3 = st.columns(3)
            bom_output_label = bom_col1.selectbox("Finished product", list(finished_options), key="coman_bom_output")
            bom_output_quantity = bom_col2.number_input("Finished quantity", min_value=0.01, value=1.0, step=1.0, key="coman_bom_output_qty")
            bom_loss = bom_col3.number_input("Expected process loss %", min_value=0.0, value=0.0, step=0.5, key="coman_bom_loss")
            selected_component_labels = st.multiselect("Components", list(component_options), key="coman_bom_components")
            component_rows = []
            if selected_component_labels:
                component_columns = st.columns(min(3, len(selected_component_labels)))
                for index, label in enumerate(selected_component_labels):
                    component = component_options[label]
                    quantity = component_columns[index % len(component_columns)].number_input(
                        f"{component.sku} quantity ({component.base_unit})",
                        min_value=0.0001,
                        value=1.0,
                        step=0.1,
                        key=f"coman_bom_qty_{component.id}",
                    )
                    component_rows.append({"input_product_id": component.id, "quantity": float(quantity), "unit": component.base_unit})
            if st.button("Create BOM version", type="primary", disabled=not component_rows):
                try:
                    repository.create_bom(
                        organization_id,
                        output_product_id=finished_options[bom_output_label].id,
                        output_quantity=float(bom_output_quantity),
                        expected_loss_pct=float(bom_loss),
                        components=component_rows,
                        actor=_actor(),
                    )
                    st.success("BOM version created.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"BOM could not be created: {exc}")

        with st.expander("Inventory ledger", expanded=False):
            if not inventory_transactions:
                st.caption("No ledger entries yet.")
            else:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Time": entry.occurred_at,
                                "Lot": getattr(lots_by_id.get(entry.lot_id), "lot_code", entry.lot_id),
                                "Movement": entry.transaction_type.replace("_", " ").title(),
                                "Quantity": entry.quantity_delta,
                                "Unit": entry.unit,
                                "Reason": entry.reason,
                                "Reference": entry.reference,
                                "Actor": entry.actor,
                            }
                            for entry in inventory_transactions
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )

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
                f"{order.order_number} — {order.product_name} ({order.requested_units:,} units)": order
                for order in open_orders
            }
            machine_options = {
                f"{machine.asset_code} — {machine.display_name}": machine
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
            performance_orders = {f"{order.order_number} — {order.product_name}": order for order in orders}
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
        orders_by_id = {order.id: order for order in orders}
        performance_df = _actuals_frame(actuals, orders_by_id)
        if actuals:
            st.dataframe(performance_df, width="stretch", hide_index=True)
            summary = st.columns(4)
            summary[0].metric("Completed Jobs", len(performance_df))
            summary[1].metric("Average Attainment", f"{performance_df['Attainment %'].mean():.1f}%")
            summary[2].metric("Total Scrap", f"{performance_df['Scrap'].sum():,.0f}")
            summary[3].metric("Actual Labor-Hours", f"{performance_df['Labor Hours'].sum():,.1f}")

            st.markdown("#### Performance visuals")
            st.caption("Output, attainment, and hours use the same orange, green, and blue accents as the rest of the app.")
            chart_source = performance_df.copy()
            chart_source["Job"] = chart_source["Order"].astype(str) + " — " + chart_source["Product"].astype(str)
            output_long = chart_source.melt(
                id_vars=["Job"],
                value_vars=["Planned Units", "Actual Units"],
                var_name="Measure",
                value_name="Units",
            )
            output_chart = (
                alt.Chart(output_long)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(
                    x=alt.X("Job:N", sort=None, title=None, axis=alt.Axis(labelAngle=-25)),
                    y=alt.Y("Units:Q", title="Finished units"),
                    color=alt.Color(
                        "Measure:N",
                        scale=alt.Scale(
                            domain=["Planned Units", "Actual Units"],
                            range=["#ff9a3c", "#4cd388"],
                        ),
                        legend=alt.Legend(orient="top", title=None),
                    ),
                    xOffset="Measure:N",
                    tooltip=["Job:N", "Measure:N", alt.Tooltip("Units:Q", format=",")],
                )
                .properties(height=310, title="Planned vs. actual output")
            )
            attainment_chart = (
                alt.Chart(chart_source)
                .mark_bar(color="#ff9a3c", cornerRadiusEnd=5)
                .encode(
                    y=alt.Y("Job:N", sort="-x", title=None),
                    x=alt.X("Attainment %:Q", title="Attainment %", scale=alt.Scale(domain=[0, max(110, float(chart_source['Attainment %'].max()) + 10)])),
                    color=alt.condition("datum['Attainment %'] >= 100", alt.value("#4cd388"), alt.value("#ff9a3c")),
                    tooltip=["Job:N", alt.Tooltip("Attainment %:Q", format=".1f")],
                )
                .properties(height=max(220, len(chart_source) * 38), title="Job attainment")
            )
            hours_long = chart_source.melt(
                id_vars=["Job"],
                value_vars=["Machine Hours", "Labor Hours"],
                var_name="Hour Type",
                value_name="Hours",
            )
            hours_chart = (
                alt.Chart(hours_long)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(
                    x=alt.X("Job:N", sort=None, title=None, axis=alt.Axis(labelAngle=-25)),
                    y=alt.Y("Hours:Q", title="Hours"),
                    color=alt.Color(
                        "Hour Type:N",
                        scale=alt.Scale(domain=["Machine Hours", "Labor Hours"], range=["#5aa8ff", "#4cd388"]),
                        legend=alt.Legend(orient="top", title=None),
                    ),
                    xOffset="Hour Type:N",
                    tooltip=["Job:N", "Hour Type:N", alt.Tooltip("Hours:Q", format=".1f")],
                )
                .properties(height=310, title="Machine and labor hours")
            )
            app_chart_config = {
                "background": "transparent",
                "axis": {"labelColor": "#b8b8b8", "titleColor": "#ffffff", "gridColor": "#343434"},
                "legend": {"labelColor": "#b8b8b8", "titleColor": "#ffffff"},
                "title": {"color": "#ffffff", "fontSize": 16, "anchor": "start"},
                "view": {"stroke": "transparent"},
            }
            visual1, visual2 = st.columns(2)
            visual1.altair_chart(output_chart.configure(**app_chart_config), width="stretch")
            visual2.altair_chart(attainment_chart.configure(**app_chart_config), width="stretch")
            st.altair_chart(hours_chart.configure(**app_chart_config), width="stretch")

        st.markdown("#### Production Ops executive report")
        st.caption(
            "Exports the current Co-Man queue, completed-job performance, machines, crew capacity, and customers "
            "using the Production Ops report design."
        )
        coman_report_payload = {
            "organization": st.session_state.get("active_organization_name") or str(organization_id),
            "facility": st.session_state.get("active_facility_name") or str(facility_id),
            "reporting_period": f"Queue snapshot {datetime.now().strftime('%Y-%m-%d')}",
            "orders": _orders_frame(orders, customers_by_id),
            "actuals": performance_df,
            "machines": _machines_frame(facility_machines),
            "crew": _crew_frame(crew_availability),
            "customers": _customers_frame(customers),
        }
        coman_report_bytes = _build_coman_executive_report_pdf(coman_report_payload)
        st.session_state["production_ops_coman_report_bytes"] = coman_report_bytes
        st.download_button(
            "Export Production Ops Report",
            data=coman_report_bytes,
            file_name=f"production_ops_coman_report_{datetime.now().strftime('%Y-%m-%d')}.pdf",
            mime="application/pdf",
            key="coman_production_ops_report",
        )

