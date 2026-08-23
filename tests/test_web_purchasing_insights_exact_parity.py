from io import BytesIO
from pathlib import Path

import pandas as pd

from services.web_buyer_parity import exact_buyer_intelligence, exact_trends
from services.web_slow_movers_parity import build_slow_movers, export_excel, filter_slow_movers, summary, tier_summary


ROOT = Path(__file__).resolve().parents[1]


def _product_rows():
    return pd.DataFrame([
        {"product_name":"Blue Dream 3.5g","subcategory":"flower","strain_type":"sativa","packagesize":"3.5g","unitssold":60,"avgunitsperday":1,"onhandunits":7,"daysonhand":7},
        {"product_name":"Calm Vape 0.5g","subcategory":"vapes","strain_type":"hybrid","packagesize":"0.5g","unitssold":30,"avgunitsperday":.5,"onhandunits":40,"daysonhand":80},
    ])


def _sales_rows():
    return pd.DataFrame([
        {"product_name":"Blue Dream 3.5g","mastercategory":"flower","strain_type":"sativa","packagesize":"3.5g","unitssold":60,"net_sales":1800},
        {"product_name":"Calm Vape 0.5g","mastercategory":"vapes","strain_type":"hybrid","packagesize":"0.5g","unitssold":30,"net_sales":1080},
    ])


def test_buyer_intelligence_matches_streamlit_summary_tables_and_lookback_math():
    result=exact_buyer_intelligence(_product_rows(),_sales_rows(),60)
    assert result["summary"]=={"total_units_sold":90.0,"total_revenue":2880.0,"at_risk_skus":1,"tracked_skus":2}
    assert result["by_category"]["category"].tolist()==["flower","vapes"]
    blue=result["by_product"].iloc[0]
    assert blue["avg_daily_units"]==1 and blue["risk_flag"]=="Reorder Risk" and blue["revenue"]==1800
    assert not result["purchase_priorities"].empty


def test_trends_matches_streamlit_continuous_table_math_and_top_n():
    result=exact_trends(_product_rows(),_sales_rows(),30,30,1.5,1)
    category=result["category_mix"].iloc[0]
    assert category["mastercategory"]=="flower" and category["units_per_day"]==3 and category["unit_share"]==2/3
    assert result["package_size_mix"]["packagesize"].tolist()==["3.5g","0.5g"]
    assert result["best_sellers_by_category"].groupby("mastercategory").size().max()==1
    assert "risk_score" in result["fast_movers_low_stock"].columns


def test_react_buyer_intelligence_and_trends_keep_exact_streamlit_workflow_shape():
    buyer=(ROOT/"frontend/src/pages/BuyingRecommendationsPage.tsx").read_text(encoding="utf-8")
    trends=(ROOT/"frontend/src/pages/BuyerTrendsPage.tsx").read_text(encoding="utf-8")
    buyer_order=["🧠 Buyer Intelligence","🌐 Optional live market references","Buyer intelligence lookback (days)","Tracked SKUs","Top Categories","SKU Risk Table","What to Buy","🤖 Data-Backed Buyer Brief","Generate Buyer Brief"]
    trends_order=["📈 Trends","Trend window (days)","Comparison window (prior days)","Run-rate multiplier","Category Mix (Units)","Package Size Mix (Units)","Top Movers (SKU-level)","Best Sellers by Category","Top N per category","Fast Movers + Low Stock (SKU-level)"]
    assert [buyer.index(value) for value in buyer_order]==sorted(buyer.index(value) for value in buyer_order)
    assert [trends.index(value) for value in trends_order]==sorted(trends.index(value) for value in trends_order)
    assert 'type Tab' not in trends and 'parity-tabs' not in trends


def test_slow_movers_uses_streamlit_velocity_doh_actions_filters_and_summary():
    inventory=pd.DataFrame({"Product Name":["Dead Flower","Moving Vape"],"Available":[20,10],"Category":["Flower","Vapes"],"Vendor":["A","B"],"SKU":["D","M"],"Unit Cost":[5,10]})
    sales=pd.DataFrame({"Product Name":["Moving Vape","Moving Vape"],"Quantity Sold":[14,14],"Date":["2026-07-01","2026-07-28"]})
    frame=build_slow_movers(inventory,sales,56)
    dead=frame.loc[frame.product_name=="Dead Flower"].iloc[0]
    assert dead.days_of_supply==999 and dead.action=="🔴 Investigate" and dead.suggested_discount=="30-50% (Urgent)"
    view=filter_slow_movers(frame,min_doh=60,top_n=0,category="Flower",brand="A",sort_by="$ On-Hand ↓",only_slow=True,exclude_zero=False)
    assert view.product_name.tolist()==["Dead Flower"]
    snapshot=summary(view,60)
    assert snapshot["slow_skus"]==1 and snapshot["units_tied"]==20 and snapshot["dollars_tied"]==100 and snapshot["worst_category"]=="Flower"
    tiers=tier_summary(view)
    assert list(tiers.columns)==["Discount Tier","Product Count","Total Units"]
    workbook=pd.ExcelFile(BytesIO(export_excel(view[["product_name","action"]],tiers,view)))
    assert workbook.sheet_names==["Slow Movers","Summary","Full Detail"]


def test_react_slow_movers_has_exact_controls_defaults_sections_and_no_react_only_facets():
    source=(ROOT/"frontend/src/pages/SlowMoversPage.tsx").read_text(encoding="utf-8")
    ordered=["🐢 Slow Movers &amp; Trends","Search (SKU / Product / Brand)","Velocity window","Slow mover DOH >","Show top N","Category / Subcategory","Vendor / Brand","Sort by","Only slow movers","Exclude on-hand = 0","📌 Snapshot — Filtered Data","🔎 Show full detail / all columns","📉 Discount Tier Summary","📥 Download Slow Movers Report (Excel)"]
    assert [source.index(value) for value in ordered]==sorted(source.index(value) for value in ordered)
    assert "useState(56)" in source and "useState(60)" in source and "useState(0)" in source and "useState(true)" in source
    assert "Decision" not in source and "multiple" not in source
