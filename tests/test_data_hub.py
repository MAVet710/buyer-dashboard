from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from modules.data_hub import (
    build_data_hub_status,
    inspect_uploaded_dataset,
    stage_uploaded_dataset,
)


@dataclass
class Upload:
    name: str
    payload: bytes

    def getvalue(self) -> bytes:
        return self.payload


def test_stage_uploaded_dataset_caches_bytes_and_history_once():
    state = {}
    upload = Upload("inventory.xlsx", b"inventory rows")

    first = stage_uploaded_dataset(
        state,
        upload,
        cache_key="_cache_inv",
        dataset_label="Inventory",
    )
    second = stage_uploaded_dataset(
        state,
        upload,
        cache_key="_cache_inv",
        dataset_label="Inventory",
    )

    assert first["bytes"] == b"inventory rows"
    assert second["fingerprint"] == first["fingerprint"]
    assert len(state["data_hub_import_history"]) == 1


def test_stage_uploaded_dataset_enforces_size_limit():
    with pytest.raises(ValueError, match="upload limit"):
        stage_uploaded_dataset(
            {},
            Upload("too-large.csv", b"12345"),
            cache_key="_cache_inv",
            dataset_label="Inventory",
            max_upload_bytes=4,
        )


def test_data_hub_status_reflects_retail_extraction_and_facility_state():
    state = {
        "_cache_inv": {
            "name": "inventory.csv",
            "bytes": b"ready",
            "staged_at": "2026-07-25T12:00:00+00:00",
        },
        "ecc_run_log": pd.DataFrame([{"batch_id_internal": "RUN-1"}]),
        "active_organization_id": "org-1",
        "active_facility_id": "facility-1",
        "active_facility_name": "Main Production",
        "demo_commercial_orders_df": pd.DataFrame([{"order": "SO-1"}]),
        "demo_nomenclature_catalog_df": pd.DataFrame([{"sku": "SKU-1"}]),
        "demo_production_machines_df": pd.DataFrame([{"asset": "IMA-1"}]),
        "compliance_sources_df": pd.DataFrame([{"topic": "packaging"}]),
    }

    rows = build_data_hub_status(state)
    by_name = {row["Dataset"]: row for row in rows}

    assert by_name["Inventory"]["Status"] == "Ready"
    assert by_name["Product Sales"]["Status"] == "Not loaded"
    assert by_name["Extraction Runs"]["Rows"] == 1
    assert by_name["Co-Man Master Data"]["Status"] == "Ready"
    assert by_name["Orders & Fulfillment"]["Status"] == "Ready"
    assert by_name["Nomenclature Catalog"]["Rows"] == 1
    assert by_name["Production Capacity"]["Rows"] == 1
    assert by_name["Compliance Sources"]["Status"] == "Ready"


def test_guided_import_inspects_required_inventory_fields():
    inspection = inspect_uploaded_dataset(
        Upload(
            "inventory.csv",
            b"Product Name,Category,On Hand,Brand\nBlue Dream,Flower,12,Doobie\n",
        ),
        "Inventory",
    )

    assert inspection["rows"] == 1
    assert inspection["columns"] == 4
    assert inspection["quality"] == "Ready"
    assert inspection["matches"] == {
        "Product": "Product Name",
        "Category": "Category",
        "On hand": "On Hand",
    }


def test_guided_import_surfaces_mapping_review_without_silent_correction():
    inspection = inspect_uploaded_dataset(
        Upload("sales.csv", b"Product Name,Unknown Metric\nBlue Dream,10\n"),
        "Product Sales",
    )

    assert inspection["quality"] == "Review mapping"
    assert inspection["missing"] == ["Units sold"]
