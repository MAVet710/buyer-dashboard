import pandas as pd
import streamlit as st

from views import buyer_perfect_view as old


def _apply_summary_filters(detail_view: pd.DataFrame):
    filtered = detail_view.copy()
    all_cats = sorted(
        filtered["subcategory"].astype(str).unique().tolist(),
        key=lambda c: (old.REB_CATEGORIES.index(str(c).lower()) if str(c).lower() in old.REB_CATEGORIES else len(old.REB_CATEGORIES), str(c).lower()),
    )
    all_sizes = sorted([str(x) for x in filtered["packagesize"].dropna().astype(str).unique().tolist()])
    all_strains = sorted([str(x) for x in filtered["strain_type"].dropna().astype(str).unique().tolist()])
    all_priorities = ["1 – Reorder ASAP", "2 – Watch Closely", "3 – Comfortable Cover", "4 – Dead Item"]

    f1, f2, f3 = st.columns(3)
    with f1:
        search = st.text_input("Search summary rows", key="buyer_summary_search", placeholder="Category, top product, type...")
    with f2:
        selected_cats = st.multiselect("Categories", all_cats, default=all_cats, key="buyer_summary_cats")
    with f3:
        selected_priorities = st.multiselect("Priorities", all_priorities, default=all_priorities, key="buyer_summary_priorities")

    f4, f5, f6 = st.columns(3)
    with f4:
        selected_sizes = st.multiselect("Package sizes", all_sizes, default=all_sizes, key="buyer_summary_sizes")
    with f5:
        selected_strains = st.multiselect("Strain / type", all_strains, default=all_strains, key="buyer_summary_strains")
    with f6:
        doh_band = st.selectbox("DOH filter", ["All", "0-7", "8-21", "22-60", "61-90", "90+"], key="buyer_summary_doh_band")

    if selected_cats:
        filtered = filtered[filtered["subcategory"].astype(str).isin(selected_cats)]
    if selected_priorities:
        filtered = filtered[filtered["reorderpriority"].astype(str).isin(selected_priorities)]
    if selected_sizes:
        filtered = filtered[filtered["packagesize"].astype(str).isin(selected_sizes)]
    if selected_strains:
        filtered = filtered[filtered["strain_type"].astype(str).isin(selected_strains)]

    if doh_band == "0-7":
        filtered = filtered[(filtered["daysonhand"] >= 0) & (filtered["daysonhand"] <= 7)]
    elif doh_band == "8-21":
        filtered = filtered[(filtered["daysonhand"] >= 8) & (filtered["daysonhand"] <= 21)]
    elif doh_band == "22-60":
        filtered = filtered[(filtered["daysonhand"] >= 22) & (filtered["daysonhand"] <= 60)]
    elif doh_band == "61-90":
        filtered = filtered[(filtered["daysonhand"] >= 61) & (filtered["daysonhand"] <= 90)]
    elif doh_band == "90+":
        filtered = filtered[filtered["daysonhand"] >= 90]

    if search.strip():
        q = search.strip().lower()
        mask = filtered["subcategory"].astype(str).str.lower().str.contains(q, na=False)
        if "top_products" in filtered.columns:
            mask |= filtered["top_products"].astype(str).str.lower().str.contains(q, na=False)
        mask |= filtered["strain_type"].astype(str).str.lower().str.contains(q, na=False)
        mask |= filtered["packagesize"].astype(str).str.lower().str.contains(q, na=False)
        filtered = filtered[mask]
    return filtered


