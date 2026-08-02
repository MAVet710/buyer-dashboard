"""Streamlit UI for white-label and retail flower repack planning."""

from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from modules.repack.logic import grams_from_unit


def render_white_label_repack_workspace():
    st.markdown("## White Label / Repack")
    st.caption("Operational and compliance tracking for private-label/repack flower workflows. Not legal advice.")

    default_retail_price_map = {1.0: 10.0, 3.5: 25.0, 7.0: 45.0, 14.0: 80.0, 28.0: 140.0}
    default_plan = [
        {"enabled": False, "package_size_g": 1.0, "allocation_pct": 0.0, "bag_or_container_cost_per_unit": 0.12, "label_cost_per_unit": 0.05, "tamper_seal_cost_per_unit": 0.0, "humidity_pack_cost_per_unit": 0.0, "compliance_sticker_cost_per_unit": 0.0, "other_packaging_cost_per_unit": 0.0, "target_retail_price_per_unit": default_retail_price_map[1.0]},
        {"enabled": True, "package_size_g": 3.5, "allocation_pct": 50.0, "bag_or_container_cost_per_unit": 0.18, "label_cost_per_unit": 0.05, "tamper_seal_cost_per_unit": 0.0, "humidity_pack_cost_per_unit": 0.0, "compliance_sticker_cost_per_unit": 0.0, "other_packaging_cost_per_unit": 0.0, "target_retail_price_per_unit": default_retail_price_map[3.5]},
        {"enabled": True, "package_size_g": 7.0, "allocation_pct": 25.0, "bag_or_container_cost_per_unit": 0.24, "label_cost_per_unit": 0.05, "tamper_seal_cost_per_unit": 0.0, "humidity_pack_cost_per_unit": 0.0, "compliance_sticker_cost_per_unit": 0.0, "other_packaging_cost_per_unit": 0.0, "target_retail_price_per_unit": default_retail_price_map[7.0]},
        {"enabled": True, "package_size_g": 14.0, "allocation_pct": 15.0, "bag_or_container_cost_per_unit": 0.32, "label_cost_per_unit": 0.05, "tamper_seal_cost_per_unit": 0.0, "humidity_pack_cost_per_unit": 0.0, "compliance_sticker_cost_per_unit": 0.0, "other_packaging_cost_per_unit": 0.0, "target_retail_price_per_unit": default_retail_price_map[14.0]},
        {"enabled": True, "package_size_g": 28.0, "allocation_pct": 10.0, "bag_or_container_cost_per_unit": 0.45, "label_cost_per_unit": 0.05, "tamper_seal_cost_per_unit": 0.0, "humidity_pack_cost_per_unit": 0.0, "compliance_sticker_cost_per_unit": 0.0, "other_packaging_cost_per_unit": 0.0, "target_retail_price_per_unit": default_retail_price_map[28.0]},
        {"enabled": False, "package_size_g": 0.0, "allocation_pct": 0.0, "bag_or_container_cost_per_unit": 0.2, "label_cost_per_unit": 0.05, "tamper_seal_cost_per_unit": 0.0, "humidity_pack_cost_per_unit": 0.0, "compliance_sticker_cost_per_unit": 0.0, "other_packaging_cost_per_unit": 0.0, "target_retail_price_per_unit": 0.0},
    ]
    st.session_state.setdefault("white_label_saved_scenarios", {})
    st.session_state.setdefault("white_label_active_scenario_name", "Current Session")
    st.session_state.setdefault("white_label_package_plan", default_plan)

    scenario_name = st.text_input("Scenario Name", value=st.session_state.get("white_label_active_scenario_name", "Current Session"))
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        if st.button("Save Scenario", key="wl_save"):
            st.session_state["white_label_saved_scenarios"][scenario_name] = {k: v for k, v in st.session_state.items() if k.startswith("wl_")}
            st.session_state["white_label_saved_scenarios"][scenario_name]["white_label_package_plan"] = st.session_state.get("white_label_package_plan", default_plan)
            st.success(f"Saved scenario: {scenario_name}")
    with s2:
        names = ["Current Session"] + sorted(st.session_state["white_label_saved_scenarios"].keys())
        load_name = st.selectbox("Load Scenario", names, key="wl_load_name")
    with s3:
        if st.button("Duplicate Scenario", key="wl_duplicate"):
            src = st.session_state["white_label_saved_scenarios"].get(load_name)
            if src:
                dup_name = f"{load_name} Copy"
                st.session_state["white_label_saved_scenarios"][dup_name] = dict(src)
                st.success(f"Duplicated as {dup_name}")
    with s4:
        if st.button("Clear Scenario", key="wl_clear"):
            for key in [k for k in list(st.session_state.keys()) if k.startswith("wl_")]:
                del st.session_state[key]
            st.session_state["white_label_package_plan"] = default_plan
            st.success("Cleared scenario values for current session.")

    if load_name != "Current Session" and st.button("Apply Loaded Scenario", key="wl_apply_load"):
        payload = st.session_state["white_label_saved_scenarios"].get(load_name, {})
        for key, val in payload.items():
            st.session_state[key] = val
        st.success(f"Loaded {load_name}")

    tabs = st.tabs(["Step 1: Bulk Lot", "Step 2: Costs", "Step 3: Package Plan", "Step 4: Results", "Step 5: Compliance"])
    with tabs[0]:
        st.info("Start with the bulk flower lot you are considering buying or repacking.")
        strain_name = st.text_input("Strain Name *", key="wl_strain_name")
        strain_type = st.selectbox("Strain Type *", ["Indica", "Sativa", "Hybrid", "CBD", "Mixed", "Unknown"], key="wl_strain_type")
        cultivator_name = st.text_input("Cultivator Name *", key="wl_cultivator_name")
        vendor_name = st.text_input("Vendor Name *", key="wl_vendor_name")
        c1, c2 = st.columns(2)
        bulk_weight_value = c1.number_input("Bulk Weight *", min_value=0.0, value=0.0, key="wl_bulk_weight_value")
        bulk_weight_unit = c2.selectbox("Weight Unit *", ["g", "oz", "lb"], key="wl_bulk_weight_unit")
        bulk_total_cost_usd = st.number_input("Total Bulk Cost ($) *", min_value=0.0, value=0.0, key="wl_bulk_total_cost_usd")
        coa_link = st.text_input("Certificate of Analysis (COA) Link *", key="wl_coa_link")
        thca_pct = st.number_input("THCA (%) *", min_value=0.0, max_value=100.0, value=0.0, key="wl_thca_pct")
        terpene_pct = st.number_input("Terpenes (%) *", min_value=0.0, max_value=100.0, value=0.0, key="wl_terpene_pct")
        with st.expander("Advanced Lot Details"):
            cultivator_license_number = st.text_input("Cultivator License Number", key="wl_cultivator_license_number")
            source_metrc_package_id = st.text_input("Source METRC Package ID", key="wl_source_metrc_package_id")
            batch_or_lot_number = st.text_input("Batch or Lot Number", key="wl_batch_or_lot_number")
            harvest_date = st.date_input("Harvest Date", value=datetime.now().date(), key="wl_harvest_date")
            testing_date = st.date_input("Testing Date", value=datetime.now().date(), key="wl_testing_date")
            received_date = st.date_input("Received Date", value=datetime.now().date(), key="wl_received_date")
            total_thc_pct = st.number_input("Total THC (%)", min_value=0.0, max_value=100.0, value=0.0, key="wl_total_thc_pct")
            moisture_pct = st.number_input("Moisture (%)", min_value=0.0, max_value=100.0, value=0.0, key="wl_moisture_pct")
            testing_notes = st.text_area("Testing Notes", key="wl_testing_notes")
            buyer_notes = st.text_area("Buyer Notes", key="wl_buyer_notes")
            compliance_notes = st.text_area("Compliance Notes", key="wl_compliance_notes")

    with tabs[1]:
        st.info("Add the costs that change the true landed cost of the flower.")
        discount_pct = st.number_input("Purchase Discount (%)", min_value=0.0, max_value=100.0, value=0.0, key="wl_discount_pct")
        shrink_loss_pct = st.number_input("Expected Shrink Loss (%)", min_value=0.0, max_value=100.0, value=0.0, key="wl_shrink_loss_pct")
        labor_cost_total_usd = st.number_input("Total Labor Cost ($)", min_value=0.0, value=0.0, key="wl_labor_cost_total_usd")
        other_costs_usd = st.number_input("Other Costs ($)", min_value=0.0, value=0.0, key="wl_other_costs_usd")
        with st.expander("Advanced Costs"):
            freight_or_delivery_cost_usd = st.number_input("Freight or Delivery Cost ($)", min_value=0.0, value=0.0, key="wl_freight_or_delivery_cost_usd")
            sample_or_testing_cost_usd = st.number_input("Sampling or Testing Cost ($)", min_value=0.0, value=0.0, key="wl_sample_or_testing_cost_usd")
            compliance_admin_cost_usd = st.number_input("Compliance Administration Cost ($)", min_value=0.0, value=0.0, key="wl_compliance_admin_cost_usd")
            qa_hold_loss_pct = st.number_input("QA Hold Loss (%)", min_value=0.0, max_value=100.0, value=0.0, key="wl_qa_hold_loss_pct")
            trim_loss_pct = st.number_input("Trim Loss (%)", min_value=0.0, max_value=100.0, value=0.0, key="wl_trim_loss_pct")
            moisture_loss_pct = st.number_input("Moisture Loss (%)", min_value=0.0, max_value=100.0, value=0.0, key="wl_moisture_loss_pct")

    total_g = grams_from_unit(st.session_state.get("wl_bulk_weight_value", 0.0), st.session_state.get("wl_bulk_weight_unit", "g"))
    landed_cost_usd = max(0.0, st.session_state.get("wl_bulk_total_cost_usd", 0.0) * (1 - st.session_state.get("wl_discount_pct", 0.0) / 100.0) + st.session_state.get("wl_freight_or_delivery_cost_usd", 0.0) + st.session_state.get("wl_sample_or_testing_cost_usd", 0.0))
    total_loss_pct = min(100.0, st.session_state.get("wl_shrink_loss_pct", 0.0) + st.session_state.get("wl_trim_loss_pct", 0.0) + st.session_state.get("wl_qa_hold_loss_pct", 0.0) + st.session_state.get("wl_moisture_loss_pct", 0.0))
    usable_weight_g = max(0.0, total_g * (1 - total_loss_pct / 100.0))
    effective_cost_per_gram = landed_cost_usd / usable_weight_g if usable_weight_g > 0 else 0.0

    with tabs[2]:
        st.info("Choose how much of the lot goes into each package size. Packaging costs can vary by size.")
        plan_df = pd.DataFrame(st.session_state.get("white_label_package_plan", default_plan))
        plan_df["bag_or_container_cost_per_unit"] = plan_df.get("bag_or_container_cost_per_unit", plan_df.get("bag_cost_per_unit", 0.0))
        for col in ["tamper_seal_cost_per_unit", "humidity_pack_cost_per_unit", "compliance_sticker_cost_per_unit", "other_packaging_cost_per_unit"]:
            if col not in plan_df.columns:
                plan_df[col] = 0.0
        plan_df["total_packaging_cost_per_unit"] = (
            plan_df["bag_or_container_cost_per_unit"].fillna(0.0)
            + plan_df["label_cost_per_unit"].fillna(0.0)
            + plan_df["tamper_seal_cost_per_unit"].fillna(0.0)
            + plan_df["humidity_pack_cost_per_unit"].fillna(0.0)
            + plan_df["compliance_sticker_cost_per_unit"].fillna(0.0)
            + plan_df["other_packaging_cost_per_unit"].fillna(0.0)
        )
        simple_mode = st.toggle("Simple Mode", value=st.session_state.get("wl_simple_mode", True), key="wl_simple_mode")
        primary_cols = ["enabled", "package_size_g", "allocation_pct", "target_retail_price_per_unit", "total_packaging_cost_per_unit"]
        edited = st.data_editor(plan_df[primary_cols], width="stretch", num_rows="dynamic", key="wl_package_editor")
        detail_cols = ["enabled", "package_size_g", "bag_or_container_cost_per_unit", "label_cost_per_unit", "tamper_seal_cost_per_unit", "humidity_pack_cost_per_unit", "compliance_sticker_cost_per_unit", "other_packaging_cost_per_unit"]
        if not simple_mode:
            with st.expander("Packaging Cost Details", expanded=False):
                details_edited = st.data_editor(plan_df[detail_cols], width="stretch", num_rows="dynamic", key="wl_packaging_detail_editor")
        else:
            details_edited = plan_df[detail_cols]
        merged = edited.merge(details_edited, on=["enabled", "package_size_g"], how="left", suffixes=("", "_detail"))
        st.session_state["white_label_package_plan"] = merged.to_dict("records")
        alloc_total = float(edited.loc[edited["enabled"], "allocation_pct"].sum()) if not edited.empty else 0.0
        if alloc_total > 100:
            st.warning("Your package allocation is over 100%.")
        elif alloc_total < 100:
            st.warning(f"You still have {100 - alloc_total:.1f}% unallocated.")
        if usable_weight_g < 0:
            st.warning("Usable grams cannot be negative.")

    enabled_df = pd.DataFrame(st.session_state.get("white_label_package_plan", default_plan))
    if not enabled_df.empty:
        enabled_df = enabled_df[enabled_df["enabled"] == True].copy()

    rows=[]
    for _,r in enabled_df.iterrows():
        size=float(r.get("package_size_g",0) or 0)
        alloc_pct=float(r.get("allocation_pct",0) or 0)
        bag=float(r.get("bag_or_container_cost_per_unit",r.get("bag_cost_per_unit",0)) or 0)
        label=float(r.get("label_cost_per_unit",0) or 0)
        tamper=float(r.get("tamper_seal_cost_per_unit",0) or 0)
        humidity=float(r.get("humidity_pack_cost_per_unit",0) or 0)
        compliance=float(r.get("compliance_sticker_cost_per_unit",0) or 0)
        other_pack=float(r.get("other_packaging_cost_per_unit",r.get("additional_packaging_cost_per_unit",0)) or 0)
        price=float(r.get("target_retail_price_per_unit",0) or 0)
        missing_inputs=[]
        if price <= 0: missing_inputs.append("Retail price missing")
        if bag < 0 or label < 0 or tamper < 0 or humidity < 0 or compliance < 0 or other_pack < 0: missing_inputs.append("Packaging cost missing")
        if alloc_pct <= 0: missing_inputs.append("Allocation missing")
        if landed_cost_usd <= 0: missing_inputs.append("Bulk cost missing")
        if size<=0:
            missing_inputs.append("Package size missing")
            st.warning("Enabled package rows must have package_size_g > 0.")
            continue
        alloc_g=usable_weight_g*(alloc_pct/100.0)
        units=int(np.floor(alloc_g/size))
        leftover=max(0.0,alloc_g-(units*size))
        if leftover>0: st.info("This package size produces leftover grams.")
        total_packaging_unit=max(0.0, bag + label + tamper + humidity + compliance + other_pack)
        total_packaging_cost=units*total_packaging_unit
        revenue=(units*price) if not missing_inputs else np.nan
        bulk_cost=units*size*effective_cost_per_gram
        unit_other=(st.session_state.get("wl_labor_cost_total_usd",0)+st.session_state.get("wl_other_costs_usd",0)+st.session_state.get("wl_compliance_admin_cost_usd",0))/max(1,len(enabled_df))
        all_in=bulk_cost+total_packaging_cost+unit_other
        profit=(revenue-all_in) if not missing_inputs else np.nan
        margin=((profit/revenue*100.0) if revenue and revenue>0 else np.nan) if not missing_inputs else np.nan
        break_even=(all_in/units) if units>0 and not missing_inputs else np.nan
        status = "Complete" if not missing_inputs else "Incomplete"
        strain_name = str(st.session_state.get("wl_strain_name") or "Repack Product").strip()
        product_name = f"{strain_name} Flower {size:g}g"
        rows.append({"Product Name":product_name,"Package Size":f"{size:g}g","Allocation %":alloc_pct,"Grams Allocated":alloc_g,"Units Produced":units,"Retail Price":(price if price>0 else np.nan),"Total Packaging / Unit":total_packaging_unit,"Total Packaging Cost":total_packaging_cost,"All-In Cost / Unit":(all_in/units if units>0 else np.nan),"Break-even Price":break_even,"Revenue":revenue,"Gross Profit":profit,"Gross Margin %":margin,"Status":status,"Missing Inputs":", ".join(missing_inputs) if missing_inputs else ""})
    results_df=pd.DataFrame(rows)
    total_units=int(results_df["Units Produced"].sum()) if not results_df.empty else 0
    total_revenue=float(results_df["Revenue"].fillna(0).sum()) if not results_df.empty else 0
    total_packaging=float(results_df["Total Packaging Cost"].fillna(0).sum()) if not results_df.empty else 0
    total_all_in=float((results_df["All-In Cost / Unit"].fillna(0)*results_df["Units Produced"]).sum()) if not results_df.empty else 0
    gross_profit=total_revenue-total_all_in
    gross_margin=(gross_profit/total_revenue*100.0) if total_revenue>0 else 0
    leftover_total=max(0.0, usable_weight_g - float(results_df["Grams Allocated"].sum()) if not results_df.empty else usable_weight_g)

    margin_readiness = {}
    with tabs[3]:
        st.info("Review estimated units, revenue, profit, and margin.")
        k=st.columns(5)
        k[0].metric("Usable Weight", f"{usable_weight_g:,.1f} g")
        k[1].metric("Total Units", f"{total_units:,}")
        k[2].metric("Total Revenue", f"${total_revenue:,.0f}")
        k[3].metric("Gross Profit", f"${gross_profit:,.0f}")
        k[4].metric("Gross Margin %", f"{gross_margin:.1f}%")
        st.metric("Leftover Grams", f"{leftover_total:,.1f} g")
        if not results_df.empty:
            st.metric("Best Package Size by Margin", str(results_df.sort_values("Gross Margin %", ascending=False).iloc[0]["Package Size"]))
        if not results_df.empty:
            readiness = {
                "complete_rows": int((results_df["Status"] == "Complete").sum()),
                "incomplete_rows": int((results_df["Status"] == "Incomplete").sum()),
                "missing_retail_price_count": int(results_df["Missing Inputs"].str.contains("Retail price missing", na=False).sum()),
                "missing_packaging_cost_count": int(results_df["Missing Inputs"].str.contains("Packaging cost missing", na=False).sum()),
                "total_allocation_pct": float(results_df["Allocation %"].sum()),
                "unallocated_grams": float(leftover_total),
            }
            st.markdown("#### Margin Readiness")
            st.json(readiness)
            margin_readiness = readiness
            if readiness["incomplete_rows"] > 0:
                st.warning("Some margins are incomplete because required inputs are missing.")
        display_df = results_df.replace({np.nan: "N/A"})
        st.dataframe(display_df, width="stretch")
        if not results_df.empty:
            st.bar_chart(results_df.set_index("Package Size")["Revenue"])
            st.bar_chart(results_df.set_index("Package Size")["Gross Profit"])
            st.bar_chart(results_df.set_index("Package Size")["Gross Margin %"])

    with tabs[4]:
        st.info("Check whether the lot has the documentation needed before launch.")
        checklist = [
            ("COA Link Present", "Ready" if st.session_state.get("wl_coa_link") else "Missing"),
            ("COA Status Passed", "Ready" if st.session_state.get("wl_coa_status", "Needs Review") == "Passed" else "Needs Review"),
            ("THCA / Cannabinoid Data Present", "Ready" if st.session_state.get("wl_thca_pct", 0) > 0 or st.session_state.get("wl_total_thc_pct", 0) > 0 else "Missing"),
            ("Terpene Data Present", "Ready" if st.session_state.get("wl_terpene_pct", 0) > 0 else "Needs Review"),
            ("Cultivator Name Present", "Ready" if st.session_state.get("wl_cultivator_name") else "Missing"),
            ("Cultivator License Present", "Ready" if st.session_state.get("wl_cultivator_license_number") else "Missing"),
            ("Source METRC Package ID Present", "Ready" if st.session_state.get("wl_source_metrc_package_id") else "Missing"),
            ("Batch/Lot Number Present", "Ready" if st.session_state.get("wl_batch_or_lot_number") else "Missing"),
            ("Harvest Date Present", "Ready" if st.session_state.get("wl_harvest_date") else "Missing"),
            ("Testing Date Present", "Ready" if st.session_state.get("wl_testing_date") else "Missing"),
            ("Label Review Completed", "Ready" if st.session_state.get("wl_label_review_status", "Needs Review") == "Ready" else "Needs Review"),
        ]
        cdf = pd.DataFrame(checklist, columns=["Requirement", "Status"])
        st.dataframe(cdf, width="stretch")

    return {"scenario_name": scenario_name or "Current Session", "summary": {"strain_name": st.session_state.get("wl_strain_name", ""), "source_metrc_package_id": st.session_state.get("wl_source_metrc_package_id", ""), "landed_cost_usd": landed_cost_usd, "total_revenue_usd": total_revenue, "gross_profit_usd": gross_profit, "gross_margin_pct": gross_margin, "coa_link": st.session_state.get("wl_coa_link", "")}, "bulk_lot_details": {k:v for k,v in st.session_state.items() if k.startswith("wl_")}, "package_plan": st.session_state.get("white_label_package_plan", default_plan), "package_output_summary": results_df, "margin_readiness": margin_readiness, "cost_breakdown": pd.DataFrame([{"Cost Type":"Landed Cost","Total Cost":landed_cost_usd,"Cost per Gram":effective_cost_per_gram,"Cost per Unit":(total_all_in/max(1,total_units))},{"Cost Type":"Packaging+Label","Total Cost":total_packaging,"Cost per Gram":(total_packaging/max(1,usable_weight_g)),"Cost per Unit":(total_packaging/max(1,total_units))},{"Cost Type":"Labor","Total Cost":st.session_state.get("wl_labor_cost_total_usd",0.0),"Cost per Gram":(st.session_state.get("wl_labor_cost_total_usd",0.0)/max(1,usable_weight_g)),"Cost per Unit":(st.session_state.get("wl_labor_cost_total_usd",0.0)/max(1,total_units))}]), "compliance_checklist": cdf}
