from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any, Iterable, Mapping

import pandas as pd

MAX_CELL_CHARS = 600
SENSITIVE_PATTERNS = (
    "password", "passwd", "password_hash", "secret", "token", "api_key", "apikey",
    "authorization", "session", "cookie", "encryption", "private_key", "oauth",
    "customer_name", "patient", "email", "phone", "home_address", "address",
    "date_of_birth", "dob", "ssn", "social_security", "employee", "username",
    "created_by", "updated_by", "counted_by", "recorded_by", "actor", "user_id",
)
BUSINESS_COLUMN_TOKENS = {
    "product", "item", "sku", "upc", "brand", "strain", "category", "type", "size",
    "weight", "unit", "package", "lot", "batch", "manifest", "vendor", "supplier",
    "quantity", "qty", "available", "onhand", "inventory", "cost", "price", "margin",
    "sales", "sold", "revenue", "discount", "promotion", "velocity", "days", "weeks",
    "age", "aging", "expiration", "expiry", "received", "delivery", "order", "status",
    "forecast", "reorder", "budget", "lead", "moq", "case", "pack", "room", "phase",
    "plant", "harvest", "machine", "capacity", "yield", "scrap", "downtime", "throughput",
    "reservation", "allocation", "fill", "shortage", "invoice", "balance", "due", "payment",
    "coa", "testing", "terpene", "method", "process", "sop", "quality", "variance", "scan",
    "audit", "source", "file", "dataset", "mapping", "freshness", "row", "column", "license",
    "facility", "organization", "operation", "state", "date", "time", "value", "amount",
    "description", "notes", "reason", "reference", "expected", "actual", "planned", "finished",
}
BUSINESS_COMPOUND_NAMES = {
    "on_hand", "onhand", "units_sold", "unit_cost", "retail_price", "days_of_supply",
    "days_on_hand", "days_cover", "avg_daily_units", "daily_velocity", "gross_margin",
    "gross_margin_pct", "open_po", "open_po_quantity", "reorder_point", "reorder_qty",
    "suggested_quantity", "fulfilled_quantity", "outstanding_quantity", "received_quantity",
}

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_SSN_RE = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}(?!\d)")
_SECRET_RE = re.compile(r"(?i)\b(?:bearer|api[_ -]?key|token|secret|password)\s*[:=]?\s+[A-Za-z0-9_./+\-=]{8,}")


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")


def is_sensitive_name(name: str) -> bool:
    normalized = norm(name)
    compact = normalized.replace("_", "")
    return any(norm(pattern) in normalized or norm(pattern).replace("_", "") in compact for pattern in SENSITIVE_PATTERNS)


def is_business_column(name: str) -> bool:
    if is_sensitive_name(name):
        return False
    normalized = norm(name)
    compact = normalized.replace("_", "")
    tokens = {token for token in normalized.split("_") if token}
    if tokens & BUSINESS_COLUMN_TOKENS:
        return True
    for candidate in BUSINESS_COMPOUND_NAMES:
        candidate_norm = norm(candidate)
        if normalized == candidate_norm or compact == candidate_norm.replace("_", ""):
            return True
    return False


def sanitize_text(value: Any, *, max_chars: int = 16000) -> str:
    """Best-effort PII/credential redaction for optional feedback/eval text storage."""
    text = str(value or "")[: max(0, int(max_chars))]
    text = _SECRET_RE.sub("[REDACTED_CREDENTIAL]", text)
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _SSN_RE.sub("[REDACTED_SSN]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    return text


def safe_scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)[:MAX_CELL_CHARS]


def allowed_columns(
    frame: pd.DataFrame,
    explicit: Iterable[str] | None = None,
    *,
    allow_business_columns: bool = False,
    sensitive_columns: Iterable[str] = (),
) -> list[str]:
    blocked = {norm(value) for value in sensitive_columns}
    explicit_norm = {norm(value) for value in explicit or ()}
    output: list[str] = []
    for raw in frame.columns:
        name = str(raw)
        normalized = norm(name)
        if normalized in blocked or is_sensitive_name(name):
            continue
        if explicit_norm and normalized in explicit_norm:
            output.append(name)
        elif not explicit_norm and allow_business_columns and is_business_column(name):
            output.append(name)
    return output


def sanitize_frame(
    frame: pd.DataFrame,
    *,
    explicit_columns: Iterable[str] | None = None,
    allow_business_columns: bool = False,
    sensitive_columns: Iterable[str] = (),
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    columns = allowed_columns(
        frame,
        explicit_columns,
        allow_business_columns=allow_business_columns,
        sensitive_columns=sensitive_columns,
    )
    if not columns:
        return pd.DataFrame(index=frame.index)
    return frame.loc[:, columns].copy()


def records(frame: pd.DataFrame, *, limit: int = 50, columns: Iterable[str] | None = None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    selected = list(columns or frame.columns)
    selected = [column for column in selected if column in frame.columns and not is_sensitive_name(column)]
    subset = frame.loc[:, selected].head(max(1, min(int(limit), 100)))
    return [{str(key): safe_scalar(value) for key, value in row.items()} for row in subset.to_dict(orient="records")]


def sanitize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in value.items():
        if is_sensitive_name(str(key)):
            continue
        if isinstance(item, Mapping):
            output[str(key)] = sanitize_mapping(item)
        elif isinstance(item, (list, tuple)):
            output[str(key)] = [sanitize_mapping(v) if isinstance(v, Mapping) else safe_scalar(v) for v in item[:100]]
        else:
            output[str(key)] = safe_scalar(item)
    return output
