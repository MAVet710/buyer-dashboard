import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type TrendPoint = { date: string; units: number; revenue: number };
type CategoryPoint = { category: string; units: number; revenue: number };
type SlowMover = Record<string, unknown>;
type LegacyOverview = {
  sales_trend: TrendPoint[];
  revenue_by_category: CategoryPoint[];
  top_slow_movers: SlowMover[];
  inventory_health: { score: number; reorder_skus: number; at_risk_skus: number; slow_movers: number; overstock_skus: number };
  inventory_condition: {
    reorder_count: number;
    overstock_count: number;
    expiring_count: number;
    no_stock_count: number;
    overstock_cost_exposure: number;
    expiring_cost_exposure: number;
    on_hand_cost: number;
    units_on_hand: number;
    units_sold: number;
  };
};

const SLOW_COLUMNS = ["product_name", "category", "brand_vendor", "onhandunits", "avg_weekly_sales", "days_of_supply", "dollars_on_hand", "expiration_date", "status"];

export function BuyerLegacyOverview() {
  const overview = useQuery({
    queryKey: ["buyer-legacy-overview"],
    queryFn: ({ signal }) => apiGet<LegacyOverview>("/api/v1/buyer-parity/legacy-overview?target_doh=21&velocity_adjustment=0.5&sales_days=60&sku_window=56&top_n=10", signal),
  });

  if (overview.isLoading) return <section className="inventory-panel"><div className="state">Building the original Buyer Dash overview…</div></section>;
  if (overview.isError) return <section className="inventory-panel"><div className="state error">{overview.error.message}</div></section>;
  if (!overview.data) return null;
  const data = overview.data;

  return <section className="buyer-legacy-overview" aria-label="Buyer purchasing overview">
    <div className="buyer-overview-grid">
      <article className="inventory-panel buyer-chart-panel">
        <div className="section-heading"><div><div className="eyebrow">Buyer performance</div><h2>Sales Trend</h2></div></div>
        {data.sales_trend.length ? <LineChart rows={data.sales_trend}/> : <div className="empty">The active sales source does not contain a usable date column for a time-series trend.</div>}
      </article>
      <article className="inventory-panel buyer-chart-panel">
        <div className="section-heading"><div><div className="eyebrow">Category mix</div><h2>Revenue by Category</h2></div></div>
        {data.revenue_by_category.length ? <BarChart rows={data.revenue_by_category}/> : <div className="empty">No category sales are available in the current buyer source.</div>}
      </article>
    </div>

    <div className="buyer-overview-grid buyer-health-grid">
      <article className="inventory-panel buyer-health-card">
        <div><div className="eyebrow">Inventory Health</div><h2>{data.inventory_health.score}/100</h2></div>
        <HealthGauge score={data.inventory_health.score}/>
        <div className="buyer-health-evidence">
          <span><strong>{data.inventory_health.reorder_skus}</strong> replenishment</span>
          <span><strong>{data.inventory_health.at_risk_skus}</strong> critical cover</span>
          <span><strong>{data.inventory_health.slow_movers}</strong> no movement</span>
          <span><strong>{data.inventory_health.overstock_skus}</strong> excess inventory</span>
        </div>
      </article>
      <article className="inventory-panel">
        <div className="section-heading"><div><div className="eyebrow">Inventory Summary</div><h2>Buyer decision queue</h2></div></div>
        <section className="metrics buyer-condition-metrics">
          <Metric label="Units On Hand" value={data.inventory_condition.units_on_hand}/>
          <Metric label="Units Sold" value={data.inventory_condition.units_sold}/>
          <Metric label="Reorder / Low Cover" value={data.inventory_condition.reorder_count}/>
          <Metric label="No Stock" value={data.inventory_condition.no_stock_count}/>
          <Metric label="Overstock SKUs" value={data.inventory_condition.overstock_count}/>
          <Metric label="Expiring <60d" value={`${data.inventory_condition.expiring_count} (${money(data.inventory_condition.expiring_cost_exposure)})`}/>
          <Metric label="Overstock $" value={money(data.inventory_condition.overstock_cost_exposure)}/>
          <Metric label="$ On Hand" value={money(data.inventory_condition.on_hand_cost)}/>
        </section>
      </article>
    </div>

    <article className="inventory-panel">
      <div className="section-heading"><div><div className="eyebrow">Embedded buyer exception review</div><h2>Top Slow Movers</h2></div></div>
      <DataTable rows={data.top_slow_movers} columns={SLOW_COLUMNS}/>
    </article>
  </section>;
}

