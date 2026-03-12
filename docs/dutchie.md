# Dutchie Live Data Integration

This document explains how to configure Dutchie API credentials so the
**Buyer Dashboard** can pull live inventory and sales data instead of relying
on manually exported CSV/XLSX files.

---

## How it works

The app has a global **Data Input Mode** selector in the sidebar (visible on
every page):

| Mode | Behaviour |
|---|---|
| **📁 Uploads** (default) | Use manual CSV/XLSX exports — existing behaviour, unchanged. |
| **🔴 Dutchie Live** | Fetch live data from the Dutchie API and populate all dashboards automatically. |

When **Dutchie Live** is selected, the app calls
`fetch_dutchie_data()` in `dutchie_client.py` and stores the
resulting DataFrames directly into `st.session_state`, bypassing the upload
widgets.  All downstream charts, tables, and exports work identically because
the session-state variable names are unchanged.

---

## Required secrets / environment variables

| Key | Description | Required? |
|---|---|---|
| `DUTCHIE_API_KEY` | API key issued by Dutchie | **Required** |
| `DUTCHIE_LOCATION_ID` | Store / location identifier | **Required** |
| `DUTCHIE_CLIENT_ID` | OAuth client ID (if using OAuth flow) | Optional |
| `DUTCHIE_CLIENT_SECRET` | OAuth client secret | Optional |
| `DUTCHIE_BASE_URL` | Dutchie API base URL | Optional (default: `https://api.dutchie.com`) |

---

## Option 1 — Streamlit secrets (recommended for Streamlit Cloud)

Create or edit `.streamlit/secrets.toml` in the repository root:

```toml
[dutchie]
DUTCHIE_API_KEY       = "your-api-key-here"
DUTCHIE_LOCATION_ID   = "your-location-id"
DUTCHIE_CLIENT_ID     = ""          # leave blank if not using OAuth
DUTCHIE_CLIENT_SECRET = ""
DUTCHIE_BASE_URL      = "https://api.dutchie.com"
```

> ⚠️ **Do not commit `.streamlit/secrets.toml` to version control.**
> It is already listed in `.gitignore`.  On Streamlit Cloud, enter the
> secrets via the **Secrets** panel in your app settings instead.

### Flat format (alternative)

The app also accepts a flat (non-nested) format:

```toml
DUTCHIE_API_KEY     = "your-api-key-here"
DUTCHIE_LOCATION_ID = "your-location-id"
```

---

## Option 2 — Environment variables (local dev / Docker)

Export the variables before launching the app:

```bash
export DUTCHIE_API_KEY="your-api-key-here"
export DUTCHIE_LOCATION_ID="your-location-id"
streamlit run app.py
```

Or add them to a `.env` file and load with your preferred tool
(e.g. `python-dotenv`).

---

## What happens when credentials are missing

If **Dutchie Live** mode is selected but one or more required keys are absent,
the app displays a **yellow warning banner** listing the missing keys.
Navigation and the upload-based workflow remain fully functional — switch back
to **📁 Uploads** mode at any time.

---

## Implementing the real API calls

The actual HTTP requests are **not yet implemented** — the integration surface
is ready and waiting for your credentials.

1. Open `dutchie_client.py`.
2. Find the `fetch_dutchie_data` function and locate the comment block
   labelled `# TODO: implement real API call`.
3. Replace the stub with real `requests` (or `httpx`) calls.  An example
   outline is provided in the comments.
4. Ensure the returned DataFrames contain columns that match the aliases
   defined at the top of `app.py` (``INV_NAME_ALIASES``, ``SALES_QTY_ALIASES``,
   etc.), or add new aliases to those lists.

The function signature and return type must remain:

```python
def fetch_dutchie_data(
    config: DutchieConfig,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    location_id: Optional[str] = None,
) -> Tuple[DutchieDataBundle, Optional[str]]:
    ...
```

Where `DutchieDataBundle` is:

```python
Tuple[
    Optional[pd.DataFrame],  # inv_df        → st.session_state.inv_raw_df
    Optional[pd.DataFrame],  # sales_df      → st.session_state.sales_raw_df
    Optional[pd.DataFrame],  # extra_df      → st.session_state.extra_sales_df
    Optional[pd.DataFrame],  # delivery_df   → st.session_state.delivery_raw_df
    Optional[pd.DataFrame],  # daily_sales   → st.session_state.daily_sales_raw_df
]
```

---

## Dutchie API reference (starting points)

- **Dutchie POS API docs:** https://dutchie.com/api
- **Authentication:** Dutchie typically issues a bearer token or uses an
  OAuth2 client-credentials flow.  Confirm the auth method with your Dutchie
  account representative when you receive your credentials.
- **Key endpoints to implement:**
  - `GET /inventory/current` — current on-hand inventory by location
  - `GET /reports/product-sales` — product-level sales within a date range
  - `GET /reports/daily-sales` — day-by-day sales summary
  - `GET /transfers/inbound` or `GET /reports/receiving` — delivery/inbound records

> **Note:** Endpoint paths and response shapes vary by Dutchie product tier
> and contract.  The exact paths above are illustrative; verify against the
> documentation or SDK provided with your credentials.
