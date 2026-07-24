"""Tenant-safe Dutchie catalog to METRC item nomenclature matching.

The matching engine is deterministic and free to run. It never invents a
catalog name: every suggested output must be an exact name from the uploaded
Dutchie catalog or a previously confirmed organization mapping.
"""

from __future__ import annotations

import re
import csv
from dataclasses import dataclass
from difflib import SequenceMatcher
from io import BytesIO
from typing import Iterable, Mapping

import pandas as pd


CATALOG_NAME_ALIASES = (
    "product name",
    "item name",
    "product",
    "item",
    "name",
    "online title",
    "menu name",
)
CATALOG_SKU_ALIASES = ("sku", "product sku", "item sku", "external id", "product id")
CATALOG_CATEGORY_ALIASES = (
    "category",
    "product category",
    "master category",
    "subcategory",
)
CATALOG_BRAND_ALIASES = ("brand", "brand name", "vendor", "manufacturer")
MANIFEST_ITEM_ALIASES = ("item", "item name", "product", "product name")

_ITEM_CODE_PREFIX = re.compile(r"^\s*[A-Z]\d{5,}\s*:\s*", re.IGNORECASE)
_SIZE_PATTERN = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)\s*(g|gram|grams|oz|ounce|ounces)\b", re.I)
_PACK_PATTERN = re.compile(r"(?<!\d)(\d+)\s*(?:pk|pack|ct|count)\b|\b(\d+)\s*pack\b", re.I)
_CLASS_PATTERN = re.compile(r"\((?:I|S|H|IH|SH)\)", re.I)
_STOP_TOKENS = {
    "amp", "the", "and", "by", "pre", "roll", "preroll", "flower", "whole",
    "raw", "pack", "pk", "count", "ct", "gram", "grams", "ounce", "ounces",
    "indica", "sativa", "hybrid", "ih", "sh", "h", "i", "s",
}


@dataclass(frozen=True)
class TabularUpload:
    frame: pd.DataFrame
    sheet_name: str
    header_row: int


@dataclass(frozen=True)
class MatchSuggestion:
    source_name: str
    correct_name: str
    confidence: float
    status: str
    match_basis: str
    catalog_item_id: str | None = None


def normalize_column(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().casefold()).strip()


def normalize_item_name(value: object) -> str:
    text = _ITEM_CODE_PREFIX.sub("", str(value or "").strip())
    text = text.casefold().replace("pre-roll", "preroll").replace("pre roll", "preroll")
    text = re.sub(r"\b(\d+)\s*pack\b", r"\1pk", text)
    text = re.sub(r"\b(\d+)\s*(?:count|ct)\b", r"\1pk", text)
    text = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.]+", " ", text)).strip()
    return text


def _column_by_alias(columns: Iterable[object], aliases: Iterable[str]) -> str | None:
    normalized = {normalize_column(column): str(column) for column in columns}
    for alias in aliases:
        if normalize_column(alias) in normalized:
            return normalized[normalize_column(alias)]
    return None


def _candidate_header_score(columns: Iterable[object], aliases: Iterable[str]) -> int:
    normalized = {normalize_column(column) for column in columns}
    return sum(1 for alias in aliases if normalize_column(alias) in normalized)


