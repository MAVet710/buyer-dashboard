"""Streamlit workflow for organization-specific catalog nomenclature mapping."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from modules.coman.db import ComanDatabaseConfigurationError
from services.nomenclature_mapper import (
    corrected_name_export,
    prepare_catalog,
    prepare_manifest,
    suggest_matches,
    suggestions_frame,
)
from services.nomenclature_store import NomenclatureStore
from ui_polish import render_metric_tiles, render_section_header


_STORE_CACHE_VERSION = "catalog-nomenclature-v1"


@st.cache_resource
def _store(cache_version: str) -> NomenclatureStore:
    del cache_version
    return NomenclatureStore()


def _actor() -> str:
    return str(
        st.session_state.get("admin_user")
        or st.session_state.get("user_user")
        or st.session_state.get("auth_user_id")
        or "system"
    )


def _catalog_frame(records) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": row.id,
                "canonical_name": row.canonical_name,
                "normalized_name": row.normalized_name,
                "sku": row.sku,
                "category": row.category,
                "brand": row.brand,
            }
            for row in records
        ]
    )


def _xlsx_with_names_only(frame: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame[["Correct Item Name"]].to_excel(
            writer,
            index=False,
            sheet_name="Correct Item Names",
        )
    return output.getvalue()


def render_nomenclature_mapper() -> None:
    organization_id = st.session_state.get("active_organization_id")
    if not organization_id:
        st.warning("Select an organization in the sidebar before mapping nomenclature.")
        return

    render_section_header(
        "Catalog Nomenclature Mapper",
        "Use each dispensary's Dutchie catalog as the source of truth for correcting METRC item names.",
        "BUYER OPERATIONS",
    )
    st.caption(
        "Catalogs and confirmed mappings are isolated by organization. "
        "No other company's nomenclature is used in this workspace."
    )

    try:
        store = _store(_STORE_CACHE_VERSION)
        if not store.configured:
            raise ComanDatabaseConfigurationError("Database unavailable")
        persisted_catalog = _catalog_frame(store.list_catalog(organization_id))
        learned_mappings = store.learned_mappings(organization_id)
    except Exception:
        st.error(
            "Nomenclature storage could not connect to Supabase. "
            "Verify COMAN_DATABASE_URL before importing a catalog."
        )
        return

    catalog_count = len(persisted_catalog)
    mapping_count = len(learned_mappings)
    render_metric_tiles(
        [
            {
                "label": "Catalog Items",
                "value": f"{catalog_count:,}",
                "help": "Active Dutchie source-of-truth names",
                "color": "orange",
            },
            {
                "label": "Learned Mappings",
                "value": f"{mapping_count:,}",
                "help": "Confirmed METRC names for this organization",
                "color": "green",
            },
            {
                "label": "Export Shape",
                "value": "1 column",
                "help": "Correct Item Name only",
                "color": "blue",
            },
        ]
    )

    catalog_tab, map_tab, library_tab = st.tabs(
        ["1 · Dutchie Catalog", "2 · Correct METRC Manifest", "Mapping Library"]
    )

    with catalog_tab:
        st.markdown("#### Upload the store's approved catalog")
        st.write(
            "Upload a Dutchie CSV or Excel catalog containing a Product Name or Item Name column. "
            "Saving it replaces the organization's active catalog while preserving confirmed METRC mappings."
        )
        catalog_file = st.file_uploader(
            "Dutchie catalog",
            type=["csv", "xlsx"],
            key=f"nomenclature_catalog_{organization_id}",
        )
        if catalog_file is not None:
            try:
                catalog = prepare_catalog(catalog_file.getvalue(), catalog_file.name)
                st.success(f"Detected {len(catalog):,} unique approved item names.")
                preview_columns = [
                    column
                    for column in ["canonical_name", "sku", "category", "brand"]
                    if column in catalog.columns
                ]
                st.dataframe(
                    catalog[preview_columns].head(100).rename(
                        columns={
                            "canonical_name": "Correct Item Name",
                            "sku": "SKU",
                            "category": "Category",
                            "brand": "Brand",
                        }
                    ),
                    width="stretch",
                    hide_index=True,
                )
                if st.button(
                    "Save as this organization's Dutchie catalog",
                    type="primary",
                    key=f"save_nomenclature_catalog_{organization_id}",
                ):
                    saved = store.replace_catalog(
                        organization_id,
                        catalog.to_dict("records"),
                        _actor(),
                    )
                    st.success(f"Saved {saved:,} catalog names for this organization.")
                    st.session_state.pop(f"nomenclature_review_{organization_id}", None)
                    st.rerun()
            except Exception as exc:
                st.error(f"The Dutchie catalog could not be read: {exc}")
        elif persisted_catalog.empty:
            st.info("Upload the first Dutchie catalog to begin.")
        else:
            st.success(f"An active catalog with {len(persisted_catalog):,} names is ready.")

    with map_tab:
        if persisted_catalog.empty:
            st.info("Save a Dutchie catalog in Step 1 before uploading a METRC manifest.")
        else:
            st.markdown("#### Upload the METRC manifest")
            manifest_file = st.file_uploader(
                "METRC manifest",
                type=["csv", "xlsx"],
                key=f"nomenclature_manifest_{organization_id}",
            )
            if manifest_file is not None:
                try:
                    manifest, item_column = prepare_manifest(
                        manifest_file.getvalue(),
                        manifest_file.name,
                    )
                    source_names = manifest[item_column].fillna("").astype(str)
                    suggestions = suggest_matches(
                        source_names,
                        persisted_catalog,
                        learned_mappings=learned_mappings,
                    )
                    initial_review = suggestions_frame(suggestions)
                    review_key = f"nomenclature_review_{organization_id}"
                    fingerprint = (
                        manifest_file.name,
                        len(manifest),
                        tuple(initial_review["Original METRC Item"].tolist()),
                    )
                    if st.session_state.get(f"{review_key}_fingerprint") != fingerprint:
                        st.session_state[review_key] = initial_review
                        st.session_state[f"{review_key}_fingerprint"] = fingerprint

                    review = st.session_state[review_key]
                    ready_count = int((review["Status"].isin(["Ready", "Confirmed"])).sum())
                    review_count = int((review["Status"] == "Review").sum())
                    unmatched_count = int((review["Status"] == "Unmatched").sum())
                    render_metric_tiles(
                        [
                            {"label": "Unique METRC Names", "value": f"{len(review):,}", "help": "Detected in this manifest", "color": "blue"},
                            {"label": "Ready", "value": f"{ready_count:,}", "help": "High-confidence or learned", "color": "green"},
                            {"label": "Needs Review", "value": f"{review_count:,}", "help": "Select the correct catalog name", "color": "yellow"},
                            {"label": "Unmatched", "value": f"{unmatched_count:,}", "help": "No safe automatic match", "color": "red"},
                        ]
                    )
                    st.markdown("#### Review suggested names")
                    st.caption(
                        "Every Correct Item Name must come from the current Dutchie catalog. "
                        "Review yellow and red rows before confirming."
                    )
                    catalog_names = persisted_catalog["canonical_name"].dropna().astype(str).tolist()
                    edited = st.data_editor(
                        review,
                        width="stretch",
                        hide_index=True,
                        disabled=[
                            "Original METRC Item",
                            "Confidence",
                            "Status",
                            "Match Basis",
                            "Catalog Item ID",
                        ],
                        column_config={
                            "Correct Item Name": st.column_config.SelectboxColumn(
                                "Correct Item Name",
                                options=catalog_names,
                                required=True,
                                help="Only names from this organization's Dutchie catalog are allowed.",
                            ),
                            "Confidence": st.column_config.ProgressColumn(
                                "Confidence",
                                min_value=0.0,
                                max_value=100.0,
                                format="%.0f%%",
                            ),
                            "Match Basis": None,
                            "Catalog Item ID": None,
                        },
                        key=f"nomenclature_editor_{organization_id}",
                    )
                    st.session_state[review_key] = edited

                    selected_names = edited["Correct Item Name"].fillna("").astype(str).str.strip()
                    invalid_names = sorted(set(selected_names[selected_names != ""]) - set(catalog_names))
                    missing_count = int((selected_names == "").sum())
                    if invalid_names:
                        st.error("One or more selected names are not in the active Dutchie catalog.")
                    elif missing_count:
                        st.warning(f"Choose a correct catalog name for {missing_count} item(s) before exporting.")
                    else:
                        review_signature = tuple(
                            zip(
                                edited["Original METRC Item"].fillna("").astype(str),
                                selected_names,
                            )
                        )
                        reviewed = st.checkbox(
                            "I reviewed the suggested names and confirmed they match this store's Dutchie catalog.",
                            key=f"nomenclature_review_ack_{organization_id}",
                        )
                        if reviewed and st.button(
                            "Confirm names and remember mappings",
                            type="primary",
                            width="stretch",
                            key=f"confirm_nomenclature_{organization_id}",
                        ):
                            saved = store.confirm_mappings(
                                organization_id,
                                edited.to_dict("records"),
                                _actor(),
                            )
                            st.session_state[f"{review_key}_confirmed_signature"] = review_signature
                            st.success(f"Confirmed {saved:,} mappings for this organization.")

                        if st.session_state.get(f"{review_key}_confirmed_signature") == review_signature:
                            output_frame = corrected_name_export(manifest, item_column, edited)
                            st.download_button(
                                "Download correct item names",
                                data=_xlsx_with_names_only(output_frame),
                                file_name="Correct_METRC_Item_Names.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                width="stretch",
                                key=f"download_nomenclature_{organization_id}",
                            )
                            st.caption(
                                f"The download contains {len(output_frame):,} rows in manifest order "
                                "and exactly one column: Correct Item Name."
                            )
                        else:
                            st.info("Confirm the reviewed names to unlock the one-column export.")
                except Exception as exc:
                    st.error(f"The METRC manifest could not be processed: {exc}")

    with library_tab:
        st.markdown("#### Organization naming source")
        if persisted_catalog.empty:
            st.info("No active Dutchie catalog has been saved.")
        else:
            st.dataframe(
                persisted_catalog[
                    ["canonical_name", "sku", "category", "brand"]
                ].rename(
                    columns={
                        "canonical_name": "Correct Item Name",
                        "sku": "SKU",
                        "category": "Category",
                        "brand": "Brand",
                    }
                ),
                width="stretch",
                hide_index=True,
            )
        st.caption(
            f"{mapping_count:,} confirmed METRC-to-Dutchie mappings are currently remembered "
            "for this organization."
        )
