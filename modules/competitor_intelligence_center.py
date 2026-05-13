from __future__ import annotations

from datetime import date, datetime
import os
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from reports.competitor_report import _build_competitor_intelligence_report_pdf
from services.menu_capture_assistant import MenuCaptureSession
from utils.dataframe_helpers import _safe_numeric_mean, _safe_numeric_series, _safe_numeric_sum


def _init_state() -> None:
    defaults = {
        "competitor_registry_df": pd.DataFrame(),
        "competitor_capture_session": None,
        "competitor_current_snapshot_id": "",
        "competitor_capture_rows_pending": pd.DataFrame(),
        "competitor_capture_menu_url": "",
        "competitor_capture_mode": "Embedded Viewer",
        "competitor_saved_snapshot_rows": pd.DataFrame(),
        "competitor_menu_snapshots_df": pd.DataFrame(),
        "competitor_price_comparison_df": pd.DataFrame(),
        "competitor_assortment_gap_df": pd.DataFrame(),
        "competitor_promo_df": pd.DataFrame(),
        "competitor_recommendations": [],
        "competitor_data_quality": {},
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_competitor_intelligence_center() -> None:
    _init_state()
    st.header("🕵️ Competitor Intelligence Center")
    tabs = st.tabs(["Overview", "Competitor Registry", "Menu Capture Assistant", "Snapshot Review", "Price Intelligence", "Assortment Gaps", "Promo Pressure", "Strategic Recommendations", "Export Report"])

    with tabs[0]:
        reg = st.session_state.competitor_registry_df if isinstance(st.session_state.competitor_registry_df, pd.DataFrame) else pd.DataFrame()
        snap = st.session_state.competitor_menu_snapshots_df if isinstance(st.session_state.competitor_menu_snapshots_df, pd.DataFrame) else pd.DataFrame()
        gap = st.session_state.competitor_assortment_gap_df if isinstance(st.session_state.competitor_assortment_gap_df, pd.DataFrame) else pd.DataFrame()
        price = st.session_state.competitor_price_comparison_df if isinstance(st.session_state.competitor_price_comparison_df, pd.DataFrame) else pd.DataFrame()
        promo = st.session_state.competitor_promo_df if isinstance(st.session_state.competitor_promo_df, pd.DataFrame) else pd.DataFrame()
        cols = st.columns(4)
        cards = [
            ("Competitors Tracked", len(reg)),("Active Snapshots", len(snap)),("Categories Compared", snap["category"].nunique() if "category" in snap.columns else 0),("Average Price Gap", round(_safe_numeric_mean(price, "price_gap_pct"),2)),
            ("Products Above Market", int((price["our_position"] == "Above Market").sum()) if "our_position" in price.columns else 0),("Products Below Market", int((price["our_position"] == "Below Market").sum()) if "our_position" in price.columns else 0),("Assortment Gap Count", len(gap)),("Brand Overlap %", round(100 - min(100, len(gap) * 2), 1)),
            ("Promo Pressure Score", round(_safe_numeric_mean(promo, "competitor_promo_pressure"),1)),("Opportunity Score", max(0, 100 - int(_safe_numeric_mean(price, "price_gap_pct") or 0))), ("Last Snapshot Date", str(snap["snapshot_date"].max()) if "snapshot_date" in snap.columns and not snap.empty else "N/A"),
        ]
        for idx, (label, value) in enumerate(cards):
            cols[idx % 4].metric(label, value)
        status = "Data Incomplete" if snap.empty else ("Overpriced" if _safe_numeric_mean(price, "price_gap_pct") > 10 else "Competitive")
        st.selectbox("Competitive Position", ["Aggressive", "Competitive", "Premium", "Overpriced", "Underpriced", "Data Incomplete"], index=["Aggressive", "Competitive", "Premium", "Overpriced", "Underpriced", "Data Incomplete"].index(status))
        st.info("**Market Read**: Biggest opportunities come from categories with large SKU gaps and where your pricing sits above market while promo pressure is high.")

    with tabs[1]:
        st.subheader("Competitor Registry")
        new = {
            "competitor_name": st.text_input("Competitor Name"), "city": st.text_input("City"), "state": st.text_input("State"),
            "dispensary_type": st.selectbox("Dispensary Type", ["adult-use", "medical", "both", "unknown"]),
            "website_url": st.text_input("Website URL"), "menu_url": st.text_input("Menu URL"), "menu_platform": st.selectbox("Menu Platform", ["Dutchie", "Jane", "Weedmaps", "Leafly", "Native", "Unknown"]),
            "distance_miles": st.number_input("Distance Miles", min_value=0.0, step=0.1), "priority": st.selectbox("Priority", ["high", "medium", "low"]),
            "active_tracking": st.checkbox("Active Tracking", value=True), "last_snapshot_date": st.date_input("Last Snapshot Date", value=date.today()), "snapshot_frequency_days": st.number_input("Snapshot Frequency Days", min_value=1, value=7), "notes": st.text_area("Notes"),
        }
        if st.button("Add Competitor"):
            df = st.session_state.competitor_registry_df
            st.session_state.competitor_registry_df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        st.dataframe(st.session_state.competitor_registry_df, use_container_width=True)

    with tabs[2]:
        st.info("Because most cannabis menus are age-gated and embedded through third-party providers, Buyer Dash will not bypass access controls. Open the menu, complete the age gate manually, then import/capture the visible category data using one of the supported capture methods.")
        st.warning("Some sites block embedded viewing. If the page below is blank or refuses to load, use Open Website in New Tab.")
        mode = st.radio("Capture Mode", ["Embedded Viewer", "Open in New Tab", "Browser Capture File Upload", "Saved HTML/Text Upload", "CSV/XLSX Upload", "PDF/Screenshot Fallback", "Local Playwright Capture"], index=0)
        st.session_state.competitor_capture_mode = mode
        url = st.text_input("Competitor Menu URL", value=st.session_state.competitor_capture_menu_url)
        if st.button("Start Capture Session") and url:
            sess = MenuCaptureSession()
            st.session_state.competitor_capture_session = sess
            st.session_state.competitor_capture_menu_url = url.strip()
            st.success(sess.start(url)["message"])

        active_url = st.session_state.competitor_capture_menu_url or url
        if active_url:
            st.link_button("Open Website in New Tab", active_url)

        if mode in ["Embedded Viewer", "Open in New Tab"] and active_url:
            st.caption("Complete the age gate manually inside the viewer if the site allows embedding. Navigate to the menu category you want to capture, then click Capture Current Category.")
            if mode == "Embedded Viewer":
                components.iframe(active_url, height=800, scrolling=True)
                st.info("If the website does not load below, it may block embedded viewing. Click Open Website in New Tab, complete the age gate there, then use one of the capture fallback methods.")

        if mode == "Local Playwright Capture":
            is_local = os.getenv("RENDER") is None and os.getenv("STREAMLIT_CLOUD") is None
            st.markdown("**Local Browser Capture Only**")
            if not is_local:
                st.warning("Hosted deployments cannot reliably display a Playwright browser window to the user. Use local mode, browser extension capture, or upload/import fallback.")
            else:
                st.info("Local only mode is available. Manually access the site and capture visible menu data without bypassing access controls.")

        cat = st.text_input("Current Category Name")
        if st.button("Capture Current Category") and st.session_state.competitor_capture_session:
            st.info(st.session_state.competitor_capture_session.capture_current_category(cat)["message"])
        st.caption("After opening the menu and selecting a category, use a capture method below to import the visible category data.")

        st.subheader("Browser Capture Assistant")
        st.write("For full one-click category capture, use the future Browser Capture Assistant. It will run in your browser after you manually pass the age gate and will export the visible product cards to Buyer Dash.")
        template = "product_name,brand,category,size,regular_price,sale_price,thc_pct,strain_type,promo_text,availability\n"
        st.download_button("Download Capture Template", data=template, file_name="browser_capture_template.csv", mime="text/csv")
        browser_upload = st.file_uploader("Upload Browser Capture CSV/JSON", type=["csv", "json"], key="browser_capture_upload")
        browser_json = st.text_area("Paste Browser Capture JSON", key="browser_capture_json")

        session = st.session_state.competitor_capture_session or MenuCaptureSession()
        competitor_name = st.text_input("Competitor Name", key="cap_comp")
        category_for_extract = cat or "Unspecified"
        if browser_upload is not None:
            if browser_upload.name.endswith(".csv"):
                rows_df = pd.read_csv(browser_upload)
                rows = rows_df.to_dict(orient="records")
            else:
                rows = session.parse_browser_capture_payload(browser_upload.read().decode("utf-8", errors="ignore"))
            extracted = session.extract_visible_product_cards(rows, competitor_name, str(date.today()), "Unknown", active_url, category_for_extract)
            st.session_state.competitor_capture_rows_pending = pd.concat([st.session_state.competitor_capture_rows_pending, extracted], ignore_index=True)
        if st.button("Import Pasted Browser Capture JSON") and browser_json.strip():
            rows = session.parse_browser_capture_payload(browser_json)
            extracted = session.extract_visible_product_cards(rows, competitor_name, str(date.today()), "Unknown", active_url, category_for_extract)
            st.session_state.competitor_capture_rows_pending = pd.concat([st.session_state.competitor_capture_rows_pending, extracted], ignore_index=True)

        saved_up = st.file_uploader("Upload saved HTML/text file", type=["html", "htm", "txt"], key="saved_html_text_upload")
        pasted_menu_text = st.text_area("Paste visible menu text", key="pasted_menu_text")
        if saved_up is not None:
            content = saved_up.read().decode("utf-8", errors="ignore")
            rows = session.parse_saved_html_or_text(content)
            extracted = session.extract_visible_product_cards(rows, competitor_name, str(date.today()), "Unknown", active_url, category_for_extract)
            st.session_state.competitor_capture_rows_pending = pd.concat([st.session_state.competitor_capture_rows_pending, extracted], ignore_index=True)
        if st.button("Import Pasted Menu Text") and pasted_menu_text.strip():
            rows = session.parse_saved_html_or_text(pasted_menu_text)
            extracted = session.extract_visible_product_cards(rows, competitor_name, str(date.today()), "Unknown", active_url, category_for_extract)
            st.session_state.competitor_capture_rows_pending = pd.concat([st.session_state.competitor_capture_rows_pending, extracted], ignore_index=True)

        up = st.file_uploader("Upload capture file", type=["csv", "json", "xlsx", "xls", "txt", "html", "pdf", "png", "jpg"], key="generic_capture_upload")
        if up is not None and up.name.endswith(".csv"):
            st.session_state.competitor_capture_rows_pending = pd.read_csv(up)
        st.info("Fallback mode loaded. Review extracted rows in Snapshot Review.")

    with tabs[3]:
        df = st.session_state.competitor_capture_rows_pending
        st.subheader("Snapshot Review")
        if isinstance(df, pd.DataFrame) and not df.empty:
            if "capture_confidence" in df.columns:
                st.dataframe(df.style.apply(lambda s: ["background-color: #4a1f1f" if v == "Low" else "" for v in s] if s.name == "capture_confidence" else ["" for _ in s], axis=1), use_container_width=True)
            else:
                st.dataframe(df, use_container_width=True)
            if st.button("Save Snapshot"):
                dedup_cols = ["competitor_name", "snapshot_date", "normalized_product_name", "brand", "package_size_label", "category", "effective_price"]
                merged = df.sort_values(by=[c for c in ["capture_confidence"] if c in df.columns], ascending=False).drop_duplicates(subset=[c for c in dedup_cols if c in df.columns], keep="first")
                st.session_state.competitor_menu_snapshots_df = pd.concat([st.session_state.competitor_menu_snapshots_df, merged], ignore_index=True)
                st.session_state.competitor_saved_snapshot_rows = merged
                st.success("Snapshot saved.")
            st.download_button("Export Cleaned Snapshot", data=df.to_csv(index=False), file_name="competitor_snapshot_cleaned.csv", mime="text/csv")
            if st.button("Discard Snapshot"):
                st.session_state.competitor_capture_rows_pending = pd.DataFrame()

    with tabs[4]:
        st.subheader("Price Intelligence")
        snap = st.session_state.competitor_menu_snapshots_df
        own = st.session_state.get("normalized_inventory_df")
        if not isinstance(own, pd.DataFrame) or own.empty:
            st.info("Upload Buyer Dashboard inventory/sales data to compare your menu against competitors.")
        if isinstance(snap, pd.DataFrame) and not snap.empty and "category" in snap.columns and "effective_price" in snap.columns:
            comp = snap.groupby("category", dropna=False).agg(competitor_avg_price=("effective_price", "mean"), lowest_competitor_price=("effective_price", "min"), highest_competitor_price=("effective_price", "max"), competitor_count=("competitor_name", "nunique")).reset_index()
            comp["our_avg_price"] = comp["competitor_avg_price"]
            comp["market_avg_price"] = comp["competitor_avg_price"]
            comp["price_gap_dollars"] = comp["our_avg_price"] - comp["competitor_avg_price"]
            comp["price_gap_pct"] = (comp["price_gap_dollars"] / comp["competitor_avg_price"].replace(0, pd.NA)) * 100
            comp["our_position"] = comp["price_gap_pct"].apply(lambda v: "Missing Data" if pd.isna(v) else ("Below Market" if v < -3 else "At Market" if abs(v) <= 3 else "Above Market" if v <= 10 else "Premium"))
            st.session_state.competitor_price_comparison_df = comp
            st.dataframe(comp, use_container_width=True)

    with tabs[5]:
        snap = st.session_state.competitor_menu_snapshots_df
        if isinstance(snap, pd.DataFrame) and not snap.empty and "category" in snap.columns:
            gap = snap.groupby("category", dropna=False).agg(competitor_sku_count=("product_name", "nunique"), brand_gap=("brand", "nunique"), package_size_gap=("package_size_label", "nunique")).reset_index()
            gap["our_sku_count"] = 0
            gap["sku_gap"] = gap["competitor_sku_count"] - gap["our_sku_count"]
            gap["category_gap_score"] = gap["sku_gap"] + gap["brand_gap"]
            gap["risk_level"] = gap["category_gap_score"].apply(lambda v: "Critical" if v >= 25 else "High" if v >= 12 else "Medium" if v >= 5 else "Low")
            gap["Recommendation"] = "Increase depth where gap score is highest."
            st.session_state.competitor_assortment_gap_df = gap
            st.dataframe(gap[["category", "our_sku_count", "competitor_sku_count", "sku_gap", "risk_level", "Recommendation"]], use_container_width=True)

    with tabs[6]:
        snap = st.session_state.competitor_menu_snapshots_df
        if isinstance(snap, pd.DataFrame) and not snap.empty:
            promo = snap.copy()
            promo["discount_pct"] = _safe_numeric_series(promo, "discount_pct")
            promo_df = promo[promo["discount_pct"] > 0].copy()
            if not promo_df.empty:
                by_comp = promo_df.groupby("competitor_name", dropna=False).agg(promo_count=("product_name", "count"), average_discount_pct=("discount_pct", "mean"), strongest_discount=("discount_pct", "max"), categories_on_promo=("category", "nunique")).reset_index()
                by_comp["competitor_promo_pressure"] = by_comp["promo_count"] + by_comp["average_discount_pct"] + by_comp["categories_on_promo"]
                st.session_state.competitor_promo_df = by_comp
                st.dataframe(by_comp, use_container_width=True)

    with tabs[7]:
        recs = []
        gap = st.session_state.competitor_assortment_gap_df
        price = st.session_state.competitor_price_comparison_df
        if isinstance(gap, pd.DataFrame) and not gap.empty and (gap["risk_level"] == "Critical").any():
            recs.append("[Assortment] Competitor menus show deeper category depth in critical gaps. Prioritize targeted SKU expansion.")
        if isinstance(price, pd.DataFrame) and not price.empty and (price["our_position"].isin(["Above Market", "Premium"]).any()):
            recs.append("[Pricing] Some categories appear above market; evaluate selective price moves and promo support.")
        recs.append("[Promotions] Avoid racing to the bottom unless margin and sell-through support deeper discounting.")
        st.session_state.competitor_recommendations = recs
        st.write(recs)

    with tabs[8]:
        payload = {
            "executive_summary": "Competitor Intelligence summary based on latest snapshots.",
            "competitors": st.session_state.competitor_registry_df.to_dict(orient="records") if isinstance(st.session_state.competitor_registry_df, pd.DataFrame) else [],
            "pricing": st.session_state.competitor_price_comparison_df.to_dict(orient="records") if isinstance(st.session_state.competitor_price_comparison_df, pd.DataFrame) else [],
            "assortment_gaps": st.session_state.competitor_assortment_gap_df.to_dict(orient="records") if isinstance(st.session_state.competitor_assortment_gap_df, pd.DataFrame) else [],
            "promo_pressure": st.session_state.competitor_promo_df.to_dict(orient="records") if isinstance(st.session_state.competitor_promo_df, pd.DataFrame) else [],
            "recommendations": st.session_state.competitor_recommendations,
            "data_quality": st.session_state.competitor_data_quality,
        }
        st.download_button("Export Competitor Intelligence Report", data=_build_competitor_intelligence_report_pdf(payload), file_name=f"competitor_intelligence_report_{datetime.now().strftime('%Y-%m-%d')}.pdf", mime="application/pdf")
        st.json({"source_type": "manual+uploads", "capture_method": "human_in_the_loop", "rows_extracted": int(len(st.session_state.competitor_capture_rows_pending)) if isinstance(st.session_state.competitor_capture_rows_pending, pd.DataFrame) else 0, "rows_saved": int(len(st.session_state.competitor_menu_snapshots_df)) if isinstance(st.session_state.competitor_menu_snapshots_df, pd.DataFrame) else 0, "last_captured_timestamp": datetime.utcnow().isoformat()})
