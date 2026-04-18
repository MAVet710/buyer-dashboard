# Cannabis Buyer Dashboard 🌿

Streamlit dashboard for cannabis purchasing decisions based on Dutchie/BLAZE inventory and sales data.

---

## How to Use

### Getting Started

1. **Open the app** and log in using your Admin or User credentials in the left sidebar.
2. **Navigate between pages** using the "App Section" radio buttons in the sidebar.
3. **Upload your reports** in the sidebar of the relevant page (see sections below).
4. Your uploaded files are **automatically saved for the rest of the day** — if your session times out and you log back in, your files will be restored without re-uploading.
5. To remove all stored files, click **"🧹 Clear uploads (today & session)"** in the sidebar.

---

### Page 1 — 📊 Inventory Dashboard

**What it does:** Calculates Days-on-Hand (DOH), reorder status, overstock flags, and expiring SKUs across your entire inventory.

**Step-by-step:**
1. In the sidebar, upload your **Inventory File** (CSV or Excel) and your **Product Sales Report** (XLSX).
2. Optionally upload an **Extra Sales Detail** file (revenue-level XLSX) and a **Quarantine List** (CSV or Excel).
3. Adjust **Forecast Settings** (Target DOH, Velocity Adjustment, Days in Sales Period) in the sidebar.
4. Browse the **SKU Inventory Buyer View** tabs — All Inventory, Reorder, Overstock, and Expiring.
5. Use the **Export** button to download the buyer view as an Excel file.

#### Required columns — Inventory File (CSV or Excel)

The dashboard auto-detects column names. Export from Dutchie or BLAZE without editing headers.

| Purpose | Accepted column names (any of these) |
|---|---|
| **Product name** *(required)* | `Product`, `Product Name`, `Item`, `Item Name`, `Name`, `SKU Name` |
| **Category** *(required)* | `Category`, `Subcategory`, `Product Category`, `Master Category`, `Department`, `EComm Category` |
| **Units on hand** *(required)* | `Available`, `On Hand`, `On Hand Units`, `Quantity`, `Qty`, `Quantity On Hand`, `Inventory Available`, `Med Total`, `Med Sellable` |
| **Batch / Lot** *(recommended)* | `Batch`, `Batch Number`, `Lot`, `Lot Number`, `Batch ID`, `Package ID` |
| **Room / Location** *(recommended)* | `Room` — rows where Room = `Vault` are used; all other rooms are excluded |
| **SKU / Product ID** *(optional)* | `SKU`, `SKU ID`, `Product ID`, `Item ID` |
| **Unit cost / price** *(optional)* | `Cost`, `Unit Cost`, `COGS`, `Current Price`, `Wholesale` |
| **Retail price** *(optional)* | `Med Price`, `Retail`, `Retail Price`, `MSRP` |
| **Strain type** *(optional)* | `EComm Strain Type`, `Strain Type`, `Strain`, `Product Type` |
| **Brand / Vendor** *(optional)* | `Brand`, `Brand Name`, `Vendor`, `Vendor Name`, `Manufacturer` |
| **Expiration date** *(optional)* | `Expiration Date`, `Expiry`, `Expiry Date`, `Best By`, `Use By Date`, `Exp Date` |

> **Dutchie tip:** Export from **Inventory → Current Inventory** and include all columns. Make sure to export **all rooms** so the Vault filter can work correctly. When `Med Price` (or any retail price column) is present, `unit_cost` is automatically computed as 50% of the retail price.

#### Required columns — Product Sales Report (XLSX)

| Purpose | Accepted column names (any of these) |
|---|---|
| **Product name** *(required)* | `Product`, `Product Name`, `Item`, `Name`, `SKU` |
| **Category** *(required)* | `Master Category`, `Category`, `Product Category`, `Department` |
| **Units sold** *(required)* | `Quantity Sold`, `Qty Sold`, `Units Sold`, `Items Sold`, `Total Inventory Sold` |
| **Net / Gross sales** *(optional)* | `Net Sales`, `Gross Sales`, `Revenue`, `Total Sales` |
| **Batch / Lot** *(optional)* | `Batch`, `Batch ID`, `Lot`, `Lot Number` |
| **Order date/time** *(optional)* | `Order Date`, `Order Time`, `DateTime` |

> **Dutchie tip:** Export from **Reports → Product Sales Report** (qty-based). Set the date range to match your "Days in Sales Period" setting (default: 60 days). Do **not** edit column headers before uploading.

#### Optional — Extra Sales Detail (XLSX)

Same format as the Product Sales Report. Use this to attach a revenue-detail report when your primary sales file does not include net sales amounts.

#### Optional — Quarantine List (CSV or Excel)

