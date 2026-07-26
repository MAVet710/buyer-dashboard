from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from modules.data_hub import build_data_hub_status, stage_uploaded_dataset


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
    }

    rows = build_data_hub_status(state)
    by_name = {row["Dataset"]: row for row in rows}

    assert by_name["Inventory"]["Status"] == "Ready"
    assert by_name["Product Sales"]["Status"] == "Not loaded"
    assert by_name["Extraction Runs"]["Rows"] == 1
    assert by_name["Co-Man Master Data"]["Status"] == "Ready"

