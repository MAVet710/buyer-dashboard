"""One-screen production control center layered over existing Co-Man planning."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from modules.coman.db import create_coman_engine
from modules.coman.repository import ComanRepository

from .service import ProductionERPService


def _actor() -> str:
    return str(st.session_state.get("admin_user") or st.session_state.get("user_user") or "system")


def render_production_control() -> None:
    org = str(st.session_state.get("active_organization_id") or "")
    facility = str(st.session_state.get("active_facility_id") or "")
    if not org or not facility:
        st.info("Select an organization and facility first.")
        return
    service = ProductionERPService(create_coman_engine())
    rows = service.queue_summary(org, facility)
    st.markdown("## Production Control")
    st.caption("Plan, reserve, execute, QA and cost production from one queue.")
    if not rows:
        st.info("No production orders yet.")
        return
    frame = pd.DataFrame(rows)
    top = st.columns(4)
    top[0].metric("Open", int((~frame["Status"].isin(["Complete", "Cancelled"])).sum()))
    top[1].metric("QA Holds", int((frame["QA"] == "HOLD").sum()))
    top[2].metric("Planned Units", f"{frame['Planned'].sum():,.0f}")
    top[3].metric("Tracked COGS", f"${frame['COGS'].sum():,.0f}")
    st.dataframe(frame.drop(columns=["order_id"]), width="stretch", hide_index=True)
    labels = {f"{row['Order']} · {row['Product']} · {row['Attention']}": row["order_id"] for row in rows}
    selected = labels[st.selectbox("Open Production 360", list(labels), key="prod_control_order")]
    snap = service.order_360(org, facility, selected)
    order = snap["order"]
    st.markdown(f"### {order.order_number} · {order.product_name}")
    metrics = st.columns(4)
    metrics[0].metric("Attainment", f"{snap['attainment_pct']:.1f}%")
    metrics[1].metric("Reserved Lots", len(snap["reservations"]))
    metrics[2].metric("Outputs", len(snap["outputs"]))
    metrics[3].metric("COGS", f"${float(snap['cogs'].get('total',0)):,.2f}")

    with st.popover("Reserve BOM materials", use_container_width=True):
        if snap["requirements"]:
            st.dataframe(pd.DataFrame(snap["requirements"]), hide_index=True, width="stretch")
        else:
            st.caption("No active BOM requirements found.")
        if st.button("Reserve available lots", type="primary", key=f"prod_reserve_{order.id}", use_container_width=True):
            try:
                result = service.reserve_bom_materials(organization_id=org, facility_id=facility, order_id=order.id, actor=_actor())
                if result["shortages"]:
                    st.warning(f"Reservations saved; {len(result['shortages'])} material shortage(s) remain.")
                    st.dataframe(pd.DataFrame(result["shortages"]), hide_index=True, width="stretch")
                else:
                    st.success("BOM materials reserved.")
            except Exception as exc:
                st.error(str(exc))

    with st.popover("Record stage / actuals", use_container_width=True):
        event_type = st.selectbox("Event", ["started","measurement","rework","waste","hold","release","completed","note"], key=f"prod_event_{order.id}")
        c1, c2, c3 = st.columns(3)
        qty = c1.number_input("Qty", min_value=0.0, step=1.0, key=f"prod_qty_{order.id}")
        labor = c2.number_input("Labor h", min_value=0.0, step=0.25, key=f"prod_labor_{order.id}")
        machine = c3.number_input("Machine h", min_value=0.0, step=0.25, key=f"prod_machine_{order.id}")
        notes = st.text_input("Note", key=f"prod_note_{order.id}")
        if st.button("Record event", type="primary", key=f"prod_event_submit_{order.id}", use_container_width=True):
            service.record_event(organization_id=org, facility_id=facility, order_id=order.id, event_type=event_type, actor=_actor(), quantity=qty if qty else None, labor_hours=labor if labor else None, machine_hours=machine if machine else None, notes=notes)
            st.rerun()

    with st.popover("Outputs + QA", use_container_width=True):
        repo = ComanRepository(create_coman_engine())
        products = repo.list_products(org)
        if products:
            options = {f"{p.name} · {p.sku}": p for p in products if p.item_type in {"cannabis","wip","finished_good"}}
            chosen = options[st.selectbox("Output product", list(options), key=f"prod_output_product_{order.id}")]
            planned = st.number_input("Planned output", min_value=0.0, step=1.0, key=f"prod_output_planned_{order.id}")
            if st.button("Add output", key=f"prod_add_output_{order.id}"):
                service.add_output(organization_id=org, facility_id=facility, order_id=order.id, product_id=chosen.id, planned_quantity=planned, actor=_actor(), label=chosen.name, unit=chosen.base_unit)
                st.rerun()
        if snap["outputs"]:
            st.dataframe(pd.DataFrame([{"Output": o.label, "Planned": o.planned_quantity, "Actual": o.actual_quantity, "Status": o.status} for o in snap["outputs"]]), hide_index=True, width="stretch")
            out_map = {f"#{o.position} {o.label}": o for o in snap["outputs"]}
            selected_out = out_map[st.selectbox("Output", list(out_map), key=f"prod_qa_out_{order.id}")]
            actual = st.number_input("Actual qty", min_value=0.0, value=float(selected_out.actual_quantity or 0), key=f"prod_actual_{selected_out.id}")
            lot_code = st.text_input("Output lot code", value=f"{order.order_number}-{selected_out.position}", key=f"prod_lot_{selected_out.id}")
            if st.button("Post actual to quarantine", key=f"prod_actual_submit_{selected_out.id}"):
                service.record_output_actual(organization_id=org, facility_id=facility, output_id=selected_out.id, actual_quantity=actual, actor=_actor(), lot_code=lot_code)
                st.rerun()
            qa_event = st.selectbox("QA action", ["sample","pass","fail","hold","retest","remediation","release"], key=f"prod_qa_event_{selected_out.id}")
            result = st.selectbox("Result", ["pending","passed","failed","not_applicable"], key=f"prod_qa_result_{selected_out.id}")
            if st.button("Record QA", type="primary", key=f"prod_qa_submit_{selected_out.id}"):
                service.record_qa(organization_id=org, facility_id=facility, order_id=order.id, output_id=selected_out.id, event_type=qa_event, result=result, actor=_actor())
                st.rerun()

    with st.popover("Add COGS", use_container_width=True):
        category = st.selectbox("Category", ["material","labor","packaging","machine","overhead","waste","other"], key=f"prod_cost_cat_{order.id}")
        amount = st.number_input("Amount USD", min_value=0.0, step=1.0, key=f"prod_cost_amt_{order.id}")
        note = st.text_input("Cost note", key=f"prod_cost_note_{order.id}")
        if st.button("Post cost", type="primary", key=f"prod_cost_submit_{order.id}"):
            service.add_cost(organization_id=org, facility_id=facility, order_id=order.id, category=category, amount_usd=amount, actor=_actor(), notes=note)
            st.rerun()


def render_production_control_dialog() -> None:
    if hasattr(st, "dialog"):
        @st.dialog("Production Control", width="large")
        def _dialog() -> None:
            render_production_control()
        _dialog()
    else:
        render_production_control()