A list of product names to exclude from analysis. Only the product name column is required (same aliases as the Inventory File above).

---

### Page 2 — 📈 Trends

**What it does:** Provides a category mix breakdown, package size mix, top movers by velocity, and fast-mover / low-stock risk scoring.

No additional file uploads are needed — this page uses the same inventory and sales files uploaded on the Inventory Dashboard page.

---

### Page 3 — 🚚 Delivery Impact

**What it does:** Measures how one or more product deliveries correlate with spikes in **Net Sales** and **order count (traffic proxy)** using a 14-day before vs 14-day after comparison window. Shows an interactive line chart with optional overlay lines.

**Step-by-step:**
1. Upload one or more **delivery manifests** (CSV or XLSX recommended; PDF also supported) — the app extracts the received date/time and delivered items from each.
2. Upload your **Sales Report** (CSV or XLSX) — an order-level file with one row per order line item.
3. Choose settings in the sidebar:
   - **Comparison window** (7, 14, 21, or 28 days before/after).
   - **Chart granularity** (daily or hourly).
   - **Fuzzy match threshold** — controls how aggressively manifest item names are matched to sales products (default 0.82).
   - **Overlay toggles** — Total Net Sales, Delivered-items Net Sales, Non-delivered Net Sales, Order Count.
4. Select a specific manifest or **Combined (all manifests)** view.
5. View:
   - **KPI table** — Net Sales before/after, $ and % lift, orders before/after per manifest.
   - **Summary metrics** — aggregated across selected manifests.
   - **Line chart** — time-series with vertical delivery-date marker(s).
   - **Top delivered items by lift** — table sorted by Net Sales lift.
   - **Unmatched items** — manifest items that couldn't be matched to any sales product.
   - **Debug text** — expandable raw text dump per manifest (downloadable).

#### Manifest format — CSV / XLSX (recommended)

Download the receiving/transfer report from Dutchie (or your POS) as CSV or XLSX and upload it directly.  The parser handles:

