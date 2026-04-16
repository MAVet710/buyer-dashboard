from io import BytesIO

import pandas as pd

from extraction_partner_upload_upgrade import (
    ECC_REQUIRED_COLUMNS,
    apply_mapping_to_dataframe,
    compute_mapping_confidence,
    detect_header_row,
    load_partner_file_multisheet,
    suggest_column_mapping,
)


class _UploadedFile:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


def test_detect_header_row_prefers_keyword_header():
    sheet = pd.DataFrame(
        [
            [2026, 1, 2, 3],
            ["Run Date", "Batch ID", "Input Weight", "Method"],
            ["2026-04-15", "A1", 1000, "BHO"],
        ]
    )
    assert detect_header_row(sheet) == 1


def test_load_partner_file_multisheet_detects_all_sheets():
    bytes_io = BytesIO()
    with pd.ExcelWriter(bytes_io, engine="openpyxl") as writer:
        pd.DataFrame(
            [
                ["metadata", "ignore"],
                ["Run Date", "Batch ID", "Method"],
                ["2026-04-15", "B1", "BHO"],
            ]
        ).to_excel(writer, sheet_name="RunsA", header=False, index=False)
        pd.DataFrame(
            [
                ["header note", "x"],
                ["Run Date", "Batch ID", "Method"],
                ["2026-04-16", "B2", "CO2"],
            ]
        ).to_excel(writer, sheet_name="RunsB", header=False, index=False)

    uploaded = _UploadedFile("partner.xlsx", bytes_io.getvalue())
    sheets, diagnostics = load_partner_file_multisheet(uploaded)

    assert set(sheets.keys()) == {"RunsA", "RunsB"}
    assert diagnostics["sheets"]["RunsA"]["detected_header_row"] == 1
    assert diagnostics["sheets"]["RunsB"]["detected_header_row"] == 1


def test_mapping_confidence_and_apply_mapping_output_shape():
    source = pd.DataFrame(
        {
            "run date": ["2026-04-15"],
            "batch id": ["X-1"],
            "input weight": [1000],
            "finished output": [180],
            "method": ["BHO"],
        }
    )
    suggestions = suggest_column_mapping(list(source.columns), ["run_date", "batch_id_internal", "method"])
    confidence = compute_mapping_confidence(suggestions)

    assert 0 <= confidence <= 1

    mapped = apply_mapping_to_dataframe(
        source_df=source,
        mapping={
            "run_date": "run date",
            "batch_id_internal": "batch id",
            "method": "method",
            "input_weight_g": "input weight",
            "finished_output_g": "finished output",
        },
        defaults={"method": "BHO", "state": "MA", "client_name": "In House", "status": "Processing", "coa_status": "Pending"},
    )
    assert list(mapped.columns) == ECC_REQUIRED_COLUMNS
    assert mapped.loc[0, "yield_pct"] == 18
