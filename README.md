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