def read_tabular_upload(
    raw_bytes: bytes,
    filename: str,
    *,
    required_aliases: Iterable[str],
) -> TabularUpload:
    """Read CSV/XLSX with automatic sheet and preamble/header detection."""
    if not raw_bytes:
        raise ValueError("The uploaded file is empty.")
    candidates: list[TabularUpload] = []
    filename_lower = str(filename or "").casefold()
    if filename_lower.endswith((".xlsx", ".xls")):
        book = pd.ExcelFile(BytesIO(raw_bytes))
        for sheet_name in book.sheet_names:
            preview = pd.read_excel(book, sheet_name=sheet_name, header=None, nrows=25)
            for header_row in range(min(20, len(preview))):
                columns = preview.iloc[header_row].fillna("").astype(str).tolist()
                score = _candidate_header_score(columns, required_aliases)
                if score:
                    frame = pd.read_excel(book, sheet_name=sheet_name, header=header_row)
                    candidates.append(TabularUpload(frame=frame, sheet_name=sheet_name, header_row=header_row))
                    break
    else:
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
            preview_rows = list(csv.reader(text.splitlines()[:25]))
            for header_row, columns in enumerate(preview_rows[:20]):
                if _candidate_header_score(columns, required_aliases):
                    frame = pd.read_csv(
                        BytesIO(raw_bytes),
                        header=header_row,
                        encoding=encoding,
                    )
                    candidates.append(TabularUpload(frame=frame, sheet_name="CSV", header_row=header_row))
                    break
            if candidates:
                break
    if not candidates:
        expected = ", ".join(required_aliases)
        raise ValueError(f"No usable table was found. Expected a header such as: {expected}.")
    candidates.sort(key=lambda item: (len(item.frame), len(item.frame.columns)), reverse=True)
    result = candidates[0]
    result.frame.dropna(how="all", inplace=True)
    return result


def prepare_catalog(raw_bytes: bytes, filename: str) -> pd.DataFrame:
    uploaded = read_tabular_upload(raw_bytes, filename, required_aliases=CATALOG_NAME_ALIASES)
    frame = uploaded.frame.copy()
    name_col = _column_by_alias(frame.columns, CATALOG_NAME_ALIASES)
    if not name_col:
        raise ValueError("The Dutchie catalog needs a Product Name or Item Name column.")
    sku_col = _column_by_alias(frame.columns, CATALOG_SKU_ALIASES)
    category_col = _column_by_alias(frame.columns, CATALOG_CATEGORY_ALIASES)
    brand_col = _column_by_alias(frame.columns, CATALOG_BRAND_ALIASES)
    result = pd.DataFrame(
        {
            "canonical_name": frame[name_col].fillna("").astype(str).str.strip(),
            "sku": frame[sku_col].fillna("").astype(str).str.strip() if sku_col else "",
            "category": frame[category_col].fillna("").astype(str).str.strip() if category_col else "",
            "brand": frame[brand_col].fillna("").astype(str).str.strip() if brand_col else "",
        }
    )
    result = result[result["canonical_name"] != ""].copy()
    result["normalized_name"] = result["canonical_name"].map(normalize_item_name)
    result = result[result["normalized_name"] != ""]
    return result.drop_duplicates("normalized_name", keep="first").reset_index(drop=True)


def prepare_manifest(raw_bytes: bytes, filename: str) -> tuple[pd.DataFrame, str]:
    uploaded = read_tabular_upload(raw_bytes, filename, required_aliases=MANIFEST_ITEM_ALIASES)
    frame = uploaded.frame.copy()
    item_col = _column_by_alias(frame.columns, MANIFEST_ITEM_ALIASES)
    if not item_col:
        raise ValueError("The METRC manifest needs an Item column.")
    frame[item_col] = frame[item_col].fillna("").astype(str).str.strip()
    frame = frame[frame[item_col] != ""].copy().reset_index(drop=True)
    if frame.empty:
        raise ValueError("The METRC manifest does not contain any item names.")
    return frame, item_col


def _tokens(name: str) -> set[str]:
    return {
        token
        for token in normalize_item_name(name).split()
        if token not in _STOP_TOKENS and not re.fullmatch(r"\d+(?:\.\d+)?g?", token)
    }


def _size_grams(name: str) -> float | None:
    match = _SIZE_PATTERN.search(str(name or ""))
    if not match:
        return None
    value, unit = float(match.group(1)), match.group(2).casefold()
    return value * 28.349523125 if unit.startswith("oz") or unit.startswith("ounce") else value


def _pack_count(name: str) -> int:
    match = _PACK_PATTERN.search(str(name or ""))
    if match:
        return int(match.group(1) or match.group(2))
    return 1


def _product_family(name: str) -> str:
    normalized = normalize_item_name(name)
    if "preroll" in normalized:
        return "pre-roll"
    if "vape" in normalized or "cartridge" in normalized or "disposable" in normalized:
        return "vape"
    if "edible" in normalized or "gumm" in normalized:
        return "edible"
    if "concentrate" in normalized or "rosin" in normalized or "resin" in normalized:
        return "concentrate"
    if "flower" in normalized:
        return "flower"
    return ""