function HealthGauge({ score }: { score: number }) {
  const bounded = Math.max(0, Math.min(100, score));
  return <div className="buyer-health-gauge" style={{ background: `conic-gradient(var(--dl-copper) 0deg ${bounded * 3.6}deg, rgba(255,255,255,.08) ${bounded * 3.6}deg 360deg)` }} aria-label={`Inventory health ${bounded} out of 100`}><div><strong>{bounded}</strong><span>Health</span></div></div>;
}

function LineChart({ rows }: { rows: TrendPoint[] }) {
  const width = 720; const height = 230; const pad = 24;
  const values = rows.map(row => Number(row.revenue || row.units || 0));
  const max = Math.max(...values, 1); const min = Math.min(...values, 0); const span = Math.max(max - min, 1);
  const pointRows = rows.map((row, index) => {
    const x = rows.length <= 1 ? width / 2 : pad + index * ((width - pad * 2) / (rows.length - 1));
    const value = Number(row.revenue || row.units || 0); const y = height - pad - ((value - min) / span) * (height - pad * 2);
    return { row, x, y };
  });
  const points = pointRows.map(point => `${point.x},${point.y}`).join(" ");
  return <div className="buyer-chart-wrap"><svg className="buyer-line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Sales Trend"><polyline points={points}/>{pointRows.map(({ row, x, y }, index) => <circle key={`${row.date}-${index}`} cx={x} cy={y} r="4"><title>{row.date}: {money(row.revenue)} · {row.units.toLocaleString()} units</title></circle>)}</svg><div className="buyer-chart-axis"><span>{rows[0]?.date}</span><span>{rows[rows.length - 1]?.date}</span></div></div>;
}

function BarChart({ rows }: { rows: CategoryPoint[] }) {
  const visible = rows.slice(0, 8); const max = Math.max(...visible.map(row => Number(row.revenue || row.units || 0)), 1);
  return <div className="buyer-category-bars">{visible.map(row => { const value = Number(row.revenue || row.units || 0); return <div className="buyer-category-bar" key={row.category}><div><strong>{row.category}</strong><span>{row.revenue ? money(row.revenue) : `${row.units.toLocaleString()} units`}</span></div><div className="buyer-bar-track"><i style={{ width: `${Math.max(2, value / max * 100)}%` }}/></div></div>; })}</div>;
}

function DataTable({ rows, columns }: { rows: SlowMover[]; columns: string[] }) {
  const visible = columns.filter(column => rows.some(row => Object.prototype.hasOwnProperty.call(row, column)));
  if (!rows.length) return <div className="empty">No slow-moving inventory in the current buyer source.</div>;
  return <div className="table-wrap"><table><thead><tr>{visible.map(column => <th key={column}>{header(column)}</th>)}</tr></thead><tbody>{rows.map((row,index) => <tr key={index}>{visible.map(column => <td key={column}>{render(row[column])}</td>)}</tr>)}</tbody></table></div>;
}

function Metric({ label, value }: { label: string; value: string | number }) { return <article className="metric"><span>{label}</span><strong>{typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : value}</strong></article>; }
function money(value: number) { return Number(value || 0).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }); }
function header(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase()); }
function render(value: unknown) { if (value == null || value === "") return "—"; if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 }); return String(value); }
