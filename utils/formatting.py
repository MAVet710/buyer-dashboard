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


def format_currency(v: Any) -> str:
    return fmt_currency(v)


def format_percent(v: Any) -> str:
    return fmt_percent(v)


def format_weight_g(v: Any) -> str:
    return fmt_grams(v)


def format_units(v: Any) -> str:
    return fmt_units(v)


def format_integer(v: Any) -> str:
    try:
        return f"{int(float(v)):,}"
    except Exception:
        return "N/A"


def format_na(v: Any, default: str = "N/A") -> str:
    return fmt_na(v, default=default)


def format_cost_per_gram(v: Any) -> str:
    try:
        return f"${float(v):,.2f}/g"
    except Exception:
        return "N/A"


def humanize_column_label(name: Any) -> str:
    s = str(name or "").strip().replace("_", " ")
    return " ".join(w.capitalize() for w in s.split())
