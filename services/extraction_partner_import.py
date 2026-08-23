"""UI-independent partner extraction workbook inspection and mapping parity."""

from __future__ import annotations

import difflib
import re
from io import BytesIO
from typing import Any, Mapping

import pandas as pd


TARGET_FIELDS = [
    "run_date", "batch_id_internal", "method", "state", "license_name", "client_name",
    "input_weight_g", "intermediate_output_g", "finished_output_g", "residual_loss_g",
    "yield_pct", "post_process_efficiency_pct", "operator", "machine_line", "status",
    "coa_status", "qa_hold", "notes",
]
DEFAULTS = {"method": "BHO", "state": "MA", "client_name": "In House", "status": "Processing", "coa_status": "Pending"}
FIELD_ALIASES = {
    "run_date": {"date", "run date", "extraction date", "production date"},
    "batch_id_internal": {"batch", "batch id", "batch number", "internal batch", "internal batch id", "run id", "run number"},
    "method": {"method", "extraction method", "process", "process type"},
    "state": {"state", "jurisdiction"},
    "license_name": {"license", "license name", "facility", "facility license", "facility license name"},
    "client_name": {"client", "client name", "customer", "customer name"},
    "input_weight_g": {"input", "input weight", "input weight g", "input grams", "starting weight"},
    "intermediate_output_g": {"intermediate", "intermediate output", "intermediate output g", "intermediate grams"},
    "finished_output_g": {"output", "finished output", "finished output g", "finished grams", "output weight"},
    "residual_loss_g": {"loss", "residual loss", "residual loss g", "loss weight", "waste"},
    "yield_pct": {"yield", "yield pct", "yield percent", "yield percentage"},
    "post_process_efficiency_pct": {"post process efficiency", "post process efficiency pct", "efficiency", "efficiency pct"},
    "operator": {"operator", "technician", "employee"},
    "machine_line": {"machine", "machine line", "equipment", "line"},
    "status": {"status", "run status"},
    "coa_status": {"coa", "coa status", "test status", "testing status"},
    "qa_hold": {"qa hold", "quality hold", "hold"},
    "notes": {"notes", "run notes", "comments"},
}


def normalize_column_name(column: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(column).strip().lower())).strip()


def detect_header_row(sheet: pd.DataFrame) -> int:
    keywords = {"date", "run", "input", "output", "weight", "yield", "operator", "method", "batch", "product", "metrc", "package", "coa", "status", "client", "state"}
    best_row, best_score = 0, float("-inf")
    for index in range(min(20, len(sheet))):
        values = [str(value).strip() for value in sheet.iloc[index].tolist() if str(value).strip() and str(value).strip().lower() != "nan"]
        if not values:
            continue
        score = sum(2.0 for value in values if any(word in normalize_column_name(value) for word in keywords))
        score += sum(0.3 for value in values if len(normalize_column_name(value)) >= 3 and not normalize_column_name(value).isdigit())
        score -= sum(1.2 for value in values if normalize_column_name(value).isdigit() or re.fullmatch(r"[\d\.\-\/]+", normalize_column_name(value)))
        if values and all(re.fullmatch(r"[\d\.\-\/]+", value) for value in values):
            score -= 4.0
        if score > best_score:
            best_row, best_score = index, score
    return best_row