def _apply_sku_filters(buyer_view_df: pd.DataFrame):
    filtered = buyer_view_df.copy()
    brand_opts = sorted([str(x) for x in filtered["brand_vendor"].dropna().astype(str).unique().tolist()]) if "brand_vendor" in filtered.columns else []
    cat_opts = sorted([str(x) for x in filtered["category"].dropna().astype(str).unique().tolist()]) if "category" in filtered.columns else []
    status_opts = ["⬛ No Stock", "⚠️ Expiring", "🔴 Reorder", "🟠 Overstock", "✅ Healthy"]

    s1, s2, s3 = st.columns(3)
    with s1:
        sku_search = st.text_input("Search SKU inventory", key="buyer_sku_search", placeholder="SKU, product, brand...")
    with s2:
        selected_brands = st.multiselect("Brand / vendor", brand_opts, default=brand_opts, key="buyer_sku_brands") if brand_opts else []
    with s3:
        selected_status = st.multiselect("Status", status_opts, default=status_opts, key="buyer_sku_status")

    s4, s5, s6 = st.columns(3)
    with s4:
        selected_cat = st.multiselect("Category", cat_opts, default=cat_opts, key="buyer_sku_cats") if cat_opts else []
    with s5:
        doh_band = st.selectbox("SKU DOH filter", ["All", "0-21", "22-60", "61-90", "90+"], key="buyer_sku_doh_band")
    with s6:
        sort_by = st.selectbox("Sort SKU view", ["DOH high to low", "DOH low to high", "Avg weekly sales", "On hand units", "Expiring soonest"], key="buyer_sku_sort")

    if selected_brands:
        filtered = filtered[filtered["brand_vendor"].astype(str).isin(selected_brands)]
    if selected_cat:
        filtered = filtered[filtered["category"].astype(str).isin(selected_cat)]
    if selected_status:
        filtered = filtered[filtered["status"].astype(str).isin(selected_status)]

    if doh_band == "0-21":
        filtered = filtered[(filtered["days_of_supply"] >= 0) & (filtered["days_of_supply"] <= 21)]
    elif doh_band == "22-60":
        filtered = filtered[(filtered["days_of_supply"] >= 22) & (filtered["days_of_supply"] <= 60)]
    elif doh_band == "61-90":
        filtered = filtered[(filtered["days_of_supply"] >= 61) & (filtered["days_of_supply"] <= 90)]
    elif doh_band == "90+":
        filtered = filtered[filtered["days_of_supply"] >= 90]

    if sku_search.strip():
        q = sku_search.strip().lower()
        mask = filtered["product_name"].astype(str).str.lower().str.contains(q, na=False)
        if "sku" in filtered.columns:
            mask |= filtered["sku"].astype(str).str.lower().str.contains(q, na=False)
        if "brand_vendor" in filtered.columns:
            mask |= filtered["brand_vendor"].astype(str).str.lower().str.contains(q, na=False)
        filtered = filtered[mask]

    if sort_by == "DOH high to low":
        filtered = filtered.sort_values("days_of_supply", ascending=False, na_position="last")
    elif sort_by == "DOH low to high":
        filtered = filtered.sort_values("days_of_supply", ascending=True, na_position="last")
    elif sort_by == "Avg weekly sales":
        filtered = filtered.sort_values("avg_weekly_sales", ascending=False, na_position="last")
    elif sort_by == "On hand units":
        filtered = filtered.sort_values("onhandunits", ascending=False, na_position="last")
    elif sort_by == "Expiring soonest" and "days_to_expire" in filtered.columns:
        filtered = filtered.sort_values("days_to_expire", ascending=True, na_position="last")
    return filtered


