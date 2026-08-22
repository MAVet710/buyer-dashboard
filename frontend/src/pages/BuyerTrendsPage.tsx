import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../lib/api";

type Row = Record<string, unknown>;
type Trends = { sales_days: number; category_mix: Row[]; package_size_mix: Row[]; top_movers: Row[]; best_sellers_by_category: Row[]; fast_movers_low_stock: Row[] };
type Tab = "category" | "package" | "movers" | "best" | "fast";

export function BuyerTrendsPage() {
  const [salesDays, setSalesDays] = useState(60); const [tab, setTab] = useState<Tab>("category");
  const result = useQuery({ queryKey: ["buyer-trends-parity", salesDays], queryFn: ({ signal }) => apiGet<Trends>(`/api/v1/buyer-parity/trends?sales_days=${salesDays}`, signal) });
  const data = result.data;
  return <div className="page"><div className="page-heading"><div><div className="eyebrow">Retail Ops · Streamlit parity</div><h1>Sales & Category Trends</h1><p>Category mix, package-size mix, top movers, category best sellers, and fast movers with low stock from the same active Buyer Dash sources.</p></div><label className="compact-field">Sales window<select value={salesDays} onChange={event => setSalesDays(Number(event.target.value))}><option value={28}>28 days</option><option value={56}>56 days</option><option value={60}>60 days</option><option value={84}>84 days</option><option value={120}>120 days</option></select></label></div>
  {result.isError ? <div className="state error">{result.error.message}</div> : null}{result.isLoading ? <div className="state">Building trends from active Buyer Dash data…</div> : null}
  {data ? <><section className="metrics"><Metric label="Categories" value={data.category_mix.length}/><Metric label="Package Segments" value={data.package_size_mix.length}/><Metric label="Tracked Movers" value={data.top_movers.length}/><Metric label="Fast + Low Stock" value={data.fast_movers_low_stock.length}/></section><div className="view-tabs parity-tabs"><button className={tab === "category" ? "active" : ""} onClick={() => setTab("category")}>Category Mix</button><button className={tab === "package" ? "active" : ""} onClick={() => setTab("package")}>Package Size Mix</button><button className={tab === "movers" ? "active" : ""} onClick={() => setTab("movers")}>Top Movers by SKU</button><button className={tab === "best" ? "active" : ""} onClick={() => setTab("best")}>Best Sellers by Category</button><button className={tab === "fast" ? "active" : ""} onClick={() => setTab("fast")}>Fast Movers + Low Stock</button></div>
  {tab === "category" ? <Panel title="Category Mix"><Bars rows={data.category_mix} label="category" value="units"/><Table rows={data.category_mix} columns={["category","units","revenue"]}/></Panel> : null}
  {tab === "package" ? <Panel title="Package Size Mix"><Table rows={data.package_size_mix} columns={["category","packagesize","units"]}/></Panel> : null}
  {tab === "movers" ? <Panel title="Top Movers by SKU"><Table rows={data.top_movers.slice(0,100)} columns={["product_name","units","revenue"]}/></Panel> : null}
  {tab === "best" ? <Panel title="Best Sellers by Category"><Table rows={data.best_sellers_by_category} columns={["category","product_name","units"]}/></Panel> : null}
  {tab === "fast" ? <Panel title="Fast Movers + Low Stock"><Table rows={data.fast_movers_low_stock} columns={["product_name","subcategory","brand_vendor","sku","onhandunits","unitssold","avgunitsperday","daysonhand"]}/></Panel> : null}</> : null}</div>;
}
function Panel({ title, children }: { title: string; children: React.ReactNode }) { return <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Buyer trend view</div><h2>{title}</h2></div></div>{children}</section>; }
function Metric({ label, value }: { label: string; value: number | string }) { return <article className="metric"><span>{label}</span><strong>{value}</strong></article>; }
function str(value: unknown) { return value == null ? "" : String(value); }
function display(value: unknown) { if (value == null || value === "") return "—"; if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined,{maximumFractionDigits:2}); return String(value); }
function heading(value: string) { return value.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase()); }
function Table({ rows, columns }: { rows: Row[]; columns: string[] }) { const visible = columns.filter(column => rows.some(row => row[column] !== undefined)); return <div className="table-wrap"><table><thead><tr>{visible.map(column => <th key={column}>{heading(column)}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={`${index}-${str(row.product_name ?? row.category)}`}>{visible.map(column=><td key={column}>{display(row[column])}</td>)}</tr>)}</tbody></table>{rows.length===0?<div className="empty">No data in this view.</div>:null}</div>; }
function Bars({ rows, label, value }: { rows: Row[]; label: string; value: string }) { const max = Math.max(...rows.map(row => Number(row[value] ?? 0)),1); return <div className="bar-list">{rows.slice(0,12).map((row,index)=><div className="mix-bar" key={`${index}-${str(row[label])}`}><span>{str(row[label])}</span><div><i style={{width:`${Number(row[value] ?? 0)/max*100}%`}}/></div><strong>{Number(row[value] ?? 0).toLocaleString()}</strong></div>)}</div>; }
