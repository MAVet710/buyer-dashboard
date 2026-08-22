import { useState } from "react";
import { apiPostForm, downloadBlob } from "../lib/api";

type Row = Record<string, unknown>;
type Kpis = Record<string, unknown> & { top_items?: Row[] };
type Result = {
  received_at: string;
  window_days: number;
  manifest_filename: string;
  sales_filename: string;
  manifest_items: Row[];
  matched: Record<string, string>;
  unmatched: string[];
  matched_count: number;
  unmatched_count: number;
  kpis: Kpis;
  weekday_wow: Kpis;
  daily_series: Row[];
  hourly_series: Row[];
  wow_delivery_series: Row[];
  wow_prior_series: Row[];
  debug_text: string;
};

export function DeliveryImpactPage() {
  const [manifest, setManifest] = useState<File | null>(null);
  const [sales, setSales] = useState<File | null>(null);
  const [receivedAt, setReceivedAt] = useState("");
  const [windowDays, setWindowDays] = useState(14);
  const [threshold, setThreshold] = useState(0.82);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const analyze = async () => {
    if (!manifest || !sales) return;
    setBusy(true); setError("");
    const form = new FormData(); form.append("manifest", manifest); form.append("sales", sales); form.append("received_at", receivedAt); form.append("window_days", String(windowDays)); form.append("fuzzy_threshold", String(threshold));
    try { setResult(await apiPostForm<Result>("/api/v1/buyer-parity/delivery-impact", form)); }
    catch (err) { setError(err instanceof Error ? err.message : "Delivery Impact failed."); }
    finally { setBusy(false); }
  };
  const debug = () => result && downloadBlob(new Blob([result.debug_text], { type: "text/plain;charset=utf-8" }), "delivery_manifest_debug.txt");
  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">Retail Ops · original Buyer Dash analysis</div><h1>Delivery Performance</h1><p>Upload the delivery manifest and order-level sales report, then compare the original before/after and same-weekday performance windows.</p></div></div>
    <section className="inventory-panel upload-workspace"><div className="form-grid"><label className="file-drop">Delivery manifest<input type="file" accept=".pdf,.csv,.xlsx,.xls" onChange={event => setManifest(event.target.files?.[0] ?? null)}/><span>{manifest?.name ?? "PDF, CSV or Excel"}</span></label><label className="file-drop">Sales report<input type="file" accept=".csv,.xlsx,.xls" onChange={event => setSales(event.target.files?.[0] ?? null)}/><span>{sales?.name ?? "Order-level CSV or Excel"}</span></label><label>Received date/time override<input type="datetime-local" value={receivedAt} onChange={event => setReceivedAt(event.target.value)}/><small>Leave blank to use the manifest's received date.</small></label><label>Before / after window<select value={windowDays} onChange={event => setWindowDays(Number(event.target.value))}><option value={7}>7 days</option><option value={14}>14 days</option><option value={21}>21 days</option><option value={28}>28 days</option></select></label><label>Fuzzy match threshold<input type="number" min={0.5} max={1} step={0.01} value={threshold} onChange={event => setThreshold(Number(event.target.value))}/></label></div><button className="primary submit" disabled={!manifest || !sales || busy} onClick={analyze}>{busy ? "Analyzing delivery…" : "Analyze Delivery Impact"}</button>{error ? <div className="form-error">{error}</div> : null}</section>
    {result ? <>
      <section className="metrics"><Metric label="Matched Manifest Items" value={result.matched_count}/><Metric label="Unmatched Items" value={result.unmatched_count}/><Metric label="Before Net Sales" value={money(num(result.kpis.net_sales_before))}/><Metric label="After Net Sales" value={money(num(result.kpis.net_sales_after))}/><Metric label="Net Sales Lift" value={signedMoney(num(result.kpis.net_sales_lift_abs))}/></section>
      <div className="two-column-grid"><section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">{result.window_days}-day window</div><h2>Before vs After</h2></div></div><KpiGrid data={result.kpis}/></section><section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Same weekday</div><h2>Week-over-Week</h2></div></div><KpiGrid data={result.weekday_wow}/></section></div>
      <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Sales trend</div><h2>Daily Delivery Impact</h2></div></div><LineChart current={result.daily_series}/></section>
      <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Same weekday overlay</div><h2>Delivery Day vs Prior Week</h2></div></div><LineChart current={result.wow_delivery_series} prior={result.wow_prior_series}/></section>
      <div className="two-column-grid"><section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Lift leaders</div><h2>Top Delivered Items</h2></div></div><Table rows={(result.kpis.top_items ?? []) as Row[]} columns={["item_name","net_sales_before","net_sales_after","sales_lift","units_before","units_after","units_lift"]}/></section><section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Match review</div><h2>Unmatched Manifest Items</h2></div></div>{result.unmatched.length ? <ul className="exception-list">{result.unmatched.map(item => <li key={item}>{item}</li>)}</ul> : <div className="success-banner">Every manifest item matched a sales product.</div>}</section></div>
      <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Manifest parsing</div><h2>Detected Items & Debug</h2><p>Received {new Date(result.received_at).toLocaleString()} · {result.manifest_filename} + {result.sales_filename}</p></div><button className="secondary" onClick={debug}>Download PDF Debug Text</button></div><Table rows={result.manifest_items} columns={["item_name","qty","package_id","batch","license_number","location"]}/></section>
    </> : null}
  </div>;
}
function Metric({ label, value }: { label: string; value: string | number }) { return <article className="metric"><span>{label}</span><strong>{value}</strong></article>; }
function num(value: unknown) { const n = Number(value ?? 0); return Number.isFinite(n) ? n : 0; }
function money(value: number) { return value.toLocaleString(undefined,{style:"currency",currency:"USD",maximumFractionDigits:2}); }
function signedMoney(value: number) { return `${value >= 0 ? "+" : ""}${money(value)}`; }
function pct(value: unknown) { const n = Number(value); return Number.isFinite(n) ? `${n >= 0 ? "+" : ""}${n.toFixed(1)}%` : "—"; }
function KpiGrid({ data }: { data: Kpis }) { return <div className="kpi-detail-grid"><Metric label="Net Sales Before" value={money(num(data.net_sales_before))}/><Metric label="Net Sales After" value={money(num(data.net_sales_after))}/><Metric label="Net Sales Lift" value={`${signedMoney(num(data.net_sales_lift_abs))} · ${pct(data.net_sales_lift_pct)}`}/><Metric label="Orders" value={`${num(data.orders_before).toLocaleString()} → ${num(data.orders_after).toLocaleString()}`}/><Metric label="Delivered Sales Lift" value={`${signedMoney(num(data.delivered_sales_lift_abs))} · ${pct(data.delivered_sales_lift_pct)}`}/><Metric label="Delivered Unit Lift" value={`${num(data.delivered_units_lift_abs) >= 0 ? "+" : ""}${num(data.delivered_units_lift_abs).toLocaleString()} · ${pct(data.delivered_units_lift_pct)}`}/></div>; }
function LineChart({ current, prior = [] }: { current: Row[]; prior?: Row[] }) { const width=1000,height=300,pad=34; const values=[...current,...prior].map(row=>num(row.total_net_sales)); const max=Math.max(...values,1); const points=(rows:Row[])=>rows.map((row,index)=>`${pad+index*((width-pad*2)/Math.max(rows.length-1,1))},${height-pad-num(row.total_net_sales)/max*(height-pad*2)}`).join(" "); return <div className="chart-shell"><svg viewBox={`0 0 ${width} ${height}`} className="parity-line-chart" role="img" aria-label="Delivery sales impact chart"><line x1={pad} x2={width-pad} y1={height-pad} y2={height-pad}/>{prior.length ? <polyline className="prior" points={points(prior)}/> : null}<polyline className="current" points={points(current)}/>{current.map((row,index)=><circle key={`${index}-${String(row.period)}`} cx={pad+index*((width-pad*2)/Math.max(current.length-1,1))} cy={height-pad-num(row.total_net_sales)/max*(height-pad*2)} r="4"><title>{String(row.period)} · {money(num(row.total_net_sales))}</title></circle>)}</svg>{prior.length ? <div className="chart-legend"><span>Delivery period</span><span>Prior same weekday</span></div> : null}</div>; }
function heading(value:string){return value.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());} function display(value:unknown){if(value==null||value==="")return"—";if(typeof value==="number")return Number.isInteger(value)?value.toLocaleString():value.toLocaleString(undefined,{maximumFractionDigits:2});return String(value);} function Table({rows,columns}:{rows:Row[];columns:string[]}){const visible=columns.filter(column=>rows.some(row=>row[column]!==undefined));return <div className="table-wrap"><table><thead><tr>{visible.map(column=><th key={column}>{heading(column)}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{visible.map(column=><td key={column}>{display(row[column])}</td>)}</tr>)}</tbody></table>{rows.length===0?<div className="empty">No rows in this view.</div>:null}</div>;}