| Feature | Detail |
|---|---|
| **Preamble rows** | Metadata rows at the top (Manifest #, Received Date, Vendor, …) are skipped automatically |
| **Repeated headers** | Multiple occurrences of `Product, Quantity, …` rows mid-file are ignored |
| **Multi-line product names** | Name fragments spread across continuation rows are stitched together (e.g. `Cresco` + `Rest` + `Flower` + `3.5g- The` + `4th Kind` → `Cresco Rest Flower 3.5g- The 4th Kind`) |
| **Quoted cells with newlines** | Standard CSV quoting (e.g. `"Garden Society Sativa\n- Lemon"`) is handled automatically |
| **Received date/time** | Extracted from the preamble (e.g. `Received Date,03/19/2026 10:30`) |
| **Item name** | Product/Item/Name column (auto-detected) |
| **Delivered qty** | Quantity/Received Qty column — "Received Qty" is preferred over plain "Qty" |
| **Optional columns** | `Package ID`, `Batch`, `License Number`, `Location` are retained when present |

#### Manifest format — PDF (fallback)

The app uses `pdfplumber` (with `PyPDF2` as fallback) to extract:

| What | How it's detected |
|---|---|
| **Received date/time** | First date+time pattern found (e.g. `Received: 03/15/2025 14:32` or ISO format) |
| **Item name** | Text column in manifest table (non-numeric cells) |
| **Delivered qty** | Numeric column in manifest table |

> If the PDF cannot be parsed automatically, switch to CSV/XLSX export from your POS.  If you must use PDF, download the debug text dump and check whether the received date and items are present in the extracted text.

#### Required columns — Sales Report (CSV or XLSX)

| Purpose | Accepted column names (any of these) |
|---|---|
| **Order ID** *(recommended)* | `Order ID`, `Order Number`, `OrderId` |
| **Order timestamp** *(required)* | `Order Time`, `Order Date`, `OrderTime`, `Datetime` |
| **Product name** *(required for item matching)* | `Product Name`, `Product`, `Item`, `Name` |
| **Category** *(optional)* | `Category`, `Master Category`, `Department` |
| **Units sold** *(optional)* | `Total Inventory Sold`, `Units Sold`, `Qty Sold`, `Quantity Sold` |
| **Revenue** *(required — one of)* | `Net Sales`, `NetSales` — preferred; `Gross Sales`, `GrossSales` as fallback |

> **Preamble rows:** If the CSV has metadata rows at the top (e.g. `Export Date:,03/20/2026`), they are automatically skipped. The parser looks for the first row containing both `Order ID` and `Order Time`.

#### Item matching strategy

Manifest item names are matched to sales `Product Name` using:
1. **Exact match** (case-insensitive).
2. **Normalised match** — strips size tokens (`3.5g`, `500mg`, `1oz`, etc.), removes punctuation, collapses whitespace.
3. **Fuzzy match** via `difflib.SequenceMatcher` with the configured threshold.

Unmatched items are listed separately and excluded from delivered-items metrics.

---

### Page 4 — 🐢 Slow Movers

**What it does:** Identifies products with excess Days-on-Hand and assigns action badges and discount tiers.

No additional file uploads are needed — this page uses the same inventory and sales files uploaded on the Inventory Dashboard page.

Use the filter bar to narrow results by category, brand, DOH threshold, and velocity window. Export the full slow-mover analysis to Excel (3 sheets: Slow Movers, Summary, Full Detail).

---

### Page 5 — 🧾 PO Builder

**What it does:** Generates a purchase order PDF pre-populated with flagged reorder items from the Inventory Dashboard.

**Step-by-step:**
1. Visit the **Inventory Dashboard** first so reorder data is loaded.
2. Navigate to **PO Builder** and click **"Add all flagged reorder items"** to pre-populate the PO.
3. Edit line items, enter store and vendor details, and click **"Generate PO PDF"** to download.

---

## Session & Data Persistence

- Uploaded files are stored **in memory for the current calendar day** (per user login).
- If your session times out (typically after ~30 minutes of browser inactivity on Streamlit Cloud), simply **log back in** — your files from today will be restored automatically.
- Files are **not** stored on disk or in any external database. They live in server memory and are cleared at midnight or when the server restarts.
- Click **"🧹 Clear uploads (today & session)"** in the sidebar to manually remove all stored files.

---

## Doobie AI Connection (DoobieLogic Source of Truth)

Buyer Dashboard login controls dashboard access.  
DoobieLogic license validation controls **AI feature access only**.

### Required environment variables

- `DOOBIE_BASE_URL` — base URL of the DoobieLogic service (example: `https://api.doobielogic.com`).
- `DOOBIE_API_KEY` *(optional, if required by your DoobieLogic deployment)* — bearer token used when calling DoobieLogic.

### Optional license environment variables

- `BUYER_DASHBOARD_LICENSE_FILE` — local cache file path (default: `.buyer_dashboard_license.json`).
- `DOOBIE_LICENSE_RECHECK_HOURS` — how old a cached validation can be before re-check (default: `24`).
- `DOOBIE_LICENSE_GRACE_HOURS` — temporary offline grace window if DoobieLogic is unavailable (default: `48`).
- `DOOBIE_LICENSE_TIMEOUT_SECONDS` — network timeout for validation requests (default: `8`).

### Validation flow

1. Users log in with the existing auth system exactly as before.
2. After login, the app loads normally regardless of license state.
3. After login, the sidebar includes a **Doobie AI** panel with connect/disconnect controls.
4. Clicking **Connect** validates key entry via `POST /api/v1/license/validate` on DoobieLogic.
5. Valid responses enable AI features; invalid responses keep AI disabled while the rest of the app stays usable.

### Local cache behavior (not authority)

- Buyer Dashboard stores a lightweight local cache containing key/license metadata and feature flags.
- Cache is convenience only; DoobieLogic remains the authority.
- Cached sessions are periodically revalidated (default every 24 hours).

### Grace-period behavior

- If DoobieLogic is temporarily unavailable:
  - Dashboard remains usable.
  - AI access can continue briefly only when a recent previously-valid cache exists and is within grace.
  - Without recent cache, AI remains disconnected until the service is reachable.
- UI indicates this with an unavailable status/warning in the Doobie AI panel.

### Feature gating behavior

Feature flags returned by DoobieLogic can gate modules like:

- `buyer_module`
- `extraction_module`
- `ai_support`
- `admin_exports`

Unavailable AI features show a connect message without crashing the app.

---

## Slow Movers & Trends — Glossary

### Days-on-Hand (DOH)
> **DOH = Units on Hand ÷ Daily Run Rate**

DOH tells you how many days the current stock will last at the current rate of sale. A product with 100 units and a daily run rate of 2 units has **50 days of supply**. Products above the configurable threshold (default: **60 days**) are flagged as slow movers.

### Weeks of Supply
> **Weeks of Supply = DOH ÷ 7**

A weeks-based view of the same metric — useful when your buying cycle is measured in weeks. A product at 14 weeks of supply has ~98 days of stock on hand.

### Avg Weekly Sales
> **Avg Weekly Sales = Total Units Sold in Window ÷ (Window Days ÷ 7)**

Computed over the selected **velocity window** (28, 56, or 84 days). Use a shorter window for recent demand signals; use a longer window to smooth out promotional spikes or seasonal dips.

### Velocity Window
The number of calendar days used when calculating average sales rate. Options:
- **28 days** — captures the most recent demand, sensitive to short-term changes.
- **56 days (default)** — balances recency and stability; recommended for most buyers.
- **84 days** — smooths out spikes; better for seasonal or slow-moving categories.

### Slow Mover Score
A 0–100 composite score where **100 = completely stuck** (no sales in window). It is derived from how far the product's DOH exceeds the 180-day ceiling. Use the score to rank products when you have many items near the threshold.

### Action Badge
Each product receives an action badge based on DOH and weekly sales:

| Badge | Meaning |
|---|---|
| ✅ Healthy | DOH ≤ 60 days — no action needed |
| 🟢 Monitor | DOH 61–90 days |
| 🟡 Watch | DOH 91–120 days — consider a small promo |
| 🟠 Markdown | DOH 121–180 days — discount recommended |
| 🔴 Promo / Stop Reorder | DOH > 180 days — urgent action |
| 🔴 Investigate | No sales data or zero velocity — check data |
| ⬛ No Stock | Zero units on hand |

## Tech Stack
- Streamlit
- pandas
- plotly

---

## Inventory Dashboard — Buyer View

The **📋 SKU Inventory Buyer View** section inside the Inventory Dashboard provides a buyer-focused, SKU-level analysis of your on-hand stock.

### How It Works
The buyer view reads the same uploaded inventory and sales files and computes metrics at the individual SKU level (one row per product name).

### Filter Bar
- **Search** — filter by product name, SKU, or brand/vendor (case-insensitive).
- **Velocity window** — same 28 / 56 / 84-day options as Slow Movers (see glossary above). Controls avg weekly sales and DOH calculations.
- **Show top N** — limit results to 25 / 50 / 100 or All SKUs after sorting.
- **Sort by** — buyer-focused options: `$ on hand ↓`, `DOH (high→low) ↓`, `DOH (low→high) ↑`, `Expiring soonest`, `Avg weekly sales ↓`.
- **Category / Subcategory** — dropdown populated from inventory data.
- **Vendor / Brand** — dropdown populated from inventory data (requires a brand/vendor column).
- **Expiration window** — `Any` / `<30 days` / `<60 days` / `<90 days` — filters by days until the earliest expiration date per SKU.
- **On-hand > 0** — toggle to hide SKUs with zero units (default: ON).
- **DOH min / max** — fine-tune the days-of-hand range shown.

### Tabs
| Tab | Default Filter | Default Sort |
|---|---|---|
| 📦 All Inventory | Active filter bar settings | Selected "Sort by" |
| 🔴 Reorder | DOH ≤ 21 days | DOH ascending (most urgent first) |
| 🟠 Overstock | DOH ≥ 90 days | $ on hand descending |
| ⚠️ Expiring | Earliest expiry < 60 days | Days to expire ascending |

Thresholds (21 / 90 / 60) are defined as constants `INVENTORY_REORDER_DOH_THRESHOLD`, `INVENTORY_OVERSTOCK_DOH_THRESHOLD`, and `INVENTORY_EXPIRING_SOON_DAYS` at the top of `app.py` and can be adjusted there.

### KPI Strip
Above each tab's table, five tiles reflect the **currently filtered data**:
- **📦 SKUs in stock** — count of SKUs with on-hand > 0.
- **💰 Total $ on hand** — sum of `on-hand units × current price` (requires cost column).
- **🔴 Reorder SKUs** — count of SKUs with Reorder status.
- **🟠 Overstock SKUs** — count of SKUs with Overstock status.
- **⚠️ Expiring <60d** — count of expiring SKUs and dollars tied up.

### Status Badge Criteria
| Badge | Criteria |
|---|---|
| ⬛ No Stock | On-hand = 0 |
| ⚠️ Expiring | Earliest expiry < 60 days (checked first for in-stock SKUs) |
| 🔴 Reorder | DOH > 0 and DOH ≤ 21 days |
| 🟠 Overstock | DOH ≥ 90 days (includes SKUs with no sales data) |
| ✅ Healthy | All other in-stock SKUs |

### Optional Inventory Columns
The buyer view works without these columns but unlocks additional features when present:

| Column | Purpose |
|---|---|
| `current price` / `unit cost` / `cost` / `wholesale` | Enables $ on hand, $ tied up expiring KPIs |
| `brand` / `vendor` | Enables Vendor/Brand filter dropdown |
| `expiration date` / `expiry` / `best by` | Enables Expiring tab and Days-to-Expire column |

Missing columns are reported as an info message above the filter bar.
