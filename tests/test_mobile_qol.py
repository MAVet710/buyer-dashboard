from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_polished_theme_includes_phone_breakpoints_and_touch_targets():
    source = (ROOT / "ui_polish.py").read_text(encoding="utf-8")

    assert "@media (max-width: 768px)" in source
    assert "@media (max-width: 430px)" in source
    assert 'data-testid=\"stTabs\"' in source
    assert 'data-testid=\"stDataFrame\"' in source
    assert "min-height: 44px" in source


def test_phone_layout_keeps_sidebar_bounded_and_main_content_full_width():
    source = (ROOT / "ui_polish.py").read_text(encoding="utf-8")

    assert "width: min(88vw, 330px)" in source
    assert "max-width: 100%" in source
    assert "background-attachment: scroll" in source


def test_buyer_navigation_uses_compact_sidebar_selectors():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert 'st.sidebar.selectbox(\n    "Retail Area"' in source
    assert 'st.sidebar.radio(\n    "Tool"' in source
    assert 'key="buyer_section_group"' in source
    assert 'key="buyer_section"' in source
    assert 'data_mode = st.sidebar.selectbox(' in source


def test_theme_has_consistent_focus_and_mobile_safe_areas():
    source = (ROOT / "ui_polish.py").read_text(encoding="utf-8")

    assert "--focus-ring" in source
    assert ':focus-within' in source
    assert 'padding-bottom: 5rem' in source


def test_budget_recognizes_generated_inventory_available_column():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert '"available", "available quantity", "inventory available"' in source


def test_white_label_primary_fields_are_human_readable():
    source = (ROOT / "modules" / "repack" / "ui.py").read_text(encoding="utf-8")

    assert 'st.text_input("Strain Name *"' in source
    assert 'st.number_input("Total Bulk Cost ($) *"' in source
    assert 'st.text_input("strain_name (required)"' not in source


def test_delivery_impact_can_reuse_loaded_sales():
    source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert '"Use sales data already loaded in Buyer Dashboard"' in source
    assert "_normalize_sales_report_dataframe(_cached_sales_raw)" in source


def test_inventory_audits_use_live_scanning_and_item_count_dialog():
    source = (ROOT / "modules" / "inventory_audit" / "ui.py").read_text(encoding="utf-8")

    assert "from streamlit_qrcode_scanner import qrcode_scanner" in source
    assert '@st.dialog("Enter inventory count"' in source
    assert '"Save & scan next"' in source
    assert "preview_scanned_item(" in source
    assert "_live_count_form(" in source
