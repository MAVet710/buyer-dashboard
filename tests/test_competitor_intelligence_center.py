from io import BytesIO
import zipfile

import pandas as pd
import streamlit as st

from modules.competitor_intelligence_center import (
    _ensure_competitor_snapshot_schema,
    _merge_into_competitor_snapshot,
    build_dutchie_capture_bundle,
)
from services.competitor_html_parser import detect_category, detect_competitor, process_competitor_files_batch


def _dutchie_parent_html(category: str) -> bytes:
    return (
        f"<html><body><div>dutchie iframe</div><div class='dutchie--embed__container'><iframe src='https://goodnaturema.com/menu?dtche%5Bcategory%5D={category}'></iframe></div></body></html>"
    ).encode()


def _product_html(rows: int, category_label: str) -> bytes:
    cards = []
    for i in range(rows):
        cards.append(
            f"""
            <div data-testid=\"product-list-item\" class=\"product-card\">
              <h3>Good Nature {category_label} Product {i}</h3>
              <div class=\"brand\">Good Brand</div>
              <div>$25.00</div>
              <div>THC 24%</div>
              <div>1g</div>
              <button>Add to cart</button>
            </div>
            """
        )
    return ("<html><body><div>dutchie iframe</div>" + "\n".join(cards) + "</body></html>").encode()


def _zip_with_saved_resource(rows: int, category: str) -> bytes:
    bio = BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"Menu - Good Nature Cannabis_{category}_files/8120.html", _product_html(rows, category).decode())
    return bio.getvalue()


def test_merge_handles_missing_competitor_name_column_without_crash():
    st.session_state.clear()
    st.session_state["competitor_menu_snapshots_df"] = pd.DataFrame()
    incoming = pd.DataFrame([
        {"product_name": "A", "category": "Flower", "effective_price": 20.0}
    ])
    out = _merge_into_competitor_snapshot(incoming, source_label="unit_test")
    assert not out.empty
    assert "competitor_name" in out.columns
    assert out.iloc[0]["competitor_name"] == "Unknown"


def test_merge_empty_incoming_preserves_existing_snapshot():
    st.session_state.clear()
    st.session_state["competitor_menu_snapshots_df"] = _ensure_competitor_snapshot_schema(
        pd.DataFrame([{"competitor_name": "Existing", "product_name": "Prod", "category": "Flower"}])
    )
    before_len = len(st.session_state["competitor_menu_snapshots_df"])
    out = _merge_into_competitor_snapshot(pd.DataFrame(), source_label="unit_test")
    assert len(out) == before_len


def test_merge_good_nature_rows_dedupes_safely_and_keeps_numeric_price():
    st.session_state.clear()
    st.session_state["competitor_menu_snapshots_df"] = pd.DataFrame()
    incoming = pd.DataFrame([
        {
            "competitor_name": "Good Nature Cannabis",
            "snapshot_date": "2026-05-14",
            "category": "Flower",
            "subcategory": "Whole Flower",
            "product_name": "Blue Dream",
            "normalized_product_name": "blue dream",
            "brand": "Brand A",
            "package_size_label": "1g",
            "effective_price": 25.0,
            "source_file_name": "flower_8120.html",
        },
        {
            "competitor_name": "Good Nature Cannabis",
            "snapshot_date": "2026-05-14",
            "category": "Flower",
            "subcategory": "Whole Flower",
            "product_name": "Blue Dream",
            "normalized_product_name": "blue dream",
            "brand": "Brand A",
            "package_size_label": "1g",
            "effective_price": 25.0,
            "source_file_name": "flower_saved_resource_dup.html",
        },
    ])
    out = _merge_into_competitor_snapshot(incoming, source_label="dutchie_zip")
    assert len(out) == 1
    assert int(out.iloc[0]["duplicate_count"]) >= 1
    assert pd.api.types.is_numeric_dtype(out["effective_price"])


def test_good_nature_dutchie_zip_parsing_returns_153_rows():
    files = [
        {"file_name": "Menu - Good Nature Cannabis_concentrates.html", "file_bytes": _dutchie_parent_html("concentrates")},
        {"file_name": "Menu - Good Nature Cannabis_flower.html", "file_bytes": _dutchie_parent_html("flower")},
        {"file_name": "Menu - Good Nature Cannabis_prerolls.html", "file_bytes": _dutchie_parent_html("pre-rolls")},
    ]
    bundle = build_dutchie_capture_bundle([], [
        type("Upload", (), {"name": "Menu - Good Nature Cannabis_concentrates_files.zip", "getvalue": lambda self: _zip_with_saved_resource(13, "concentrates")})(),
        type("Upload", (), {"name": "Menu - Good Nature Cannabis_flower_files.zip", "getvalue": lambda self: _zip_with_saved_resource(75, "flower")})(),
        type("Upload", (), {"name": "Menu - Good Nature Cannabis_prerolls_files.zip", "getvalue": lambda self: _zip_with_saved_resource(65, "prerolls")})(),
    ])
    for c in bundle["companions"]:
        files.append({"file_name": c["inside_zip_name"], "file_bytes": c["file_bytes"]})
    out = process_competitor_files_batch(files, snapshot_date="2026-05-14")
    assert len(out["cleaned_df"]) == 153
    assert out["cleaned_df"]["category"].notna().all()
    assert set(out["cleaned_df"]["competitor_name"].unique()) == {"Good Nature Cannabis"}


def test_inventory_like_rows_do_not_merge_into_snapshot():
    st.session_state.clear()
    st.session_state["competitor_menu_snapshots_df"] = pd.DataFrame()
    incoming = pd.DataFrame([
        {"our_product_name": "Widget", "our_category": "Flower", "our_brand": "B", "quantity_on_hand": 10, "cost": 4.0}
    ])
    out = _merge_into_competitor_snapshot(incoming, source_label="inventory_upload")
    assert out.empty
    assert st.session_state.get("competitor_last_merge_skipped") is True


def test_detect_good_nature_and_dtche_categories():
    text = "https://goodnaturema.com/menu?dtche%5Bcategory%5D=concentrates"
    assert detect_competitor(text, "Menu - Good Nature Cannabis_concentrates.html") == "Good Nature Cannabis"
    assert detect_category(text, "x.html") == "Concentrates"
    assert detect_category("dtche[category]=pre-rolls", "x.html") == "Pre-Rolls"
