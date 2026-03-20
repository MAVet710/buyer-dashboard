"""
Delivery Impact – core analytics module.

Provides pure-Python helpers for:
  • Parsing order-level sales reports (CSV / XLSX) with preamble skipping
  • Parsing delivery manifest PDFs (pdfplumber → PyPDF2 fallback)
  • Normalising and matching product names
  • Computing 14-day before/after KPIs
  • Building daily / hourly time-series DataFrames for charting

All functions are side-effect-free and importable in tests without Streamlit.
"""

from __future__ import annotations

import re
import difflib
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Size tokens that are stripped during normalisation so that
# "Blue Dream 3.5g" and "Blue Dream" match the same product.
_SIZE_TOKENS: re.Pattern = re.compile(
    r"\b(\d+(\.\d+)?\s*(g|oz|mg|ml|lb|pack|pk|ct|count|piece|pc))\b",
    re.IGNORECASE,
)

# Header columns we look for when scanning sales CSV/XLSX preamble rows.
_SALES_HEADER_REQUIRED = {"orderid", "ordertime"}
_SALES_HEADER_ANY = {"orderid", "ordertime", "productname", "netsales", "netrevenue"}

# ---------------------------------------------------------------------------
# Constants for manifest PDF table column detection
# ---------------------------------------------------------------------------

# Normalised header cell values that indicate a column holds the product/item name.
_NAME_COL_KEYWORDS: frozenset = frozenset({
    "item", "itemname", "product", "productname", "description",
    "name", "productdescription", "itemdescription",
})

# Normalised header cell values that strongly indicate a *received* quantity column.
# These are checked first so "Received Qty" wins over a plain "Qty" column.
_QTY_COL_KEYWORDS_PREFERRED: frozenset = frozenset({
    "receivedqty", "qtyreceived", "receivedquantity", "quantityreceived",
    "received", "recqty", "recvqty",
})

# Fallback qty keywords used when no preferred column is found.
_QTY_COL_KEYWORDS_FALLBACK: frozenset = frozenset({
    "qty", "quantity", "units", "count", "unitcount", "totalreceived",
})

# Complete set of normalised strings recognised as header cell values.
# Used to detect which rows are header rows (rather than data rows).
_HEADER_CELL_NORMS: frozenset = frozenset(
    _NAME_COL_KEYWORDS
    | _QTY_COL_KEYWORDS_PREFERRED
    | _QTY_COL_KEYWORDS_FALLBACK
    | {
        "orderedqty", "ordered", "unitprice", "price", "sku", "id", "line",
        "no", "number", "uom", "unit", "packageid", "package", "type",
        "category", "brand", "licensenumber", "total", "linenumber", "ln",
        "strain", "vendor", "manifest", "transfer", "weight",
    }
)


# ---------------------------------------------------------------------------
# Product-name normalisation and matching
# ---------------------------------------------------------------------------

