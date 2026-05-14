from pathlib import Path

from services.competitor_html_parser import parse_competitor_file, process_competitor_files_batch

FIX = Path("tests/fixtures/competitor_html")


def _b(name: str) -> bytes:
    return (FIX / name).read_text().encode()


def test_sunnyside_names_are_not_price_fragments():
    cleaned, _, _, file_result, _ = parse_competitor_file(_b("sunnyside_vapes.html"), "Sunnyside Vapes.html", snapshot_date="2026-05-14")
    assert file_result["rows_saved"] > 0
    assert cleaned["product_name"].str.contains(r"\$").sum() == 0


def test_kush_no_add_to_cart_in_cleaned():
    cleaned, _, _, _, _ = parse_competitor_file(_b("kush_flower.html"), "Kush Groove Flower.html")
    assert not cleaned["product_name"].str.lower().str.contains("add to cart").any()


def test_new_leaf_shell_requires_companion_iframe():
    cleaned, _, _, file_result, _ = parse_competitor_file(_b("new_leaf_flower_parent.html"), "New Leaf Flower parent.html")
    assert cleaned.empty
    assert file_result["status"] == "needs_companion_iframe_file"


def test_batch_lifecycle_and_multi_competitor_survive():
    files = [
        {"file_name": "Kush Groove Flower.html", "file_bytes": _b("kush_flower.html")},
        {"file_name": "Kush Groove Pre-Rolls.html", "file_bytes": _b("kush_prerolls.html")},
        {"file_name": "Sunnyside Edibles.html", "file_bytes": _b("sunnyside_edibles.html")},
        {"file_name": "New Leaf Pre-Rolls parent.html", "file_bytes": _b("new_leaf_prerolls_parent.html")},
    ]
    out = process_competitor_files_batch(files, snapshot_date="2026-05-14")
    assert len(out["file_df"]) == len(files)
    assert out["cleaned_df"]["competitor_name"].nunique() >= 2
    assert out["cleaned_df"]["category"].nunique() >= 2