def _similarity(source: str, candidate: str) -> tuple[float, str]:
    source_norm, candidate_norm = normalize_item_name(source), normalize_item_name(candidate)
    if source_norm == candidate_norm:
        return 1.0, "Exact normalized catalog name"
    seq = SequenceMatcher(None, source_norm, candidate_norm).ratio()
    source_tokens, candidate_tokens = _tokens(source), _tokens(candidate)
    union = source_tokens | candidate_tokens
    token_score = len(source_tokens & candidate_tokens) / len(union) if union else 0.0
    source_size, candidate_size = _size_grams(source), _size_grams(candidate)
    size_score = 1.0 if source_size is None or candidate_size is None else float(abs(source_size - candidate_size) < 0.01)
    pack_score = float(_pack_count(source) == _pack_count(candidate))
    source_family, candidate_family = _product_family(source), _product_family(candidate)
    family_score = 1.0 if not source_family or not candidate_family else float(source_family == candidate_family)
    score = (0.35 * seq) + (0.35 * token_score) + (0.12 * size_score) + (0.10 * pack_score) + (0.08 * family_score)
    return score, "Catalog structure: name, strain tokens, size, pack count, and product family"


def suggest_matches(
    source_names: Iterable[object],
    catalog: pd.DataFrame,
    *,
    learned_mappings: Mapping[str, tuple[str, str | None]] | None = None,
) -> list[MatchSuggestion]:
    if catalog is None or catalog.empty:
        raise ValueError("Upload or load a Dutchie catalog before matching a manifest.")
    learned = learned_mappings or {}
    catalog_rows = catalog.to_dict("records")
    unique_sources = list(dict.fromkeys(str(value or "").strip() for value in source_names if str(value or "").strip()))
    results: list[MatchSuggestion] = []
    for source in unique_sources:
        normalized_source = normalize_item_name(source)
        if normalized_source in learned:
            correct_name, catalog_item_id = learned[normalized_source]
            results.append(MatchSuggestion(source, correct_name, 1.0, "Confirmed", "Previously confirmed for this organization", catalog_item_id))
            continue
        scored: list[tuple[float, dict, str]] = []
        for row in catalog_rows:
            score, basis = _similarity(source, str(row["canonical_name"]))
            scored.append((score, row, basis))
        scored.sort(key=lambda item: (item[0], str(item[1]["canonical_name"])), reverse=True)
        top_score, top_row, basis = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        margin = top_score - runner_up
        if top_score >= 0.90 and margin >= 0.04:
            status = "Ready"
        elif top_score >= 0.68:
            status = "Review"
        else:
            status = "Unmatched"
        correct_name = str(top_row["canonical_name"]) if status != "Unmatched" else ""
        results.append(
            MatchSuggestion(
                source_name=source,
                correct_name=correct_name,
                confidence=round(top_score, 4),
                status=status,
                match_basis=basis,
                catalog_item_id=str(top_row.get("id") or "") or None,
            )
        )
    return results


def suggestions_frame(suggestions: Iterable[MatchSuggestion]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Original METRC Item": item.source_name,
                "Correct Item Name": item.correct_name,
                "Confidence": round(item.confidence * 100.0, 1),
                "Status": item.status,
                "Match Basis": item.match_basis,
                "Catalog Item ID": item.catalog_item_id or "",
            }
            for item in suggestions
        ]
    )


def corrected_name_export(
    manifest: pd.DataFrame,
    item_column: str,
    review: pd.DataFrame,
) -> pd.DataFrame:
    """Return the intentionally minimal, row-aligned one-column deliverable."""
    approved = {
        str(row["Original METRC Item"]).strip(): str(row["Correct Item Name"]).strip()
        for _, row in review.iterrows()
        if str(row.get("Correct Item Name") or "").strip()
    }
    values = [approved.get(str(value or "").strip(), "") for value in manifest[item_column]]
    return pd.DataFrame({"Correct Item Name": values})
