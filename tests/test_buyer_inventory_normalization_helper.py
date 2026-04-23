import pandas as pd

from buyer_inventory_normalization import ensure_inventory_derived_fields
from views.buyer_perfect_view import (
    VALID_STRAIN_TYPES,
    detect_column,
    extract_size,
    extract_strain_type,
    normalize_col,
    normalize_rebelle_category,
)


def test_helper_derives_subcategory_without_raw_category_column():
    inv_df = pd.DataFrame(
        [
            {"itemname": "Blue Dream Pre-Roll 1g", "onhandunits": 4},
            {"itemname": "Northern Lights Vape 0.5g", "onhandunits": 2},
        ]
    )

    out = ensure_inventory_derived_fields(
        inv_df,
        normalize_category=normalize_rebelle_category,
        extract_strain_type=extract_strain_type,
        extract_size=extract_size,
        valid_strain_types=VALID_STRAIN_TYPES,
        detect_column=detect_column,
        normalize_col=normalize_col,
    )

    assert set(out["subcategory"].tolist()) == {"pre rolls", "vapes"}
    assert "packagesize" in out.columns
    assert "strain_type" in out.columns


def test_helper_uses_safe_fallbacks_when_parsing_is_empty():
    inv_df = pd.DataFrame([{"itemname": "", "onhandunits": 1}])

    out = ensure_inventory_derived_fields(
        inv_df,
        normalize_category=normalize_rebelle_category,
        extract_strain_type=extract_strain_type,
        extract_size=extract_size,
        valid_strain_types=VALID_STRAIN_TYPES,
        detect_column=detect_column,
        normalize_col=normalize_col,
    )

    assert out.loc[0, "subcategory"] == "unspecified"
    assert out.loc[0, "packagesize"] == "unknown"
    assert out.loc[0, "strain_type"] == "unspecified"