def render_buyer_perfect_view_v2():
    old.render_section_header("Buyer Dashboard", "v18 buyer filters upgraded. Summary and SKU inventory now support deeper filtering without changing the underlying buyer logic.")
    inv_raw_df = st.session_state.get(old.INV_RAW)
    sales_raw_df = st.session_state.get(old.SALES_RAW)
    if not isinstance(inv_raw_df, pd.DataFrame) or not isinstance(sales_raw_df, pd.DataFrame):
        st.warning("Inventory and Product Sales uploads are required. Use Inventory Prep first.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        doh_threshold = int(st.number_input("Target Days on Hand", 1, 60, 21, key="buyer_perfect_doh_v2"))
    with c2:
        velocity_adjustment = float(st.number_input("Velocity Adjustment", 0.01, 5.0, 0.5, key="buyer_perfect_velocity_v2"))
    with c3:
        date_diff = int(st.slider("Days in Sales Period", 7, 120, 60, key="buyer_perfect_days_v2"))

    try:
        detail, detail_product, inv_df, sales_detail_df = old._build_buyer_pipeline(inv_raw_df, sales_raw_df, doh_threshold, velocity_adjustment, date_diff)
    except Exception as exc:
        st.error(f"Could not build buyer pipeline: {exc}")
        return

    st.session_state["detail_cached_df"] = detail.copy()
    st.session_state[old.BUYER_READY] = detail_product.copy()
    st.session_state["detail_product_cached_df"] = detail_product.copy()

    total_units = int(pd.to_numeric(detail["unitssold"], errors="coerce").fillna(0).sum())
    reorder_asap = int((detail["reorderpriority"] == "1 – Reorder ASAP").sum())
    if "buyer_metric_filter" not in st.session_state:
        st.session_state["buyer_metric_filter"] = "All"

    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Units Sold (Granular Size-Level): {total_units}", key="buyer_perfect_units_btn_v2"):
            st.session_state["buyer_metric_filter"] = "All"
    with col2:
        if st.button(f"Reorder ASAP (Lines): {reorder_asap}", key="buyer_perfect_reorder_btn_v2"):
            st.session_state["buyer_metric_filter"] = "Reorder ASAP"

    detail_view = detail[detail["reorderpriority"] == "1 – Reorder ASAP"].copy() if st.session_state["buyer_metric_filter"] == "Reorder ASAP" else detail.copy()

    _dp = detail_product[["subcategory", "product_name", "strain_type", "packagesize", "unitssold"]].copy()
    _dp["unitssold"] = pd.to_numeric(_dp["unitssold"], errors="coerce").fillna(0)
    _dp_sorted = _dp.sort_values("unitssold", ascending=False)
    _top_products = _dp_sorted.groupby(["subcategory", "strain_type", "packagesize"], dropna=False, sort=False)["product_name"].apply(lambda x: ", ".join(x.astype(str).head(5).tolist())).reset_index().rename(columns={"product_name": "top_products"})
    _product_counts = _dp.groupby(["subcategory", "strain_type", "packagesize"], dropna=False)["product_name"].nunique().reset_index().rename(columns={"product_name": "product_count"})
    _prod_ctx_df = _top_products.merge(_product_counts, on=["subcategory", "strain_type", "packagesize"], how="left")
    detail_view = detail_view.merge(_prod_ctx_df, on=["subcategory", "strain_type", "packagesize"], how="left")
    detail_view["product_count"] = detail_view["product_count"].fillna(0).astype(int)
    detail_view["top_products"] = detail_view["top_products"].fillna("")

    st.markdown(f"*Current filter:* **{st.session_state['buyer_metric_filter']}**")
    st.markdown("### Summary Filters")
    detail_view = _apply_summary_filters(detail_view)
    selected_cats = sorted(detail_view["subcategory"].astype(str).unique().tolist())
    show_product_rows = st.checkbox("Show product-level rows", value=False, key="buyer_perfect_show_products_v2")

    top = st.columns(4)
    with top[0]:
        old.render_metric_card("Tracked Categories", f"{detail_view['subcategory'].nunique():,}")
    with top[1]:
        old.render_metric_card("Forecast Rows", f"{len(detail_view):,}")
    with top[2]:
        old.render_metric_card("Reorder ASAP", f"{int((detail_view['reorderpriority'] == '1 – Reorder ASAP').sum()):,}")
    with top[3]:
        old.render_metric_card("Product Rows", f"{len(detail_product):,}")

    cat_quick = detail_view.groupby("subcategory", dropna=False).agg(onhandunits=("onhandunits", "sum"), avgunitsperday=("avgunitsperday", "sum"), reorder_lines=("reorderpriority", lambda x: int((x == "1 – Reorder ASAP").sum()))).reset_index()
    cat_quick["category_dos"] = 0
    mask = cat_quick["avgunitsperday"] > 0
    cat_quick.loc[mask, "category_dos"] = (cat_quick.loc[mask, "onhandunits"] / cat_quick.loc[mask, "avgunitsperday"]).astype(int)
    st.markdown("### Category DOS (at a glance)")
    st.dataframe(cat_quick.sort_values(["reorder_lines", "category_dos"], ascending=[False, True]), use_container_width=True, hide_index=True)

    st.markdown("### Forecast Table")
    display_cols = [c for c in ["top_products", "mastercategory", "subcategory", "strain_type", "packagesize", "onhandunits", "unitssold", "avgunitsperday", "daysonhand", "reorderqty", "reorderpriority", "product_count"] if c in detail_view.columns]
    st.download_button("📥 Export Forecast Table (Excel)", data=old._build_export_bytes(detail_view[display_cols], "Forecast"), file_name="forecast_table.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="buyer_perfect_export_forecast_v2")
    st.dataframe(detail_view[display_cols], use_container_width=True, hide_index=True)

    if show_product_rows and not detail_product.empty:
        st.markdown("### 📦 Product-Level Rows")
        dpv = detail_product[detail_product["subcategory"].isin(selected_cats)].copy()
        if len(dpv) > old.PRODUCT_TABLE_DISPLAY_LIMIT:
            dpv = dpv.sort_values("unitssold", ascending=False).head(old.PRODUCT_TABLE_DISPLAY_LIMIT)
        prod_display_cols = [c for c in ["product_name", "subcategory", "strain_type", "packagesize", "brand_vendor", "sku", "onhandunits", "unitssold", "avgunitsperday", "daysonhand", "expiration_date"] if c in dpv.columns]
        st.dataframe(dpv[prod_display_cols], use_container_width=True, hide_index=True)

    st.markdown("### 📋 SKU Inventory Buyer View")
    vel_window = st.selectbox("Velocity window", [28, 56, 84], index=1, key="buyer_perfect_sku_vel_v2")
    buyer_view_df = old._build_sku_inventory_buyer_view(inv_df, sales_detail_df, vel_window)
    buyer_view_df = _apply_sku_filters(buyer_view_df)
    cols_order = [c for c in ["sku", "product_name", "brand_vendor", "category", "packagesize", "strain_type", "onhandunits", "avg_weekly_sales", "days_of_supply", "weeks_of_supply", "dollars_on_hand", "retail_dollars_on_hand", "expiration_date", "days_to_expire", "status"] if c in buyer_view_df.columns]
    t1, t2, t3, t4 = st.tabs(["📦 All Inventory", "🔴 Reorder", "🟠 Overstock", "⚠️ Expiring"])
    with t1:
        st.dataframe(buyer_view_df[cols_order], use_container_width=True, hide_index=True)
    with t2:
        st.dataframe(buyer_view_df[buyer_view_df["days_of_supply"] <= old.INVENTORY_REORDER_DOH_THRESHOLD][cols_order], use_container_width=True, hide_index=True)
    with t3:
        st.dataframe(buyer_view_df[buyer_view_df["days_of_supply"] >= old.INVENTORY_OVERSTOCK_DOH_THRESHOLD][cols_order], use_container_width=True, hide_index=True)
    with t4:
        if "days_to_expire" in buyer_view_df.columns:
            st.dataframe(buyer_view_df[buyer_view_df["days_to_expire"].notna() & (buyer_view_df["days_to_expire"] < old.INVENTORY_EXPIRING_SOON_DAYS)][cols_order], use_container_width=True, hide_index=True)
        else:
            st.info("No expiration date column detected in the inventory file.")

    st.markdown("### 🤖 Doobie Inventory Check")
    old._doobie_inventory_check(detail_view, detail_product)

    st.markdown("### 🧠 Doobie Buyer Brief")
    if st.button("Generate Doobie Buyer Brief", key="buyer_perfect_brief_v2"):
        run_buyer_doobie(detail_product, state="MA")
