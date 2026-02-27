# Cannabis Buyer Dashboard 🌿

Streamlit dashboard for cannabis purchasing decisions based on Dutchie inventory and sales data.

## How to Use
1. Upload your latest **Inventory CSV** from Dutchie.
2. Upload your **Sales XLSX** from the last 30 days.
3. Explore reorder alerts, sales trends, and download the Buyer View.

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
- **💰 Total $ on hand** — sum of `on-hand units × unit cost` (requires cost column).
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
| `unit cost` / `cost` / `wholesale` | Enables $ on hand, $ tied up expiring KPIs |
| `brand` / `vendor` | Enables Vendor/Brand filter dropdown |
| `expiration date` / `expiry` / `best by` | Enables Expiring tab and Days-to-Expire column |

Missing columns are reported as an info message above the filter bar.
