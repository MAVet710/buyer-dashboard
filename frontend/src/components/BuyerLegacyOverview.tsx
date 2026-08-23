import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import type { CSSProperties } from "react";

type Row = Record<string, unknown>;
type LegacyOverview = {
  sales_trend: Row[];
  revenue_by_category: Row[];
  top_slow_movers: Row[];
  inventory_health: {
    score: number;
    reorder_skus: number;
    at_risk_skus: number;
    slow_movers: number;
    overstock_skus: number;
  };
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

type Props = {
  targetDoh: number;
  velocityAdjustment: number;
  salesDays: number;
  skuWindow: number;
  topN: number;
};

const SLOW_COLUMNS = ["product_name", "category", "brand_vendor", "onhandunits", "avg_weekly_sales", "days_of_supply", "dollars_on_hand", "expiration_date", "status"];

export function BuyerLegacyOverview({ targetDoh, velocityAdjustment, salesDays, skuWindow, topN }: Props) {
  const params = new URLSearchParams({
    target_doh: String(targetDoh),
    velocity_adjustment: String(velocityAdjustment),
    sales_days: String(salesDays),
    sku_window: String(skuWindow),
    top_n: String(topN > 0 ? Math.min(Math.max(topN, 1), 50) : 10),
  });
  const overview = useQuery({
    queryKey: ["buyer-legacy-overview", targetDoh, velocityAdjustment, salesDays, skuWindow, topN],
    queryFn: ({ signal }) => apiGet<LegacyOverview>(`/api/v1/buyer-parity/legacy-overview?${params}`, signal),
  });

  if (overview.isLoading) return <section className="inventory-panel"><div className="state">Building the purchasing command-center evidence…</div></section>;
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
      <div className="section-heading"><div><div className="eyebrow">Embedded buyer exception review</div><h2>Top Slow Movers</h2><p>Kept inside the purchasing workflow so the buyer does not have to leave the command center to see aging inventory risk.</p></div></div>
      <DataTable rows={data.top_slow_movers} columns={SLOW_COLUMNS}/>
    </article>
  </section>;
}

function HealthGauge({ score }: { score: number }) {
  const bounded = Math.max(0, Math.min(100, score));
  const style = { "--buyer-health-angle": `${bounded * 3.6}deg` } as CSSProperties;
  return <div className="buyer-health-gauge" style={style} aria-label={`Inventory health ${bounded} out of 100`}><div><strong>{bounded}</strong><span>Health</span></div></div>;
}

function LineChart({ rows }: { rows: Row[] }) {
  const width = 720; const height = 230; const pad = 24;
  const values = rows.map(row => number(row.revenue) || number(row.units));
  const max = Math.max(...values, 1); const min = Math.min(...values, 0); const span = Math.max(max - min, 1);
  const pointRows = rows.map((row, index) => {
    const x = rows.length <= 1 ? width / 2 : pad + index * ((width - pad * 2) / (rows.length - 1));
    const value = number(row.revenue) || number(row.units); const y = height - pad - ((value - min) / span) * (height - pad * 2);
    return { row, x, y };
  });
  const points = pointRows.map(point => `${point.x},${point.y}`).join(" ");
  return <div className="buyer-chart-wrap"><svg className="buyer-line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Sales Trend"><polyline points={points}/>{pointRows.map(({ row, x, y }, index) => <circle key={`${text(row.date)}-${index}`} cx={x} cy={y} r="4"><title>{`${text(row.date)}: ${money(number(row.revenue))} · ${number(row.units).toLocaleString()} units`}</title></circle>)}</svg><div className="buyer-chart-axis"><span>{text(rows[0]?.date)}</span><span>{text(rows[rows.length - 1]?.date)}</span></div></div>;
}

function BarChart({ rows }: { rows: Row[] }) {
  const visible = rows.slice(0, 8); const max = Math.max(...visible.map(row => number(row.revenue) || number(row.units)), 1);
  return <div className="buyer-category-bars">{visible.map((row, index) => { const value = number(row.revenue) || number(row.units); return <div className="buyer-category-bar" key={`${text(row.category)}-${index}`}><div><strong>{text(row.category) || "Uncategorized"}</strong><span>{number(row.revenue) ? money(number(row.revenue)) : `${number(row.units).toLocaleString()} units`}</span></div><div className="buyer-bar-track"><i style={{ width: `${Math.max(2, value / max * 100)}%` }}/></div></div>; })}</div>;
}

function DataTable({ rows, columns }: { rows: Row[]; columns: string[] }) {
  const visible = columns.filter(column => rows.some(row => Object.prototype.hasOwnProperty.call(row, column)));
  if (!rows.length) return <div className="empty">No slow-moving inventory in the current buyer source.</div>;
  return <div className="table-wrap"><table><thead><tr>{visible.map(column => <th key={column}>{header(column)}</th>)}</tr></thead><tbody>{rows.map((row,index) => <tr key={index}>{visible.map(column => <td key={column}>{render(row[column], column)}</td>)}</tr>)}</tbody></table></div>;
}

function Metric({ label, value }: { label: string; value: string | number }) { return <article className="metric"><span>{label}</span><strong>{typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : value}</strong></article>; }
function text(value: unknown) { return value == null ? "" : String(value); }
function number(value: unknown) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0; }
function money(value: number) { return Number(value || 0).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }); }
function header(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase()); }
function render(value: unknown, column: string) { if (value == null || value === "") return "—"; if (typeof value === "number") { if (column.includes("dollar") || column.includes("revenue")) return money(value); return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 }); } return String(value); }
