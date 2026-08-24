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
      <article className="inventory-panel buyer-chart-panel buyer-chart-elevated">
        <div className="section-heading"><div><div className="eyebrow">Buyer performance</div><h2>Sales Trend</h2><p>Daily sales activity from the active Product Sales source.</p></div></div>
        {data.sales_trend.length ? <LineChart rows={data.sales_trend}/> : <div className="empty">No dated sales rows are available in the active Product Sales source.</div>}
      </article>
      <article className="inventory-panel buyer-chart-panel buyer-chart-elevated">
        <div className="section-heading"><div><div className="eyebrow">Category mix</div><h2>Revenue by Category</h2><p>Revenue concentration and category contribution from the same sales source.</p></div></div>
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
  const width = 760; const height = 260; const left = 58; const right = 18; const top = 18; const bottom = 30;
  const revenues = rows.map(row => number(row.revenue));
  const units = rows.map(row => number(row.units));
  const useRevenue = revenues.some(value => value > 0);
  const values = useRevenue ? revenues : units;
  const max = Math.max(...values, 1);
  const chartWidth = width - left - right; const chartHeight = height - top - bottom;
  const pointRows = rows.map((row, index) => {
    const x = rows.length <= 1 ? left + chartWidth / 2 : left + index * (chartWidth / (rows.length - 1));
    const value = values[index] ?? 0;
    const y = top + chartHeight - (value / max) * chartHeight;
    return { row, x, y, value };
  });
  const points = pointRows.map(point => `${point.x},${point.y}`).join(" ");
  const area = pointRows.length ? `M ${pointRows[0].x} ${top + chartHeight} L ${pointRows.map(point => `${point.x} ${point.y}`).join(" L ")} L ${pointRows[pointRows.length - 1].x} ${top + chartHeight} Z` : "";
  const totalRevenue = revenues.reduce((sum, value) => sum + value, 0);
  const totalUnits = units.reduce((sum, value) => sum + value, 0);
  const recent = values.slice(-7); const prior = values.slice(-14, -7);
  const recentAvg = average(recent); const priorAvg = average(prior);
  const change = prior.length && priorAvg ? ((recentAvg - priorAvg) / priorAvg) * 100 : null;
  const grid = [0, .25, .5, .75, 1];
  const dotEvery = Math.max(1, Math.ceil(rows.length / 18));

  return <div className="buyer-chart-wrap">
    <div className="buyer-chart-kpis">
      <div><span>{useRevenue ? "Sales in view" : "Units in view"}</span><strong>{useRevenue ? money(totalRevenue) : totalUnits.toLocaleString()}</strong></div>
      <div><span>Daily average</span><strong>{useRevenue ? money(recentAvg || average(values)) : Math.round(recentAvg || average(values)).toLocaleString()}</strong></div>
      <div><span>7-day movement</span><strong className={change == null ? "" : change >= 0 ? "positive" : "negative"}>{change == null ? "Building baseline" : `${change >= 0 ? "+" : ""}${change.toFixed(1)}%`}</strong></div>
    </div>
    <div className="buyer-chart-stage">
      <svg className="buyer-line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Sales Trend">
        <defs><linearGradient id="buyer-sales-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--dl-copper)" stopOpacity=".34"/><stop offset="78%" stopColor="var(--dl-copper)" stopOpacity=".05"/><stop offset="100%" stopColor="var(--dl-copper)" stopOpacity="0"/></linearGradient></defs>
        {grid.map(ratio => { const y = top + chartHeight - ratio * chartHeight; const value = max * ratio; return <g className="buyer-chart-grid" key={ratio}><line x1={left} x2={width-right} y1={y} y2={y}/><text x={left-8} y={y+4} textAnchor="end">{useRevenue ? compactMoney(value) : compactNumber(value)}</text></g>; })}
        {area ? <path className="buyer-area-fill" d={area}/> : null}
        <polyline className="buyer-trend-line" points={points}/>
        {pointRows.map(({ row, x, y }, index) => index % dotEvery === 0 || index === pointRows.length - 1 ? <circle key={`${text(row.date)}-${index}`} cx={x} cy={y} r="4"><title>{`${text(row.date)}: ${money(number(row.revenue))} · ${number(row.units).toLocaleString()} units`}</title></circle> : null)}
      </svg>
    </div>
    <div className="buyer-chart-axis"><span>{shortDate(rows[0]?.date)}</span><span>{rows.length.toLocaleString()} daily points</span><span>{shortDate(rows[rows.length - 1]?.date)}</span></div>
  </div>;
}

function BarChart({ rows }: { rows: Row[] }) {
  const visible = rows.slice(0, 8);
  const values = visible.map(row => number(row.revenue) || number(row.units));
  const max = Math.max(...values, 1);
  const total = rows.reduce((sum, row) => sum + (number(row.revenue) || number(row.units)), 0);
  return <div className="buyer-category-bars">{visible.map((row, index) => {
    const value = number(row.revenue) || number(row.units); const share = total ? value / total * 100 : 0;
    return <div className="buyer-category-bar" key={`${text(row.category)}-${index}`}>
      <div className="buyer-category-bar-label"><span className="buyer-category-rank">{String(index + 1).padStart(2, "0")}</span><strong>{titleCase(text(row.category) || "Uncategorized")}</strong><span>{number(row.revenue) ? money(number(row.revenue)) : `${number(row.units).toLocaleString()} units`}</span></div>
      <div className="buyer-bar-track"><i style={{ width: `${Math.max(2, value / max * 100)}%` }}/></div>
      <div className="buyer-category-share"><span>{share.toFixed(1)}% of mix</span><span>{number(row.units).toLocaleString()} units</span></div>
    </div>;
  })}</div>;
}

function DataTable({ rows, columns }: { rows: Row[]; columns: string[] }) {
  const visible = columns.filter(column => rows.some(row => Object.prototype.hasOwnProperty.call(row, column)));
  if (!rows.length) return <div className="empty">No slow-moving inventory in the current buyer source.</div>;
  return <div className="table-wrap"><table><thead><tr>{visible.map(column => <th key={column}>{header(column)}</th>)}</tr></thead><tbody>{rows.map((row,index) => <tr key={index}>{visible.map(column => <td key={column}>{render(row[column], column)}</td>)}</tr>)}</tbody></table></div>;
}

function Metric({ label, value }: { label: string; value: string | number }) { return <article className="metric"><span>{label}</span><strong>{typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : value}</strong></article>; }
function text(value: unknown) { return value == null ? "" : String(value); }
function number(value: unknown) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0; }
function average(values: number[]) { return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0; }
function money(value: number) { return Number(value || 0).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }); }
function compactMoney(value: number) { return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0)); }
function compactNumber(value: number) { return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0)); }
function shortDate(value: unknown) { const parsed = new Date(text(value)); return Number.isNaN(parsed.valueOf()) ? text(value) : parsed.toLocaleDateString("en-US", { month: "short", day: "numeric" }); }
function titleCase(value: string) { return value.replace(/\b\w/g, char => char.toUpperCase()); }
function header(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase()); }
function render(value: unknown, column: string) { if (value == null || value === "") return "—"; if (typeof value === "number") { if (column.includes("dollar") || column.includes("revenue")) return money(value); return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 }); } return String(value); }
