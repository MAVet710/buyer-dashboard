from __future__ import annotations

from io import BytesIO

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from modules.coman.models import Base, Organization
from services.nomenclature_mapper import (
    corrected_name_export,
    normalize_item_name,
    prepare_catalog,
    prepare_manifest,
    suggest_matches,
    suggestions_frame,
)
from services.nomenclature_store import NomenclatureStore


def _catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "canonical_name": "AMP Pre-Roll 1g (H) Fire Dawg",
                "normalized_name": normalize_item_name("AMP Pre-Roll 1g (H) Fire Dawg"),
                "sku": "FD-1",
                "category": "Pre-Rolls",
                "brand": "AMP",
            },
            {
                "canonical_name": "AMP Pre-Roll 0.5g 5pk (IH) Chem",
                "normalized_name": normalize_item_name("AMP Pre-Roll 0.5g 5pk (IH) Chem"),
                "sku": "CH-5",
                "category": "Pre-Rolls",
                "brand": "AMP",
            },
        ]
    )


def test_normalize_item_name_removes_metrc_code_and_standardizes_pack_terms():
    assert normalize_item_name("M00002017802: Pre-Roll 5 Pack 0.5g - Fire Dawg") == (
        "preroll 5pk 0.5g fire dawg"
    )


def test_matcher_returns_only_names_from_the_uploaded_catalog():
    suggestions = suggest_matches(
        [
            "M00001105432: Pre-Roll 1g - Fire Dawg",
            "M00002560816: Pre-Roll 5 Pack 0.5g - Chem",
        ],
        _catalog(),
    )

    assert [row.correct_name for row in suggestions] == [
        "AMP Pre-Roll 1g (H) Fire Dawg",
        "AMP Pre-Roll 0.5g 5pk (IH) Chem",
    ]
    assert all(row.correct_name in set(_catalog()["canonical_name"]) for row in suggestions)


def test_confirmed_organization_mapping_wins_over_fuzzy_matching():
    learned = {
        normalize_item_name("Legacy Fire Dawg"): (
            "AMP Pre-Roll 1g (H) Fire Dawg",
            "catalog-1",
        )
    }
    result = suggest_matches(["Legacy Fire Dawg"], _catalog(), learned_mappings=learned)[0]

    assert result.correct_name == "AMP Pre-Roll 1g (H) Fire Dawg"
    assert result.status == "Confirmed"
    assert result.confidence == 1.0


def test_final_export_has_one_column_and_preserves_manifest_row_order():
    manifest = pd.DataFrame(
        {
            "Package": ["PKG-1", "PKG-2", "PKG-3"],
            "Item": ["Source A", "Source B", "Source A"],
        }
    )
    review = pd.DataFrame(
        {
            "Original METRC Item": ["Source A", "Source B"],
            "Correct Item Name": ["Correct A", "Correct B"],
        }
    )

    result = corrected_name_export(manifest, "Item", review)

    assert list(result.columns) == ["Correct Item Name"]
    assert result["Correct Item Name"].tolist() == ["Correct A", "Correct B", "Correct A"]


def test_upload_parsers_detect_dutchie_and_metrc_columns():
    catalog_bytes = BytesIO()
    manifest_bytes = BytesIO()
    with pd.ExcelWriter(catalog_bytes, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "Product Name": ["AMP Pre-Roll 1g (H) Fire Dawg"],
                "SKU": ["FD-1"],
            }
        ).to_excel(writer, index=False, sheet_name="Catalog")
    with pd.ExcelWriter(manifest_bytes, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "Package": ["PKG-1"],
                "Item": ["M00001105432: Pre-Roll 1g - Fire Dawg"],
            }
        ).to_excel(writer, index=False, sheet_name="Sheet1")

    catalog = prepare_catalog(catalog_bytes.getvalue(), "catalog.xlsx")
    manifest, item_column = prepare_manifest(manifest_bytes.getvalue(), "manifest.xlsx")

    assert catalog.loc[0, "canonical_name"] == "AMP Pre-Roll 1g (H) Fire Dawg"
    assert item_column == "Item"
    assert len(manifest) == 1


def test_csv_parser_skips_dutchie_metadata_preamble():
    raw = (
        "Export Date:,2026-07-24\n"
        "Location:,Store A\n"
        "Product Name,SKU,Category\n"
        "AMP Pre-Roll 1g (H) Fire Dawg,FD-1,Pre-Rolls\n"
    ).encode("utf-8")

    catalog = prepare_catalog(raw, "dutchie_catalog.csv")

    assert len(catalog) == 1
    assert catalog.loc[0, "canonical_name"] == "AMP Pre-Roll 1g (H) Fire Dawg"


def test_store_keeps_catalogs_and_learned_mappings_tenant_scoped():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Organization(id="org-a", name="Store A", slug="store-a"),
                Organization(id="org-b", name="Store B", slug="store-b"),
            ]
        )
        session.commit()
    store = NomenclatureStore(engine=engine)
    store.replace_catalog("org-a", _catalog().to_dict("records"), "tester")
    catalog_a = store.list_catalog("org-a")
    assert len(catalog_a) == 2
    assert store.list_catalog("org-b") == []

    review = suggestions_frame(
        suggest_matches(["Pre-Roll 1g - Fire Dawg"], _catalog())
    )
    store.confirm_mappings("org-a", review.to_dict("records"), "tester")

    assert normalize_item_name("Pre-Roll 1g - Fire Dawg") in store.learned_mappings("org-a")
    assert store.learned_mappings("org-b") == {}


def test_sql_migration_enables_rls_for_both_tenant_tables():
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "0010_catalog_nomenclature_mapper.sql"
    ).read_text(encoding="utf-8")

    assert "catalog_nomenclature_items enable row level security" in sql
    assert "catalog_nomenclature_mappings enable row level security" in sql
