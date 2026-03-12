"""
Dutchie Live Data Client
========================

Stub integration module for Dutchie POS / Dutchie Ecommerce APIs.

When Dutchie API credentials become available, implement the real API calls
in the ``fetch_dutchie_data`` function below.  The rest of the app is already
wired to consume the DataFrames this function returns.

Configuration
-------------
Set the following in ``.streamlit/secrets.toml`` **or** as environment
variables (environment variables take lower priority than secrets):

    [dutchie]
    DUTCHIE_API_KEY        = "your-api-key"
    DUTCHIE_CLIENT_ID      = "your-client-id"
    DUTCHIE_CLIENT_SECRET  = "your-client-secret"
    DUTCHIE_BASE_URL       = "https://api.dutchie.com"
    DUTCHIE_LOCATION_ID    = "your-location-id"

See ``docs/dutchie.md`` for detailed setup instructions and a description
of the expected DataFrame schemas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd

try:
    import streamlit as st
    _STREAMLIT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _STREAMLIT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class DutchieConfig:
    """Holds all credentials and settings needed to call the Dutchie API."""

    api_key: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    base_url: str = "https://api.dutchie.com"
    location_id: Optional[str] = None

    @classmethod
    def from_env_and_secrets(cls) -> "DutchieConfig":
        """
        Build a DutchieConfig by reading from Streamlit secrets (when running
        inside Streamlit) and then falling back to environment variables.

        Priority: ``st.secrets`` > ``os.environ``.
        Supports both a flat key format (``DUTCHIE_API_KEY``) and a nested
        ``[dutchie]`` table in ``secrets.toml``.
        """

        def _get(key: str, default: Optional[str] = None) -> Optional[str]:
            if _STREAMLIT_AVAILABLE:
                # Try nested [dutchie] section first, then flat top-level key
                try:
                    return str(st.secrets["dutchie"][key])
                except (KeyError, TypeError, AttributeError, FileNotFoundError):
                    pass
                try:
                    return str(st.secrets[key])
                except (KeyError, TypeError, AttributeError, FileNotFoundError):
                    pass
            return os.environ.get(key, default)

        return cls(
            api_key=_get("DUTCHIE_API_KEY"),
            client_id=_get("DUTCHIE_CLIENT_ID"),
            client_secret=_get("DUTCHIE_CLIENT_SECRET"),
            base_url=_get("DUTCHIE_BASE_URL") or "https://api.dutchie.com",
            location_id=_get("DUTCHIE_LOCATION_ID"),
        )

    def missing_keys(self) -> list:
        """Return a list of required config keys that are not yet set."""
        required: dict = {
            "DUTCHIE_API_KEY": self.api_key,
            "DUTCHIE_LOCATION_ID": self.location_id,
        }
        return [k for k, v in required.items() if not v]

    def is_configured(self) -> bool:
        """Return ``True`` only when all required keys are present."""
        return len(self.missing_keys()) == 0


# ---------------------------------------------------------------------------
# Return-type alias
# ---------------------------------------------------------------------------

# 5-tuple matching the session_state DataFrames the app expects:
#   (inv_df, sales_df, extra_sales_df, delivery_df, daily_sales_df)
DutchieDataBundle = Tuple[
    Optional[pd.DataFrame],  # inv_df        → st.session_state.inv_raw_df
    Optional[pd.DataFrame],  # sales_df      → st.session_state.sales_raw_df
    Optional[pd.DataFrame],  # extra_df      → st.session_state.extra_sales_df
    Optional[pd.DataFrame],  # delivery_df   → st.session_state.delivery_raw_df
    Optional[pd.DataFrame],  # daily_sales   → st.session_state.daily_sales_raw_df
]


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------

def fetch_dutchie_data(
    config: DutchieConfig,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    location_id: Optional[str] = None,
) -> Tuple[DutchieDataBundle, Optional[str]]:
    """
    Fetch live inventory and sales data from the Dutchie API.

    Parameters
    ----------
    config:
        A ``DutchieConfig`` instance (typically built via
        ``DutchieConfig.from_env_and_secrets()``).
    start_date:
        ISO 8601 date string (``YYYY-MM-DD``) for the beginning of the sales
        window.  Overrides ``config.start_date`` when supplied.
    end_date:
        ISO 8601 date string for the end of the sales window.
    location_id:
        Store / location identifier.  Overrides ``config.location_id``.

    Returns
    -------
    (bundle, error_message)
        ``bundle``
            5-tuple ``(inv_df, sales_df, extra_df, delivery_df, daily_sales_df)``.
            Any element may be ``None`` when not available.
        ``error_message``
            Human-readable string when something prevented a successful fetch,
            ``None`` when data was fetched successfully.

    Notes
    -----
    **This function is currently a stub.**  It validates credentials and
    returns ``None`` DataFrames with a descriptive status message.

    When you receive Dutchie API credentials, replace the stub section below
    (marked ``# TODO: implement real API call``) with real HTTP requests.

    Expected DataFrame schemas
    --------------------------
    Returned DataFrames should use column names that match the aliases already
    defined in ``app.py`` (``INV_NAME_ALIASES``, ``SALES_QTY_ALIASES``, etc.)
    so that downstream normalization works without changes.  Typical Dutchie
    API field names map as follows:

    **Inventory** (``inv_df``):
        ``product`` → product/item name
        ``category`` / ``subcategory`` → category
        ``available`` → units on hand
        ``batch`` / ``batchid`` → batch/lot ID
        ``room`` → room (use "Vault" for main saleable stock)
        ``cost`` → unit cost/COGS
        ``brand`` → brand/vendor name
        ``expirationdate`` → expiration date

    **Sales** (``sales_df`` / ``extra_df``):
        ``product`` → product name
        ``category`` → category
        ``quantitysold`` → units sold
        ``netsales`` → net sales revenue
        ``ordertime`` / ``orderdate`` → sale timestamp

    **Delivery** (``delivery_df``):
        ``receiveddate`` → delivery/received date
        ``product`` → product name (optional)
        ``quantity`` → received quantity (optional)

    **Daily Sales** (``daily_sales_df``):
        ``date`` → sale date
        ``netsales`` → net sales for that day
        ``category`` → category (optional)
    """

    _empty: DutchieDataBundle = (None, None, None, None, None)

    # ── 1. Validate credentials ──────────────────────────────────────────────
    if not config.is_configured():
        missing = config.missing_keys()
        msg = (
            "**Dutchie Live** is selected but the following secrets are not "
            f"configured: `{'`, `'.join(missing)}`.  "
            "See *docs/dutchie.md* for setup instructions."
        )
        return _empty, msg

    # ── 2. TODO: implement real API call ─────────────────────────────────────
    #
    # Replace this stub with real HTTP calls once credentials are available.
    # Example outline (requires: pip install requests):
    #
    #   import requests
    #
    #   headers = {"Authorization": f"Bearer {config.api_key}"}
    #   base = config.base_url.rstrip("/")
    #   loc = location_id or config.location_id
    #
    #   # Inventory snapshot
    #   inv_resp = requests.get(
    #       f"{base}/inventory/current",
    #       headers=headers,
    #       params={"locationId": loc},
    #       timeout=30,
    #   )
    #   inv_resp.raise_for_status()
    #   inv_df = pd.DataFrame(inv_resp.json()["data"])
    #
    #   # Product sales report
    #   sales_resp = requests.get(
    #       f"{base}/reports/product-sales",
    #       headers=headers,
    #       params={"locationId": loc, "startDate": start_date, "endDate": end_date},
    #       timeout=30,
    #   )
    #   sales_resp.raise_for_status()
    #   sales_df = pd.DataFrame(sales_resp.json()["data"])
    #
    #   # (Repeat for extra_df, delivery_df, daily_sales_df as needed)
    #
    #   return (inv_df, sales_df, None, delivery_df, daily_sales_df), None
    #
    # ─────────────────────────────────────────────────────────────────────────

    msg = (
        "Dutchie API credentials are configured ✅  "
        "Live data fetch is not yet implemented — "
        "add the real API calls inside `dutchie_client.py → fetch_dutchie_data`."
    )
    return _empty, msg
