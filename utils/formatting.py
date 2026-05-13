from typing import Any

def fmt_currency(v: Any) -> str:
    try:
        return f"${float(v):,.2f}"
    except Exception:
        return "N/A"

def fmt_percent(v: Any) -> str:
    try:
        return f"{float(v):.1f}%"
    except Exception:
        return "N/A"

def fmt_grams(v: Any) -> str:
    try:
        return f"{float(v):,.1f} g"
    except Exception:
        return "N/A"

def fmt_units(v: Any) -> str:
    try:
        return f"{int(float(v)):,}"
    except Exception:
        return "N/A"

def fmt_na(v: Any, default: str = "N/A") -> str:
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default