def normalize_workbook(payload: bytes, filename: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    diagnostics: dict[str, Any] = {"sheets": {}, "warnings": []}
    sheets: dict[str, pd.DataFrame] = {}
    if filename.casefold().endswith(".csv"):
        frame = pd.read_csv(BytesIO(payload))
        sheets["CSV"] = frame
        diagnostics["sheets"]["CSV"] = {"detected_header_row": 0, "rows": len(frame), "columns": [str(column) for column in frame.columns]}
    elif filename.casefold().endswith((".xlsx", ".xls")):
        for sheet_name, raw in pd.read_excel(BytesIO(payload), sheet_name=None, header=None).items():
            header = detect_header_row(raw)
            frame = pd.read_excel(BytesIO(payload), sheet_name=sheet_name, header=header).dropna(axis=1, how="all").dropna(axis=0, how="all")
            if frame.empty:
                diagnostics["warnings"].append(f"{sheet_name}: no data after header normalization")
                continue
            sheets[sheet_name] = frame
            diagnostics["sheets"][sheet_name] = {"detected_header_row": header, "rows": len(frame), "columns": [str(column) for column in frame.columns]}
    else:
        raise ValueError("Use a CSV, XLSX, or XLS extraction run file.")
    normalized = []
    for sheet_name, frame in sheets.items():
        row = frame.copy()
        row.columns = [normalize_column_name(column) for column in row.columns]
        row["__source_sheet"] = sheet_name
        normalized.append(row)
    if not normalized:
        return pd.DataFrame(), diagnostics
    combined = pd.concat(normalized, ignore_index=True, sort=False).dropna(axis=0, how="all")
    diagnostics["rows_extracted"] = len(combined)
    diagnostics["normalized_columns"] = [str(column) for column in combined.columns]
    return combined, diagnostics


def suggestions(columns: list[str]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for target in TARGET_FIELDS:
        aliases = {normalize_column_name(value) for value in FIELD_ALIASES.get(target, set())} | {normalize_column_name(target)}
        scored = []
        for column in columns:
            normalized = normalize_column_name(column)
            score = 1.0 if normalized in aliases else max(
                difflib.SequenceMatcher(None, alias, normalized).ratio() for alias in aliases
            )
            scored.append((column, score))
        source, score = max(scored, key=lambda value: value[1]) if scored else ("IGNORE", 0.0)
        output[target] = {"source": source if score >= 0.72 else "IGNORE", "score": float(score)}
    return output


def confidence(proposals: Mapping[str, Mapping[str, Any]]) -> float:
    scores = [float(value.get("score", 0)) for value in proposals.values()]
    return sum(scores) / len(scores) if scores else 0.0


def apply_mapping(frame: pd.DataFrame, mapping: Mapping[str, str], defaults: Mapping[str, Any]) -> pd.DataFrame:
    effective = {**DEFAULTS, **dict(defaults)}
    output = pd.DataFrame(index=frame.index)
    for target in TARGET_FIELDS:
        source = str(mapping.get(target) or "IGNORE")
        output[target] = frame[source] if source != "IGNORE" and source in frame.columns else effective.get(target, None)
    output["run_date"] = pd.to_datetime(output["run_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    for column in ("input_weight_g", "intermediate_output_g", "finished_output_g", "residual_loss_g", "yield_pct", "post_process_efficiency_pct"):
        output[column] = pd.to_numeric(output[column], errors="coerce").fillna(0.0)
    output["yield_pct"] = output.apply(lambda row: row["yield_pct"] if row["yield_pct"] > 0 else (row["finished_output_g"] / row["input_weight_g"] * 100 if row["input_weight_g"] > 0 else 0.0), axis=1)
    output["post_process_efficiency_pct"] = output.apply(lambda row: row["post_process_efficiency_pct"] if row["post_process_efficiency_pct"] > 0 else (row["finished_output_g"] / row["intermediate_output_g"] * 100 if row["intermediate_output_g"] > 0 else 0.0), axis=1)
    for column in ("batch_id_internal", "license_name", "operator", "machine_line", "notes"):
        output[column] = output[column].fillna("").astype(str)
    for column in ("method", "state", "client_name", "status", "coa_status"):
        output[column] = output[column].fillna(effective[column]).replace("", effective[column]).astype(str)
    output["qa_hold"] = output["qa_hold"].map(
        lambda value: value
        if isinstance(value, bool)
        else str(value).strip().casefold() in {"true", "1", "yes", "y", "hold"}
        if pd.notna(value)
        else False
    )
    return output[TARGET_FIELDS]