def normalize_product_name(name: str) -> str:
    """
    Return a normalised, lower-case product name suitable for fuzzy matching.

    Steps:
      1. Lower-case.
      2. Strip size tokens (e.g. ``3.5g``, ``500mg``, ``1oz``).
      3. Remove punctuation (keep alphanumeric and spaces).
      4. Collapse repeated whitespace.
    """
    s = str(name).lower().strip()
    s = _SIZE_TOKENS.sub(" ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def match_manifest_to_sales(
    manifest_items: List[str],
    sales_names: List[str],
    fuzzy_threshold: float = 0.82,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Match each manifest item name to a sales product name.

    Strategy (priority order):
      1. Exact match (case-insensitive).
      2. Normalised match (sizes / punctuation stripped).
      3. Fuzzy match via ``difflib.SequenceMatcher`` with *fuzzy_threshold*.

    Parameters
    ----------
    manifest_items:
        Product names extracted from delivery manifests.
    sales_names:
        Unique ``Product Name`` values from the sales report.
    fuzzy_threshold:
        Minimum similarity ratio (0–1) to accept a fuzzy match.
        Default ``0.82`` is conservative.

    Returns
    -------
    matched : dict
        Mapping of ``manifest_name → sales_name`` for each successful match.
    unmatched : list
        Manifest items that could not be matched.
    """
    # Pre-compute normalised lookup for sales names
    norm_to_sales: Dict[str, str] = {}
    for sn in sales_names:
        norm_to_sales[normalize_product_name(sn)] = sn

    # Exact (lower) lookup
    lower_to_sales: Dict[str, str] = {sn.lower(): sn for sn in sales_names}

    matched: Dict[str, str] = {}
    unmatched: List[str] = []

    for item in manifest_items:
        item_lower = item.lower().strip()
        item_norm = normalize_product_name(item)

        # 1) Exact match
        if item_lower in lower_to_sales:
            matched[item] = lower_to_sales[item_lower]
            continue

        # 2) Normalised match
        if item_norm in norm_to_sales:
            matched[item] = norm_to_sales[item_norm]
            continue

        # 3) Fuzzy match
        best_ratio = 0.0
        best_sales = None
        for norm_sn, sn in norm_to_sales.items():
            ratio = difflib.SequenceMatcher(None, item_norm, norm_sn).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_sales = sn
        if best_ratio >= fuzzy_threshold and best_sales is not None:
            matched[item] = best_sales
            continue

        unmatched.append(item)

    return matched, unmatched


# ---------------------------------------------------------------------------
# Sales report parsing
# ---------------------------------------------------------------------------

def find_sales_header_row(raw_bytes: bytes, is_xlsx: bool = False) -> int:
    """
    Scan lines of a CSV (or first sheet text of XLSX) for the true header row.

    The header row is the first row that contains **both** ``Order ID`` and
    ``Order Time`` columns (case-insensitive, punctuation-stripped).

    Returns the 0-based row index of the header, or ``0`` if not found.
    """
    if is_xlsx:
        # For XLSX we read without header and scan cell values
        try:
            import openpyxl  # type: ignore
            wb = openpyxl.load_workbook(BytesIO(raw_bytes), read_only=True, data_only=True)
            ws = wb.active
            for i, row in enumerate(ws.iter_rows(max_row=40, values_only=True)):
                norm_cells = {
                    re.sub(r"[^a-z0-9]", "", str(v).lower())
                    for v in row
                    if v is not None
                }
                if norm_cells & _SALES_HEADER_REQUIRED == _SALES_HEADER_REQUIRED:
                    wb.close()
                    return i
                if len(norm_cells & _SALES_HEADER_ANY) >= 2:
                    wb.close()
                    return i
            wb.close()
        except Exception:
            pass
        return 0

    # CSV path: decode and scan lines
    try:
        text = raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        return 0

    for i, line in enumerate(text.splitlines()):
        # Normalise each comma-separated cell
        norm_cells = {
            re.sub(r"[^a-z0-9]", "", cell.lower())
            for cell in line.split(",")
        }
        if norm_cells & _SALES_HEADER_REQUIRED == _SALES_HEADER_REQUIRED:
            return i
        if len(norm_cells & _SALES_HEADER_ANY) >= 2:
            return i
        # Stop scanning if we've gone past 40 lines – probably no header
        if i > 40:
            break
    return 0


def parse_sales_report_bytes(
    raw_bytes: bytes,
    filename: str = "",
) -> pd.DataFrame:
    """
    Parse an order-level sales report (CSV or XLSX) into a clean DataFrame.

    Expected columns (auto-detected):
      - ``Order ID``
      - ``Order Time``      → parsed as datetime (timezone-naive)
      - ``Product Name``
      - ``Category``        (optional)
      - ``Total Inventory Sold`` / ``Units Sold``
      - ``Net Sales``       (or ``Gross Sales`` as fallback)

    Preamble metadata rows (e.g. ``Export Date:,03/20/2026``) are skipped
    automatically.

    Returns a DataFrame with canonical column names::

        order_id, order_time, product_name, category, units_sold, net_sales
    """
    is_xlsx = filename.lower().endswith((".xlsx", ".xls"))

    header_row = find_sales_header_row(raw_bytes, is_xlsx=is_xlsx)

    if is_xlsx:
        df = pd.read_excel(BytesIO(raw_bytes), header=header_row)
    else:
        df = pd.read_csv(BytesIO(raw_bytes), skiprows=header_row)

    # Normalise column names: lower, strip, remove spaces/underscores
    df.columns = (
        df.columns.astype(str)
        .str.lower()
        .str.strip()
        .str.replace(r"[\s_]+", "", regex=True)
    )

    # Canonical column resolution helper
    def _find_col(candidates: List[str]) -> Optional[str]:
        for c in candidates:
            if c in df.columns:
                return c
        return None

    order_id_col = _find_col(["orderid", "ordernumber", "order"])
    time_col = _find_col(["ordertime", "orderdate", "datetime", "date"])
    name_col = _find_col(["productname", "product", "name", "item", "itemname"])
    cat_col = _find_col(["category", "mastercategory", "productcategory", "department"])
    units_col = _find_col([
        "totalinventorysold", "unitssold", "quantitysold", "qtysold",
        "units", "quantity", "qty",
    ])
    net_sales_col = _find_col(["netsales", "netsale", "netsalesamount"])
    gross_sales_col = _find_col(["grosssales", "gross", "totalsales"])
    revenue_col = net_sales_col or gross_sales_col

    # Build output DataFrame
    out: Dict[str, pd.Series] = {}

    if order_id_col:
        out["order_id"] = df[order_id_col].astype(str)
    else:
        out["order_id"] = pd.Series(range(len(df)), dtype=str)

    if time_col:
        out["order_time"] = pd.to_datetime(df[time_col], errors="coerce")
        # Drop timezone info to keep everything timezone-naive
        if hasattr(out["order_time"].dt, "tz_localize"):
            try:
                out["order_time"] = out["order_time"].dt.tz_localize(None)
            except TypeError:
                out["order_time"] = out["order_time"].dt.tz_convert(None)
    else:
        out["order_time"] = pd.NaT

    if name_col:
        out["product_name"] = df[name_col].astype(str)
    else:
        out["product_name"] = pd.Series([""] * len(df))

    if cat_col:
        out["category"] = df[cat_col].astype(str)
    else:
        out["category"] = pd.Series([""] * len(df))

    if units_col:
        out["units_sold"] = pd.to_numeric(df[units_col], errors="coerce").fillna(0.0)
    else:
        out["units_sold"] = 0.0

    if revenue_col:
        raw_rev = df[revenue_col].astype(str).str.replace(r"[\$,]", "", regex=True)
        out["net_sales"] = pd.to_numeric(raw_rev, errors="coerce").fillna(0.0)
    else:
        out["net_sales"] = 0.0

    result = pd.DataFrame(out)

    # Drop rows where order_time is NaT (un-parseable) and rows that look
    # like subtotal / total rows (product name == "total")
    result = result[result["order_time"].notna()].copy()
    result = result[
        result["product_name"].str.strip().str.lower() != "total"
    ].copy()

    return result.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Manifest PDF parsing
# ---------------------------------------------------------------------------

def parse_manifest_pdf_bytes(
    pdf_bytes: bytes,
    filename: str = "",
) -> Tuple[Optional[pd.Timestamp], pd.DataFrame, str]:
    """
    Extract received datetime and item table from a delivery manifest PDF.

    Returns
    -------
    received_dt : pd.Timestamp or None
        The first datetime found in the PDF text.
    items_df : DataFrame
        Columns: ``item_name`` (str), ``qty`` (float).
    raw_text : str
        Full extracted text (for debug downloads).
    """
    raw_text = ""

    # ── Strategy 1: pdfplumber ───────────────────────────────────────────────
    try:
        import pdfplumber  # type: ignore

        rows: List[List[str]] = []
        page_texts: List[str] = []

        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                page_texts.append(page_text)
                tables = page.extract_tables() or []
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    for row in table:  # include header so _rows_to_items_df can detect columns
                        rows.append(
                            [str(c).strip() if c is not None else "" for c in row]
                        )

        raw_text = "\n".join(page_texts)

        received_dt = _extract_datetime_from_text(raw_text)
        items_df = _rows_to_items_df(rows, raw_text)

        if not items_df.empty or received_dt is not None:
            return received_dt, items_df, raw_text

    except Exception:
        pass

    # ── Strategy 2: PyPDF2 text extraction ──────────────────────────────────
    try:
        from PyPDF2 import PdfReader  # type: ignore

        reader = PdfReader(BytesIO(pdf_bytes))
        text_parts: List[str] = []
        for page in reader.pages:
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:
                continue
        raw_text = "\n".join(text_parts)

        received_dt = _extract_datetime_from_text(raw_text)
        items_df = _parse_items_from_text(raw_text)
        return received_dt, items_df, raw_text

    except Exception:
        pass

    return None, pd.DataFrame(columns=["item_name", "qty"]), raw_text


# ── Internal helpers for PDF parsing ─────────────────────────────────────────

# Datetime patterns commonly found on manifests
_DT_PATTERNS: List[re.Pattern] = [
    # "Received: 03/15/2025 14:32"  or  "Date Received: 3/15/25 2:32 PM"
    re.compile(
        r"(?:received|date)[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+"
        r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)",
        re.IGNORECASE,
    ),
    # Generic "03/15/2025 14:32" anywhere
    re.compile(
        r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+"
        r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)",
        re.IGNORECASE,
    ),
    # ISO: "2025-03-15T14:32:00"
    re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?)"),
    # Date only: "03/15/2025" or "03/15/25"
    re.compile(r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})"),
    # ISO date only: "2025-03-15"
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
]

# Explicit datetime formats tried in priority order.
# ``infer_datetime_format`` was removed in pandas 2.2, so we list formats
# explicitly to stay compatible across pandas versions.
_DT_FORMATS: List[str] = [
    "%m/%d/%Y %I:%M %p",   # 03/19/2026 10:58 AM
    "%m/%d/%Y %I:%M%p",    # 03/19/2026 10:58AM
    "%m/%d/%Y %H:%M:%S",   # 03/19/2026 10:30:00
    "%m/%d/%Y %H:%M",      # 03/19/2026 10:30
    "%m/%d/%y %I:%M %p",   # 03/19/26 10:58 AM
    "%m/%d/%y %I:%M%p",    # 03/19/26 10:58AM
    "%m/%d/%y %H:%M:%S",   # 03/19/26 10:30:00
    "%m/%d/%y %H:%M",      # 03/19/26 10:30
    "%Y-%m-%dT%H:%M:%S",   # 2026-03-19T10:30:00
    "%Y-%m-%d %H:%M:%S",   # 2026-03-19 10:30:00
    "%Y-%m-%d %H:%M",      # 2026-03-19 10:30
    "%m/%d/%Y",            # 03/19/2026
    "%m/%d/%y",            # 03/19/26
    "%Y-%m-%d",            # 2026-03-19
]


def _parse_datetime_string(s: str) -> Optional[pd.Timestamp]:
    """
    Try to parse *s* as a timezone-naive ``pd.Timestamp``.

    Tries each format in :data:`_DT_FORMATS` before falling back to
    ``pd.to_datetime`` without the deprecated *infer_datetime_format* flag.
    Returns ``None`` when no format succeeds.
    """
    s = s.strip()
    if not s:
        return None
    for fmt in _DT_FORMATS:
        try:
            ts = pd.Timestamp(datetime.strptime(s, fmt))
            if pd.notna(ts):
                return ts
        except (ValueError, OverflowError):
            continue
    # Last-resort: let pandas infer (works on older pandas; may be slow).
    try:
        ts = pd.to_datetime(s)
        if pd.notna(ts):
            if ts.tzinfo is not None:
                ts = ts.tz_convert(None)
            return ts
    except Exception:
        pass
    return None


def _extract_datetime_from_text(text: str) -> Optional[pd.Timestamp]:
    """Return the first parseable datetime found in *text*, or ``None``."""
    for pat in _DT_PATTERNS:
        for m in pat.finditer(text):
            raw = " ".join(g for g in m.groups() if g)
            ts = _parse_datetime_string(raw)
            if ts is not None:
                return ts
    return None


# Normalised label strings (lower, alnum-only) that indicate a row's first
# cell is a "Date Received" type label.  Used by the priority-ranked extractor.
_RECEIVED_DATE_LABEL_NORMS: frozenset = frozenset({
    "datereceived",
    "receiveddate",
    "received",
    "receiveddatetime",
    "datereceivedtime",
    "deliverydate",
    "receivedon",
    "datedelivered",
    "receivedtime",
})


def _extract_received_dt_from_rows(
    preamble_rows: List[List[str]],
    raw_text: str,
) -> Optional[pd.Timestamp]:
    """
    Extract the received date/time from manifest preamble rows using a
    priority-ranked search:

    1. Rows whose first cell matches a "Date Received" label (e.g.
       ``Received Date``, ``Date Received:``, ``Received``).
    2. Any datetime-like value found anywhere in the preamble rows.
    3. Any datetime-like value found in *raw_text* (full file text).

    Returns a timezone-naive ``pd.Timestamp``, or ``None``.
    """
    # Priority 1: labeled rows
    for row in preamble_rows:
        if len(row) < 2:
            continue
        label_norm = _norm_cell(row[0])
        if label_norm in _RECEIVED_DATE_LABEL_NORMS:
            for cell in row[1:]:
                dt = _parse_datetime_string(cell)
                if dt is not None:
                    return dt

    # Priority 2: general scan of preamble text
    preamble_text = "\n".join(" ".join(r) for r in preamble_rows)
    dt = _extract_datetime_from_text(preamble_text)
    if dt is not None:
        return dt

    # Priority 3: full raw-text fallback
    return _extract_datetime_from_text(raw_text)


def _try_parse_float(s: str) -> Optional[float]:
    """
    Parse *s* as a float, stripping currency symbols and commas.

    Returns ``None`` when the string cannot be interpreted as a plain number
    (e.g. a product name, or a percentage string ending in ``%``).
    Percentage strings are intentionally rejected so that "100%" is not
    mistaken for a received quantity of 100.
    """
    stripped = s.strip()
    # Explicitly reject percentage values.
    if stripped.endswith("%"):
        return None
    cleaned = re.sub(r"[\$,\s]", "", stripped)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalize_row(row: List[str]) -> List[str]:
    """
    Normalise a table row returned by pdfplumber.

    Multi-line cell values (containing ``\\n``) are collapsed to a single space
    so that each cell represents one logical value.  Leading / trailing
    whitespace is stripped from every cell.
    """
    return [re.sub(r"\s+", " ", str(c).replace("\n", " ")).strip() for c in row]


def _rows_to_items_df(rows: List[List[str]], raw_text: str) -> pd.DataFrame:
    """
    Convert table rows (including the optional header row) extracted by
    pdfplumber into an items DataFrame.

    Improvements over the previous implementation:

    * Detects the header row to identify which column is the **item name** and
      which is the **received quantity** (preferred) or a generic qty column.
      This prevents line-number columns (1, 2, 3 …) from being mistaken for
      the received quantity.
    * Normalises cells that contain embedded newlines so they are treated as a
      single value rather than split into multiple rows.
    * Handles *continuation rows* where a product name wraps onto a second
      table row with an empty qty cell.  Continuation text is appended to the
      most recently committed item when all non-name columns are empty,
      otherwise it starts a new pending name.
    * Filters currency / price cells so they are not appended to product names.
    * Falls back to :func:`_parse_items_from_text` when no items can be parsed
      from the table structure.
    """
    if not rows:
        return _parse_items_from_text(raw_text)

    n_cols = max(len(r) for r in rows) if rows else 0
    if n_cols < 2:
        return _parse_items_from_text(raw_text)

    # ── Step 1: detect header row, find name & qty column indices ─────────────
    name_col_idx: Optional[int] = None
    qty_col_idx: Optional[int] = None
    data_start = 0

    for row_i, row in enumerate(rows[:5]):
        norm_cells = [re.sub(r"[^a-z0-9]", "", str(c).lower()) for c in row]
        # Treat the row as a header when at least 2 cells match known keywords.
        if sum(1 for nc in norm_cells if nc in _HEADER_CELL_NORMS) < 2:
            continue

        # Locate the item-name column.
        for col_i, nc in enumerate(norm_cells):
            if nc in _NAME_COL_KEYWORDS and name_col_idx is None:
                name_col_idx = col_i

        # Locate the qty column – prefer explicit "received" variants.
        for col_i, nc in enumerate(norm_cells):
            if nc in _QTY_COL_KEYWORDS_PREFERRED and qty_col_idx is None:
                qty_col_idx = col_i
                break
        if qty_col_idx is None:
            for col_i, nc in enumerate(norm_cells):
                if nc in _QTY_COL_KEYWORDS_FALLBACK and qty_col_idx is None:
                    qty_col_idx = col_i

        data_start = row_i + 1
        break

    # ── Step 2: process data rows ─────────────────────────────────────────────
    items: List[Dict] = []
    pending_name: str = ""  # carries partial name from a continuation row

    for raw_row in rows[data_start:]:
        row = _normalize_row(raw_row)
        if len(row) < 2:
            continue

        if name_col_idx is not None and qty_col_idx is not None:
            # ── Column-aware path ────────────────────────────────────────────
            name = row[name_col_idx] if name_col_idx < len(row) else ""
            qty_str = row[qty_col_idx] if qty_col_idx < len(row) else ""

            # Skip rows that are themselves header repetitions.
            name_norm = re.sub(r"[^a-z0-9]", "", name.lower())
            if name_norm in _HEADER_CELL_NORMS:
                pending_name = ""
                continue

            qty = _try_parse_float(qty_str)

            if qty is None and name:
                # Continuation row: name text but qty column is empty.
                # If all non-name columns are also empty this row is a
                # continuation of the *previous* item; otherwise it is the
                # start of the next item whose qty will arrive in a later row.
                non_name_empty = all(
                    not row[i]
                    for i in range(len(row))
                    if i != name_col_idx
                )
                if non_name_empty and items:
                    # Append continuation text to the last committed item.
                    items[-1]["item_name"] = re.sub(
                        r"\s+", " ",
                        items[-1]["item_name"] + " " + name,
                    ).strip()
                else:
                    pending_name = " ".join(filter(None, [pending_name, name]))
            elif qty is not None:
                full_name = " ".join(filter(None, [pending_name, name]))
                full_name = re.sub(r"\s+", " ", full_name).strip()
                if full_name:
                    items.append({"item_name": full_name, "qty": qty})
                pending_name = ""
            else:
                # Empty row – reset accumulator.
                pending_name = ""
        else:
            # ── Heuristic path (no header detected) ──────────────────────────
            # Filter currency cells; take the *last* numeric in the row as qty
            # so that leading line-number columns are skipped naturally.
            name_candidates: List[str] = []
            numeric_vals: List[float] = []
            for cell in row:
                if not cell:
                    continue
                # Skip cells that look like currency (leading $).
                if re.match(r"^\$", cell):
                    continue
                val = _try_parse_float(cell)
                if val is not None:
                    numeric_vals.append(val)
                else:
                    norm = re.sub(r"[^a-z0-9]", "", cell.lower())
                    if norm in _HEADER_CELL_NORMS:
                        continue
                    name_candidates.append(cell)

            if name_candidates:
                full_name = " ".join(
                    filter(None, [pending_name] + name_candidates)
                )
                full_name = re.sub(r"\s+", " ", full_name).strip()
                # Use the last numeric value (skip leading line numbers).
                qty_val: Optional[float] = numeric_vals[-1] if numeric_vals else None
                if qty_val is not None:
                    items.append({"item_name": full_name, "qty": qty_val})
                    pending_name = ""
                else:
                    pending_name = full_name
            else:
                pending_name = ""

    if items:
        return pd.DataFrame(items)
    return _parse_items_from_text(raw_text)


# Pattern: a line with at least one word followed by a number (qty)
_ITEM_LINE_PAT = re.compile(
    r"^(.+?)\s+(\d+(?:\.\d+)?)\s*$",
)


def _parse_items_from_text(text: str) -> pd.DataFrame:
    """
    Best-effort item extraction from raw PDF text.

    Looks for lines matching "<product name>  <number>" pattern.

    Multi-line product names are handled by accumulating lines that do not
    end with a number as a *pending prefix*.  When the next matching line is
    found the prefix is prepended to form the complete product name.
    A blank line or a recognised header keyword resets the accumulator.
    """
    # Normalised keywords that should never appear as a product name and that
    # also reset the multi-line accumulator.
    _TEXT_SKIP = frozenset({
        "total", "subtotal", "page", "qty", "quantity", "item", "product",
        "received", "ordered", "price", "sku", "id", "line", "number",
        "description", "name", "unitprice", "unit",
    })

    items: List[Dict] = []
    pending: str = ""  # partial product name carried across lines

    for line in text.splitlines():
        line = line.strip()
        if not line:
            pending = ""
            continue

        m = _ITEM_LINE_PAT.match(line)
        if m:
            name = m.group(1).strip()
            qty_str = m.group(2)

            # Skip lines that look like dates or page numbers.
            if re.search(r"\d{4}", name) and len(name) < 12:
                pending = ""
                continue

            norm = re.sub(r"[^a-z0-9]", "", name.lower())
            if norm in _TEXT_SKIP:
                pending = ""
                continue

            full_name = " ".join(filter(None, [pending, name]))
            full_name = re.sub(r"\s+", " ", full_name).strip()

            try:
                qty = float(qty_str)
                items.append({"item_name": full_name, "qty": qty})
            except ValueError:
                pass
            pending = ""
        else:
            # Line has no trailing number – might be the first part of a
            # multi-line product name.  Skip lines that look like dates,
            # times, or header keywords so they don't pollute product names.
            norm = re.sub(r"[^a-z0-9]", "", line.lower())
            if norm in _TEXT_SKIP:
                pending = ""
            elif re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", line):
                # Looks like a date string (e.g. "03/15/2025 14:32") – skip.
                pending = ""
            else:
                pending = " ".join(filter(None, [pending, line]))

    if not items:
        return pd.DataFrame(columns=["item_name", "qty"])
    return pd.DataFrame(items)


# ---------------------------------------------------------------------------
# Manifest CSV / XLSX parsing  (Dutchie-style receiving exports)
# ---------------------------------------------------------------------------

# Header keywords that indicate the manifest header row (normed: lower, alnum only).
_MANIFEST_HEADER_NAME_KEYWORDS: frozenset = frozenset({
    "product", "item", "itemname", "productname", "description",
    "name", "productdescription", "itemdescription",
})

_MANIFEST_HEADER_QTY_KEYWORDS_PREFERRED: frozenset = frozenset({
    "receivedqty", "qtyreceived", "receivedquantity", "quantityreceived",
    "received", "recqty", "recvqty",
})

_MANIFEST_HEADER_QTY_KEYWORDS_FALLBACK: frozenset = frozenset({
    "qty", "quantity", "units", "count", "unitcount",
})

# All normalised strings we treat as header cells (used to detect repeated headers).
_MANIFEST_ALL_HEADER_NORMS: frozenset = frozenset(
    _MANIFEST_HEADER_NAME_KEYWORDS
    | _MANIFEST_HEADER_QTY_KEYWORDS_PREFERRED
    | _MANIFEST_HEADER_QTY_KEYWORDS_FALLBACK
    | {
        "packageid", "package", "licensenumber", "license", "batch",
        "location", "unitprice", "price", "sku", "id", "type",
        "category", "brand", "uom", "unit", "vendor", "manifest",
        "orderedqty", "ordered", "linenumber", "ln", "no", "number",
        "strain", "transfer", "weight",
    }
)


def _norm_cell(v: object) -> str:
    """Return a normalised (lower, alnum-only) version of a cell value."""
    return re.sub(r"[^a-z0-9]", "", str(v).lower())


def parse_manifest_csv_xlsx_bytes(
    raw_bytes: bytes,
    filename: str = "",
) -> Tuple[Optional[pd.Timestamp], pd.DataFrame, str]:
    """
    Extract received datetime and item table from a Dutchie-style CSV or XLSX
    delivery / receiving export.

    Handles:
    * Arbitrary preamble / metadata rows above the real header row.
    * Repeated header rows that appear again mid-file (skipped automatically).
    * Multi-line product names split across continuation rows (rows that have
      name text but a blank quantity cell).  Fragments are accumulated and
      joined with a single space when the row with a numeric quantity arrives.
    * Quoted CSV cells containing embedded newlines – whitespace is collapsed
      before processing.
    * Optional extra columns (Package ID, Batch, License Number, Location) are
      retained when present.

    Parameters
    ----------
    raw_bytes:
        Raw file bytes of the CSV or XLSX manifest.
    filename:
        Original file name (used to detect XLSX vs CSV).

    Returns
    -------
    received_dt : pd.Timestamp or None
        First date/time detected in the preamble rows.
    items_df : DataFrame
        Columns: ``item_name`` (str), ``qty`` (float), plus any optional
        columns detected in the header (``package_id``, ``batch``,
        ``license_number``, ``location``).
    raw_text : str
        Plain-text representation of the file (for debug / download).
    """
    is_xlsx = filename.lower().endswith((".xlsx", ".xls"))
    raw_text = ""

    try:
        if is_xlsx:
            raw_df = pd.read_excel(BytesIO(raw_bytes), header=None, dtype=str)
        else:
            raw_df = pd.read_csv(
                BytesIO(raw_bytes),
                header=None,
                dtype=str,
                on_bad_lines="skip",
            )

        # Build raw_text for debugging / date extraction from preamble.
        raw_text = raw_df.fillna("").astype(str).apply(
            lambda r: ",".join(r.tolist()), axis=1
        ).str.cat(sep="\n")

        rows: List[List[str]] = []
        for _, r in raw_df.iterrows():
            rows.append([
                re.sub(r"\s+", " ", str(v).replace("\n", " ")).strip()
                if pd.notna(v) and str(v) not in ("nan", "None", "")
                else ""
                for v in r
            ])

    except Exception:
        return None, pd.DataFrame(columns=["item_name", "qty"]), raw_text

    # ── Step 1: find the header row ──────────────────────────────────────────
    # Scan up to the first 40 rows for a row that contains at least one
    # name-column keyword AND at least one quantity-column keyword.

    header_row_idx: Optional[int] = None
    name_col_idx: Optional[int] = None
    qty_col_idx: Optional[int] = None
    optional_col_map: Dict[str, int] = {}  # canonical_name → column index

    max_scan = min(40, len(rows))
    for row_i, row in enumerate(rows[:max_scan]):
        norm_cells = [_norm_cell(c) for c in row]
        has_name = any(nc in _MANIFEST_HEADER_NAME_KEYWORDS for nc in norm_cells)
        has_qty = any(
            nc in _MANIFEST_HEADER_QTY_KEYWORDS_PREFERRED
            or nc in _MANIFEST_HEADER_QTY_KEYWORDS_FALLBACK
            for nc in norm_cells
        )
        if not (has_name and has_qty):
            continue

        # Found the header row.
        header_row_idx = row_i

        # Identify name column (first match).
        for col_i, nc in enumerate(norm_cells):
            if nc in _MANIFEST_HEADER_NAME_KEYWORDS and name_col_idx is None:
                name_col_idx = col_i

        # Identify qty column – prefer explicit "received" variants.
        for col_i, nc in enumerate(norm_cells):
            if nc in _MANIFEST_HEADER_QTY_KEYWORDS_PREFERRED and qty_col_idx is None:
                qty_col_idx = col_i
                break
        if qty_col_idx is None:
            for col_i, nc in enumerate(norm_cells):
                if nc in _MANIFEST_HEADER_QTY_KEYWORDS_FALLBACK and qty_col_idx is None:
                    qty_col_idx = col_i

        # Detect optional columns.
        _OPT_MAP = {
            "packageid": "package_id",
            "package": "package_id",
            "batch": "batch",
            "licensenumber": "license_number",
            "license": "license_number",
            "location": "location",
        }
        for col_i, nc in enumerate(norm_cells):
            if col_i in (name_col_idx, qty_col_idx):
                continue
            if nc in _OPT_MAP and _OPT_MAP[nc] not in optional_col_map:
                optional_col_map[_OPT_MAP[nc]] = col_i

        break

    # ── Step 2: extract received date from preamble rows (priority-ranked) ────
    preamble_rows = rows[: (header_row_idx if header_row_idx is not None else max_scan)]
    received_dt = _extract_received_dt_from_rows(preamble_rows, raw_text)

    if header_row_idx is None or name_col_idx is None or qty_col_idx is None:
        return received_dt, pd.DataFrame(columns=["item_name", "qty"]), raw_text

    # ── Step 3: process data rows ─────────────────────────────────────────────
    items: List[Dict] = []
    pending_name: str = ""  # accumulated name fragments from continuation rows
    pending_opt: Dict[str, str] = {}  # optional-column values from first fragment row

    for row in rows[header_row_idx + 1:]:
        # Pad row to at least cover all known column indices.
        max_col = max(name_col_idx, qty_col_idx, *optional_col_map.values(), 0)
        while len(row) <= max_col:
            row.append("")

        name_val = row[name_col_idx]
        qty_str = row[qty_col_idx]

        # Collapse embedded newlines and extra whitespace in the name cell.
        name_val = re.sub(r"\s+", " ", name_val).strip()

        # Skip completely blank rows.
        if not any(row):
            pending_name = ""
            pending_opt = {}
            continue

        # Skip rows that are repeated header instances.
        name_norm = _norm_cell(name_val)
        if name_norm in _MANIFEST_HEADER_NAME_KEYWORDS:
            pending_name = ""
            pending_opt = {}
            continue

        qty = _try_parse_float(qty_str)

        if qty is None and name_val:
            # Continuation row: name text but no quantity yet.
            if not pending_name:
                # First fragment – also grab optional columns from this row.
                for opt_key, opt_col in optional_col_map.items():
                    v = row[opt_col] if opt_col < len(row) else ""
                    if v:
                        pending_opt[opt_key] = v
            pending_name = " ".join(filter(None, [pending_name, name_val]))

        elif qty is not None:
            # Row with quantity – commit item.
            full_name = " ".join(filter(None, [pending_name, name_val]))
            full_name = re.sub(r"\s+", " ", full_name).strip()
            if full_name:
                entry: Dict = {"item_name": full_name, "qty": qty}
                # Optional columns: prefer values from the qty row, fall back to
                # what was collected from earlier continuation rows.
                for opt_key, opt_col in optional_col_map.items():
                    v = row[opt_col] if opt_col < len(row) else ""
                    entry[opt_key] = v or pending_opt.get(opt_key, "")
                items.append(entry)
            pending_name = ""
            pending_opt = {}

        else:
            # Empty name and no qty – reset accumulator.
            pending_name = ""
            pending_opt = {}

    if not items:
        return received_dt, pd.DataFrame(columns=["item_name", "qty"]), raw_text

    items_df = pd.DataFrame(items)
    # Enforce strict typing to prevent int + str errors downstream.
    items_df["item_name"] = items_df["item_name"].astype(str).str.strip()
    items_df["qty"] = pd.to_numeric(items_df["qty"], errors="coerce").fillna(0.0)
    return received_dt, items_df, raw_text


# ---------------------------------------------------------------------------
# KPI computation
# ---------------------------------------------------------------------------

DELIVERY_WINDOW_DAYS = 14  # default comparison window


def compute_delivery_kpis(
    sales_df: pd.DataFrame,
    delivery_dt: pd.Timestamp,
    window_days: int = DELIVERY_WINDOW_DAYS,
    delivered_names: Optional[List[str]] = None,
) -> Dict:
    """
    Compute before/after KPIs for a single delivery.

    Parameters
    ----------
    sales_df:
        Order-level DataFrame with at minimum columns
        ``order_time`` (datetime), ``net_sales`` (float), ``product_name`` (str).
        One row = one order line item.
    delivery_dt:
        The delivery received timestamp.
    window_days:
        Number of days before / after to include in comparison.
    delivered_names:
        Sales-side product names that match this delivery's manifest items.
        Pass ``None`` or ``[]`` to skip delivered-items sub-KPIs.

    Returns
    -------
    dict with keys:
      net_sales_before, net_sales_after, net_sales_lift_abs, net_sales_lift_pct
      orders_before, orders_after, orders_lift_abs, orders_lift_pct
      delivered_sales_before, delivered_sales_after, delivered_sales_lift_abs,
      delivered_sales_lift_pct, delivered_units_before, delivered_units_after,
      delivered_units_lift_abs, delivered_units_lift_pct
      top_items : DataFrame with columns item_name, sales_lift, units_lift (sorted)
    """
    dt = pd.Timestamp(delivery_dt)
    before_start = dt - timedelta(days=window_days)
    after_end = dt + timedelta(days=window_days)

    before_mask = (sales_df["order_time"] >= before_start) & (sales_df["order_time"] < dt)
    after_mask = (sales_df["order_time"] >= dt) & (sales_df["order_time"] < after_end)

    before = sales_df[before_mask]
    after = sales_df[after_mask]

    def _lift(b: float, a: float) -> Tuple[float, float]:
        abs_lift = a - b
        pct_lift = (abs_lift / b * 100.0) if b != 0 else float("nan")
        return round(abs_lift, 2), round(pct_lift, 2) if not pd.isna(pct_lift) else float("nan")

    net_b = float(before["net_sales"].sum())
    net_a = float(after["net_sales"].sum())
    net_lift_abs, net_lift_pct = _lift(net_b, net_a)

    # Traffic proxy: unique order IDs (or row count if no order_id)
    if "order_id" in sales_df.columns:
        orders_b = int(before["order_id"].nunique())
        orders_a = int(after["order_id"].nunique())
    else:
        orders_b = len(before)
        orders_a = len(after)

    orders_lift_abs, orders_lift_pct = _lift(float(orders_b), float(orders_a))

    result: Dict = {
        "net_sales_before": net_b,
        "net_sales_after": net_a,
        "net_sales_lift_abs": net_lift_abs,
        "net_sales_lift_pct": net_lift_pct,
        "orders_before": orders_b,
        "orders_after": orders_a,
        "orders_lift_abs": int(orders_lift_abs) if not pd.isna(orders_lift_abs) else None,
        "orders_lift_pct": orders_lift_pct,
        "delivered_sales_before": None,
        "delivered_sales_after": None,
        "delivered_sales_lift_abs": None,
        "delivered_sales_lift_pct": None,
        "delivered_units_before": None,
        "delivered_units_after": None,
        "delivered_units_lift_abs": None,
        "delivered_units_lift_pct": None,
        "top_items": pd.DataFrame(),
    }

    if delivered_names:
        delivered_set = {n.lower() for n in delivered_names}
        del_mask = sales_df["product_name"].str.lower().isin(delivered_set)

        before_del = before[before["product_name"].str.lower().isin(delivered_set)]
        after_del = after[after["product_name"].str.lower().isin(delivered_set)]

        del_net_b = float(before_del["net_sales"].sum())
        del_net_a = float(after_del["net_sales"].sum())
        del_net_lift_abs, del_net_lift_pct = _lift(del_net_b, del_net_a)

        del_units_b: float = 0.0
        del_units_a: float = 0.0
        if "units_sold" in sales_df.columns:
            del_units_b = float(before_del["units_sold"].sum())
            del_units_a = float(after_del["units_sold"].sum())
        del_units_lift_abs, del_units_lift_pct = _lift(del_units_b, del_units_a)

        result.update({
            "delivered_sales_before": del_net_b,
            "delivered_sales_after": del_net_a,
            "delivered_sales_lift_abs": del_net_lift_abs,
            "delivered_sales_lift_pct": del_net_lift_pct,
            "delivered_units_before": del_units_b,
            "delivered_units_after": del_units_a,
            "delivered_units_lift_abs": del_units_lift_abs,
            "delivered_units_lift_pct": del_units_lift_pct,
        })

        # Top items by lift
        top_rows: List[Dict] = []
        for name in delivered_names:
            name_lower = name.lower()
            b_rows = before[before["product_name"].str.lower() == name_lower]
            a_rows = after[after["product_name"].str.lower() == name_lower]
            item_net_b = float(b_rows["net_sales"].sum())
            item_net_a = float(a_rows["net_sales"].sum())
            item_units_b = float(b_rows["units_sold"].sum()) if "units_sold" in sales_df.columns else 0.0
            item_units_a = float(a_rows["units_sold"].sum()) if "units_sold" in sales_df.columns else 0.0
            s_lift, _ = _lift(item_net_b, item_net_a)
            u_lift, _ = _lift(item_units_b, item_units_a)
            top_rows.append({
                "item_name": name,
                "net_sales_before": item_net_b,
                "net_sales_after": item_net_a,
                "sales_lift": s_lift,
                "units_before": item_units_b,
                "units_after": item_units_a,
                "units_lift": u_lift,
            })

        if top_rows:
            result["top_items"] = (
                pd.DataFrame(top_rows)
                .sort_values("sales_lift", ascending=False)
                .reset_index(drop=True)
            )

    return result


# ---------------------------------------------------------------------------
# Week-over-week (same weekday) KPI function
# ---------------------------------------------------------------------------

def compute_weekday_wow_kpis(
    sales_df: pd.DataFrame,
    delivery_dt: pd.Timestamp,
    delivered_names: Optional[List[str]] = None,
) -> Dict:
    """
    Compare the 24-hour delivery day to the same weekday exactly 7 days prior.

    For example: delivery on Thu 2026-03-19 compares Thu 2026-03-19 00:00–23:59
    to Thu 2026-03-12 00:00–23:59.

    Parameters
    ----------
    sales_df:
        Order-level DataFrame with at minimum columns
        ``order_time`` (datetime), ``net_sales`` (float), ``product_name`` (str).
    delivery_dt:
        The delivery received timestamp.  Only the calendar date is used;
        both the delivery day and the prior-week day run midnight-to-midnight.
    delivered_names:
        Sales-side product names matched to this delivery's manifest items.
        Pass ``None`` or ``[]`` to skip delivered-items sub-KPIs.

    Returns
    -------
    dict with the same keys as :func:`compute_delivery_kpis` plus:
      ``delivery_day_start`` : pd.Timestamp – midnight of the delivery day
      ``prior_day_start``    : pd.Timestamp – midnight of the prior-week same weekday
    In this function "before" = prior-week same weekday, "after" = delivery day.
    """
    dt = pd.Timestamp(delivery_dt)
    day_start = dt.normalize()  # midnight on the delivery calendar day
    day_end = day_start + timedelta(days=1)
    prior_start = day_start - timedelta(days=7)
    prior_end = prior_start + timedelta(days=1)

    delivery_mask = (sales_df["order_time"] >= day_start) & (sales_df["order_time"] < day_end)
    prior_mask = (sales_df["order_time"] >= prior_start) & (sales_df["order_time"] < prior_end)

    delivery_day = sales_df[delivery_mask]
    prior_day = sales_df[prior_mask]

    def _lift(b: float, a: float) -> Tuple[float, float]:
        abs_lift = a - b
        pct_lift = (abs_lift / b * 100.0) if b != 0 else float("nan")
        return round(abs_lift, 2), round(pct_lift, 2) if not pd.isna(pct_lift) else float("nan")

    net_prior = float(prior_day["net_sales"].sum())
    net_delivery = float(delivery_day["net_sales"].sum())
    net_lift_abs, net_lift_pct = _lift(net_prior, net_delivery)

    if "order_id" in sales_df.columns:
        orders_prior = int(prior_day["order_id"].nunique())
        orders_delivery = int(delivery_day["order_id"].nunique())
    else:
        orders_prior = len(prior_day)
        orders_delivery = len(delivery_day)

    orders_lift_abs, orders_lift_pct = _lift(float(orders_prior), float(orders_delivery))

    result: Dict = {
        "net_sales_before": net_prior,
        "net_sales_after": net_delivery,
        "net_sales_lift_abs": net_lift_abs,
        "net_sales_lift_pct": net_lift_pct,
        "orders_before": orders_prior,
        "orders_after": orders_delivery,
        "orders_lift_abs": int(orders_lift_abs) if not pd.isna(orders_lift_abs) else None,
        "orders_lift_pct": orders_lift_pct,
        "delivered_sales_before": None,
        "delivered_sales_after": None,
        "delivered_sales_lift_abs": None,
        "delivered_sales_lift_pct": None,
        "delivered_units_before": None,
        "delivered_units_after": None,
        "delivered_units_lift_abs": None,
        "delivered_units_lift_pct": None,
        "top_items": pd.DataFrame(),
        "delivery_day_start": day_start,
        "prior_day_start": prior_start,
    }

    if delivered_names:
        delivered_set = {n.lower() for n in delivered_names}

        del_delivery = delivery_day[delivery_day["product_name"].str.lower().isin(delivered_set)]
        del_prior = prior_day[prior_day["product_name"].str.lower().isin(delivered_set)]

        del_net_prior = float(del_prior["net_sales"].sum())
        del_net_delivery = float(del_delivery["net_sales"].sum())
        del_net_lift_abs, del_net_lift_pct = _lift(del_net_prior, del_net_delivery)

        del_units_prior: float = 0.0
        del_units_delivery: float = 0.0
        if "units_sold" in sales_df.columns:
            del_units_prior = float(del_prior["units_sold"].sum())
            del_units_delivery = float(del_delivery["units_sold"].sum())
        del_units_lift_abs, del_units_lift_pct = _lift(del_units_prior, del_units_delivery)

        result.update({
            "delivered_sales_before": del_net_prior,
            "delivered_sales_after": del_net_delivery,
            "delivered_sales_lift_abs": del_net_lift_abs,
            "delivered_sales_lift_pct": del_net_lift_pct,
            "delivered_units_before": del_units_prior,
            "delivered_units_after": del_units_delivery,
            "delivered_units_lift_abs": del_units_lift_abs,
            "delivered_units_lift_pct": del_units_lift_pct,
        })

        top_rows: List[Dict] = []
        for name in delivered_names:
            name_lower = name.lower()
            a_rows = delivery_day[delivery_day["product_name"].str.lower() == name_lower]
            b_rows = prior_day[prior_day["product_name"].str.lower() == name_lower]
            item_net_prior = float(b_rows["net_sales"].sum())
            item_net_delivery = float(a_rows["net_sales"].sum())
            item_units_prior = (
                float(b_rows["units_sold"].sum()) if "units_sold" in sales_df.columns else 0.0
            )
            item_units_delivery = (
                float(a_rows["units_sold"].sum()) if "units_sold" in sales_df.columns else 0.0
            )
            s_lift, _ = _lift(item_net_prior, item_net_delivery)
            u_lift, _ = _lift(item_units_prior, item_units_delivery)
            top_rows.append({
                "item_name": name,
                "net_sales_before": item_net_prior,
                "net_sales_after": item_net_delivery,
                "sales_lift": s_lift,
                "units_before": item_units_prior,
                "units_after": item_units_delivery,
                "units_lift": u_lift,
            })

        if top_rows:
            result["top_items"] = (
                pd.DataFrame(top_rows)
                .sort_values("sales_lift", ascending=False)
                .reset_index(drop=True)
            )

    return result


# ---------------------------------------------------------------------------
# Week-over-week time-series builder (two comparable daily/hourly series)
# ---------------------------------------------------------------------------

def build_wow_time_series(
    sales_df: pd.DataFrame,
    delivery_dt: pd.Timestamp,
    granularity: str = "daily",
    delivered_names: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build two time-series DataFrames for a week-over-week chart overlay:

    1. ``delivery_ts`` – the delivery day (midnight → next midnight).
    2. ``prior_ts``    – the same weekday 7 days earlier.

    Both DataFrames have the same column schema as :func:`build_time_series`
    (period, total_net_sales, delivered_net_sales, non_delivered_net_sales,
    order_count).  ``period`` values in ``prior_ts`` are shifted forward by
    7 days so both series share the same x-axis when overlaid.

    Parameters
    ----------
    sales_df, delivery_dt, granularity, delivered_names:
        Same semantics as :func:`build_time_series`.

    Returns
    -------
    (delivery_ts, prior_ts_shifted)
    """
    dt = pd.Timestamp(delivery_dt)
    day_start = dt.normalize()
    day_end = day_start + timedelta(days=1)
    prior_start = day_start - timedelta(days=7)
    prior_end = prior_start + timedelta(days=1)

    # Defensively coerce order_time to datetime so .dt accessors and
    # timedelta arithmetic work even when the caller passes object-dtype data.
    sales_df = sales_df.copy()
    sales_df["order_time"] = pd.to_datetime(sales_df["order_time"], errors="coerce")
    sales_df = sales_df.dropna(subset=["order_time"])

    def _build_day_ts(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        window = sales_df[
            (sales_df["order_time"] >= start) & (sales_df["order_time"] < end)
        ].copy()

        if window.empty:
            return pd.DataFrame(columns=[
                "period", "total_net_sales",
                "delivered_net_sales", "non_delivered_net_sales",
                "order_count",
            ])

        freq = "h" if granularity == "hourly" else "D"
        window["period"] = window["order_time"].dt.floor(freq)

        delivered_set = {n.lower() for n in delivered_names} if delivered_names else set()
        window["_is_delivered"] = window["product_name"].str.lower().isin(delivered_set)

        agg_total = (
            window.groupby("period")
            .agg(
                total_net_sales=("net_sales", "sum"),
                order_count=(
                    ("order_id", "nunique") if "order_id" in window.columns
                    else ("net_sales", "count")
                ),
            )
            .reset_index()
        )

        if delivered_set:
            agg_del = (
                window[window["_is_delivered"]]
                .groupby("period")["net_sales"]
                .sum()
                .rename("delivered_net_sales")
                .reset_index()
            )
            agg_non_del = (
                window[~window["_is_delivered"]]
                .groupby("period")["net_sales"]
                .sum()
                .rename("non_delivered_net_sales")
                .reset_index()
            )
            ts = agg_total.merge(agg_del, on="period", how="left")
            ts = ts.merge(agg_non_del, on="period", how="left")
        else:
            ts = agg_total.copy()
            ts["delivered_net_sales"] = 0.0
            ts["non_delivered_net_sales"] = ts["total_net_sales"]

        ts = ts.fillna(0.0).sort_values("period").reset_index(drop=True)
        return ts

    delivery_ts = _build_day_ts(day_start, day_end)
    prior_ts = _build_day_ts(prior_start, prior_end)

    # Shift prior_ts period forward by 7 days so both series share the same x-axis.
    # Coerce to datetime first in case groupby produced an object-dtype column.
    if not prior_ts.empty:
        prior_ts = prior_ts.copy()
        prior_ts["period"] = pd.to_datetime(prior_ts["period"])
        prior_ts["period"] = prior_ts["period"] + timedelta(days=7)

    return delivery_ts, prior_ts


# ---------------------------------------------------------------------------
# Time-series builder
# ---------------------------------------------------------------------------

def build_time_series(
    sales_df: pd.DataFrame,
    delivery_dt: pd.Timestamp,
    window_days: int = DELIVERY_WINDOW_DAYS,
    granularity: str = "daily",
    delivered_names: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Build a time-series DataFrame for the line chart.

    Parameters
    ----------
    sales_df:
        Parsed sales DataFrame (see :func:`parse_sales_report_bytes`).
    delivery_dt:
        Delivery received timestamp.
    window_days:
        Days before/after to include.
    granularity:
        ``"daily"`` or ``"hourly"``.
    delivered_names:
        Sales product names matched to this manifest's items.

    Returns
    -------
    DataFrame with columns:
        period, total_net_sales, delivered_net_sales, non_delivered_net_sales, order_count
    """
    dt = pd.Timestamp(delivery_dt)
    start = dt - timedelta(days=window_days)
    end = dt + timedelta(days=window_days)

    # Defensively coerce order_time to datetime so .dt accessors work even
    # when the caller passes object-dtype data (e.g. string timestamps).
    sales_df = sales_df.copy()
    sales_df["order_time"] = pd.to_datetime(sales_df["order_time"], errors="coerce")
    sales_df = sales_df.dropna(subset=["order_time"])

    window = sales_df[
        (sales_df["order_time"] >= start) & (sales_df["order_time"] < end)
    ].copy()

    if window.empty:
        return pd.DataFrame(columns=[
            "period", "total_net_sales",
            "delivered_net_sales", "non_delivered_net_sales",
            "order_count",
        ])

    freq = "h" if granularity == "hourly" else "D"
    window["period"] = window["order_time"].dt.floor(freq)

    delivered_set: set = set()
    if delivered_names:
        delivered_set = {n.lower() for n in delivered_names}

    window["_is_delivered"] = window["product_name"].str.lower().isin(delivered_set)

    agg_total = (
        window.groupby("period")
        .agg(
            total_net_sales=("net_sales", "sum"),
            order_count=("order_id", "nunique") if "order_id" in window.columns else ("net_sales", "count"),
        )
        .reset_index()
    )

    if delivered_set:
        agg_del = (
            window[window["_is_delivered"]]
            .groupby("period")["net_sales"]
            .sum()
            .rename("delivered_net_sales")
            .reset_index()
        )
        agg_non_del = (
            window[~window["_is_delivered"]]
            .groupby("period")["net_sales"]
            .sum()
            .rename("non_delivered_net_sales")
            .reset_index()
        )
        ts = agg_total.merge(agg_del, on="period", how="left")
        ts = ts.merge(agg_non_del, on="period", how="left")
    else:
        ts = agg_total.copy()
        ts["delivered_net_sales"] = 0.0
        ts["non_delivered_net_sales"] = ts["total_net_sales"]

    ts = ts.fillna(0.0).sort_values("period").reset_index(drop=True)
    return ts
