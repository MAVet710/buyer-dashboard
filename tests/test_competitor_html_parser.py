import pandas as pd

from services.competitor_html_parser import NORMALIZED_SCHEMA, detect_menu_platform, parse_competitor_snapshot


def _parse(html: str, file_name: str):
    return parse_competitor_snapshot(html.encode(), file_name, "", "2026-05-14", "")


def test_platform_detection_joint_sunnyside_dutchie():
    assert detect_menu_platform("window.jointEcommerce /categories/flower/", "Kush Groove Flower.html") == "joint_ecommerce"
    assert detect_menu_platform("sunnyside.shop ProductListItem brand-name product-name", "Sunnyside Edibles.html") == "sunnyside_react"
    assert detect_menu_platform("dutchie--embed__container dtche%5Bcategory%5D=flower", "New Leaf Flower.html") == "dutchie_embedded"


def test_normalized_schema_consistent_for_all():
    cases = [
        ("window.jointEcommerce $20 Add to cart", "Kush Groove Flower.html"),
        ("sunnyside.shop product-name THC: 100mg $18", "Sunnyside Vapes.html"),
        ("dutchie--embed__container <iframe src='7997.html'></iframe>", "New Leaf Flower parent.html"),
    ]
    for html, name in cases:
        df, _ = _parse(html, name)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == NORMALIZED_SCHEMA


def test_dutchie_shell_returns_companion_status():
    html = "<div class='dutchie--embed__container'><iframe src='7997.html'></iframe></div>"
    df, meta = _parse(html, "New Leaf Pre-Rolls parent.html")
    assert meta.get("status") == "needs_companion_iframe_file"
    assert meta.get("embedded_iframe_detected") is True
    assert meta.get("detected_platform") == "Dutchie Embedded"
    assert df.empty


def test_sunnyside_mg_potency_to_mg_fields_not_pct():
    html = "sunnyside.shop product-name THC: 100mg CBD: 99.4mg TAC: 286.7mg $25 Add to cart"
    df, _ = _parse(html, "Sunnyside Edibles.html")
    if not df.empty:
        row = df.iloc[0]
        assert row["thc_mg"] == 100.0
        assert row["cbd_mg"] == 99.4
        assert row["tac_mg"] == 286.7
        assert pd.isna(row["thc_pct"]) or row["thc_pct"] is None
