import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { apiDownload, apiGet, downloadBlob } from "../lib/api";

type Row = Record<string, unknown>;
type Dashboard = {
  controls: { target_doh: number; velocity_adjustment: number; sales_days: number; sku_window: number };
  summary: { units_sold: number; reorder_asap: number; tracked_products: number; categories: number };
  sources: { inventory: { filename: string; rows: number }; sales: { filename: string; rows: number } };
  category_dos: Row[];
  forecast: Row[];
  product_rows: Row[];
  product_rows_total: number;
  sku_views: { all: Row[]; reorder: Row[]; overstock: Row[]; expiring: Row[] };
};
type Intelligence = {
  sales_days: number;
  summary: { tracked_skus: number; total_units_sold: number; at_risk_skus: number; overstock_watch: number };
  purchase_priorities: Row[];
  sku_risk: Row[];
  overstock_watch: Row[];
  category_risk: Row[];
};

type Tab = "category" | "forecast" | "products" | "sku" | "doobie";
type SkuTab = "all" | "reorder" | "overstock" | "expiring";

export function BuyerOperationsPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const [targetDoh, setTargetDoh] = useState(21);
  const [velocity, setVelocity] = useState(0.5);
  const [salesDays, setSalesDays] = useState(60);
  const [skuWindow, setSkuWindow] = useState(56);
  const [tab, setTab] = useState<Tab>("category");
  const [skuTab, setSkuTab] = useState<SkuTab>("all");
  const [onlyReorder, setOnlyReorder] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const query = new URLSearchParams({ target_doh: String(targetDoh), velocity_adjustment: String(velocity), sales_days: String(salesDays), sku_window: String(skuWindow) });
  const dashboard = useQuery({ queryKey: ["buyer-parity", targetDoh, velocity, salesDays, skuWindow], queryFn: ({ signal }) => apiGet<Dashboard>(`/api/v1/buyer-parity/dashboard?${query}`, signal) });
  const intelligence = useQuery({ queryKey: ["buyer-intelligence-parity", targetDoh, velocity, salesDays], queryFn: ({ signal }) => apiGet<Intelligence>(`/api/v1/buyer-parity/intelligence?target_doh=${targetDoh}&velocity_adjustment=${velocity}&sales_days=${salesDays}`, signal), enabled: tab === "doobie" });
  const categoryOptions = useMemo(() => Array.from(new Set((dashboard.data?.forecast ?? []).map(row => text(row.subcategory)).filter(Boolean))).sort(), [dashboard.data]);
  const visibleCategories = categories.length ? categories : categoryOptions;
  const forecast = useMemo(() => (dashboard.data?.forecast ?? []).filter(row => visibleCategories.includes(text(row.subcategory)) && (!onlyReorder || text(row.reorderpriority) === "1 – Reorder ASAP")), [dashboard.data, visibleCategories, onlyReorder]);

  const download = async (kind: "forecast" | "product" | "sku") => {
    const params = new URLSearchParams(query); params.set("kind", kind);
    const names = { forecast: "forecast_table.xlsx", product: "product_level_forecast.xlsx", sku: "sku_inventory_buyer_view.xlsx" };
    downloadBlob(await apiDownload(`/api/v1/buyer-parity/export?${params}`), names[kind]);
  };

  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">Retail Ops · original Buyer Dash workflow</div><h1>Buyer Operations</h1><p>Category DOS, forecast, product rows, SKU buyer view, exports and the Doobie buyer brief use the same rules as the Streamlit workspace.</p></div><div className="source-pills">{dashboard.data ? <><span className="access-badge">Inventory · {dashboard.data.sources.inventory.filename}</span><span className="access-badge">Sales · {dashboard.data.sources.sales.filename}</span></> : null}</div></div>
    <section className="inventory-panel parity-controls"><label>Target Days on Hand<input type="number" min={1} max={120} value={targetDoh} onChange={event => setTargetDoh(Number(event.target.value))}/></label><label>Velocity Adjustment<input type="number" min={0.01} max={5} step={0.01} value={velocity} onChange={event => setVelocity(Number(event.target.value))}/></label><label>Days in Sales Period<input type="range" min={7} max={120} value={salesDays} onChange={event => setSalesDays(Number(event.target.value))}/><span>{salesDays} days</span></label></section>
    {dashboard.isError ? <div className="state error">{dashboard.error.message}</div> : null}
    {dashboard.isLoading ? <div className="state">Building the Buyer Dash forecast from the active durable sources…</div> : null}
    {dashboard.data ? <>
      <section className="metrics"><Metric label="Units Sold" value={dashboard.data.summary.units_sold.toLocaleString()}/><Metric label="Reorder ASAP" value={dashboard.data.summary.reorder_asap}/><Metric label="Tracked Products" value={dashboard.data.summary.tracked_products}/><Metric label="Categories" value={dashboard.data.summary.categories}/></section>
      <div className="view-tabs parity-tabs"><button className={tab === "category" ? "active" : ""} onClick={() => setTab("category")}>Category DOS</button><button className={tab === "forecast" ? "active" : ""} onClick={() => setTab("forecast")}>Forecast Table</button><button className={tab === "products" ? "active" : ""} onClick={() => setTab("products")}>Product Rows</button><button className={tab === "sku" ? "active" : ""} onClick={() => setTab("sku")}>SKU Buyer View</button><button className={tab === "doobie" ? "active" : ""} onClick={() => setTab("doobie")}>Doobie Buyer Brief</button></div>
      {tab === "category" ? <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">At a glance</div><h2>Category DOS</h2></div></div><DataTable rows={dashboard.data.category_dos} columns={["subcategory","category_dos","reorder_lines","product_count","top_products"]}/></section> : null}
      {tab === "forecast" ? <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Forecast</div><h2>Forecast Table</h2></div><button className="secondary" onClick={() => download("forecast")}>Export Forecast Table (Excel)</button></div><div className="filters parity-filter-row"><label>Visible Categories<select multiple value={visibleCategories} onChange={event => setCategories(Array.from(event.target.selectedOptions).map(option => option.value))}>{categoryOptions.map(category => <option key={category}>{category}</option>)}</select></label><label className="toggle"><input type="checkbox" checked={onlyReorder} onChange={event => setOnlyReorder(event.target.checked)}/> Only Reorder ASAP</label></div><DataTable rows={forecast} columns={["top_products","mastercategory","subcategory","strain_type","packagesize","onhandunits","unitssold","avgunitsperday","daysonhand","reorderqty","reorderpriority","product_count"]}/></section> : null}
      {tab === "products" ? <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Product-level</div><h2>Product Rows</h2><p>{dashboard.data.product_rows_total > dashboard.data.product_rows.length ? `Showing top ${dashboard.data.product_rows.length.toLocaleString()} of ${dashboard.data.product_rows_total.toLocaleString()} rows by units sold.` : `${dashboard.data.product_rows_total.toLocaleString()} rows`}</p></div><button className="secondary" onClick={() => download("product")}>Download Product-Level Table (Excel)</button></div><DataTable rows={dashboard.data.product_rows} columns={["product_name","subcategory","strain_type","packagesize","brand_vendor","sku","onhandunits","unitssold","avgunitsperday","daysonhand","expiration_date"]}/></section> : null}
      {tab === "sku" ? <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">SKU-wide inventory</div><h2>SKU Buyer View</h2></div><div className="heading-actions"><label className="compact-field">Velocity window<select value={skuWindow} onChange={event => setSkuWindow(Number(event.target.value))}><option value={28}>28 days</option><option value={56}>56 days</option><option value={84}>84 days</option></select></label><button className="secondary" onClick={() => download("sku")}>Export SKU View</button></div></div><div className="view-tabs"><button className={skuTab === "all" ? "active" : ""} onClick={() => setSkuTab("all")}>All Inventory</button><button className={skuTab === "reorder" ? "active" : ""} onClick={() => setSkuTab("reorder")}>Reorder</button><button className={skuTab === "overstock" ? "active" : ""} onClick={() => setSkuTab("overstock")}>Overstock</button><button className={skuTab === "expiring" ? "active" : ""} onClick={() => setSkuTab("expiring")}>Expiring</button></div><DataTable rows={dashboard.data.sku_views[skuTab]} columns={["sku","product_name","brand_vendor","subcategory","onhandunits","avgunitsperday","days_of_supply","weeks_of_supply","dollars_on_hand","retail_dollars_on_hand","expiration_date","days_to_expire","status"]}/></section> : null}
      {tab === "doobie" ? <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Doobie replaces the legacy buyer AI</div><h2>Buyer Intelligence evidence</h2><p>The deterministic store evidence is preserved first; Doobie is the action/interpretation layer.</p></div><button className="primary" onClick={() => onNavigate("Doobie")}>Open Doobie</button></div>{intelligence.data ? <><section className="metrics"><Metric label="Tracked SKUs" value={intelligence.data.summary.tracked_skus}/><Metric label="Units Sold" value={intelligence.data.summary.total_units_sold.toLocaleString()}/><Metric label="Reorder Risk" value={intelligence.data.summary.at_risk_skus}/><Metric label="Overstock Watch" value={intelligence.data.summary.overstock_watch}/></section><h3>Buy first</h3><DataTable rows={intelligence.data.purchase_priorities} columns={["Need","Recommended units","Current on hand","Days of cover","Units sold","SKUs","Reason"]}/><h3>SKU stockout risk</h3><DataTable rows={intelligence.data.sku_risk} columns={["product_name","category","on_hand_units","units_sold","days_of_cover"]}/><h3>Overstock / slow watch</h3><DataTable rows={intelligence.data.overstock_watch} columns={["product_name","category","on_hand_units","units_sold","days_of_cover"]}/></> : <div className="state">Building Buyer Intelligence evidence…</div>}</section> : null}
    </> : null}
  </div>;
}

function Metric({ label, value }: { label: string; value: string | number }) { return <article className="metric"><span>{label}</span><strong>{value}</strong></article>; }
function pretty(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase()); }
function text(value: unknown) { return value == null ? "" : String(value); }
function render(value: unknown) { if (value == null || value === "") return "—"; if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 }); return String(value); }
function DataTable({ rows, columns }: { rows: Row[]; columns: string[] }) { const visible = columns.filter(column => rows.some(row => row[column] !== undefined)); return <div className="table-wrap"><table><thead><tr>{visible.map(column => <th key={column}>{pretty(column)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={`${index}-${text(row.product_name ?? row.subcategory ?? row.sku)}`}>{visible.map(column => <td key={column}>{render(row[column])}</td>)}</tr>)}</tbody></table>{rows.length === 0 ? <div className="empty">No rows match this view.</div> : null}</div>; }
