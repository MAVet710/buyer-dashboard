import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type TimelineEvent = { occurred_at:string|null;area:string;event_type:string;title:string;detail:string;actor:string;reference:string;status:string;quantity:number|null;unit:string };
type LineageRow = { run_id:string;lot_id:string|null;lot_code:string;package_id:string;product_name:string;quantity:number;unit:string;purpose:string };
type Snapshot = {
  package:{id:string;lot_code:string;package_id:string;location:string;status:string;received_at:string|null;expiration_at:string|null;balance:number;unit:string};
  product:{id:string;sku:string;name:string;item_type:string};
  lineage:{inputs:LineageRow[];outputs:LineageRow[];run_count:number};
  summary:{inventory_events:number;package_studio_runs:number;audits:number;order_allocations:number;traceability_actions:number};
  timeline:TimelineEvent[];
};

export function Package360Page({onNavigate,initialCode=""}:{onNavigate:(page:string)=>void;initialCode?:string}){
  const [input,setInput]=useState(initialCode);
  const [code,setCode]=useState(initialCode);
  const snapshot=useQuery({queryKey:["package-360",code],enabled:Boolean(code),queryFn:({signal})=>apiGet<Snapshot>(`/api/v1/package-360/resolve?code=${encodeURIComponent(code)}`,signal)});
  const data=snapshot.data;
  return <div className="page package-360-page">
    <div className="eyebrow">PACKAGE 360 · SOURCE TRAIL</div><h1>Follow the package, not the spreadsheet.</h1><p className="section-note">Scan or enter a package ID, lot code, barcode, or internal lot ID to see the complete facility-scoped operational history.</p>
    <section className="inventory-panel"><form className="two-column-grid" onSubmit={event=>{event.preventDefault();setCode(input.trim())}}><label>Package / lot identifier<input autoFocus value={input} placeholder="Scan or enter package, lot, or barcode" onChange={event=>setInput(event.target.value)}/></label><div className="heading-actions"><button className="primary" type="submit" disabled={!input.trim()}>Open Package 360</button></div></form></section>
    {snapshot.isLoading?<div className="state">Building package source trail…</div>:null}
    {snapshot.isError?<div className="warning-banner">{snapshot.error.message}</div>:null}
    {data?<>
      <section className="page-heading"><div><div className="eyebrow">{data.package.package_id||data.package.lot_code}</div><h2>{data.product.name}</h2><p>{data.product.sku} · {data.package.location||"Unassigned"} · {title(data.package.status)}</p></div><div className="heading-actions"><button className="secondary" onClick={()=>onNavigate("Inventory")}>Inventory</button><button className="secondary" onClick={()=>onNavigate("Package Studio")}>Package Studio</button><button className="secondary" onClick={()=>onNavigate("Compliance")}>Traceability</button></div></section>
      <section className="metrics four"><Metric label="On hand" value={`${number(data.package.balance)} ${data.package.unit}`}/><Metric label="Lineage runs" value={data.summary.package_studio_runs}/><Metric label="Audits" value={data.summary.audits}/><Metric label="Traceability" value={data.summary.traceability_actions}/></section>
      <div className="two-column-grid"><section className="inventory-panel"><div className="eyebrow">PACKAGE STATE</div><h2>Current state</h2><Row label="Package ID" value={data.package.package_id||"—"}/><Row label="Lot code" value={data.package.lot_code}/><Row label="Location" value={data.package.location||"—"}/><Row label="Status" value={title(data.package.status)}/><Row label="Received" value={date(data.package.received_at)}/><Row label="Expiration" value={date(data.package.expiration_at)}/><Row label="Inventory events" value={String(data.summary.inventory_events)}/><Row label="Order allocations" value={String(data.summary.order_allocations)}/></section><section className="inventory-panel"><div className="eyebrow">GENEALOGY</div><h2>Inputs & outputs</h2><h3>Inputs</h3>{data.lineage.inputs.length?data.lineage.inputs.map((row,index)=><Lineage key={`in-${index}`} row={row}/>):<div className="info-banner">No Package Studio source inputs are linked to this package yet.</div>}<h3>Outputs</h3>{data.lineage.outputs.length?data.lineage.outputs.map((row,index)=><Lineage key={`out-${index}`} row={row}/>):<div className="info-banner">No Package Studio child outputs are linked to this package yet.</div>}</section></div>
      <section className="inventory-panel"><div className="eyebrow">UNIFIED EVENT TIMELINE</div><h2>What happened, in order</h2>{!data.timeline.length?<div className="info-banner">No durable events have been recorded for this package yet.</div>:<div className="package-timeline">{data.timeline.map((event,index)=><article className="commercial-order-card" key={`${event.occurred_at}-${event.area}-${index}`}><div><strong>{event.title}</strong><span className="status-pill">{event.area}</span></div><p>{event.detail||title(event.event_type)}</p><small>{event.occurred_at?new Date(event.occurred_at).toLocaleString():"Unknown time"}{event.quantity!=null?` · ${event.quantity>0?"+":""}${number(event.quantity)} ${event.unit}`:""}{event.status?` · ${title(event.status)}`:""}{event.actor?` · ${event.actor}`:""}{event.reference?` · ${event.reference}`:""}</small></article>)}</div>}</section>
    </>:null}
  </div>;
}
function Metric({label,value}:{label:string;value:string|number}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function Row({label,value}:{label:string;value:string}){return <div className="catalog-row"><strong>{label}</strong><span>{value||"—"}</span></div>}
function Lineage({row}:{row:LineageRow}){return <div className="catalog-row"><strong>{row.product_name}</strong><span>{row.package_id||row.lot_code}</span><small>{number(row.quantity)} {row.unit} · {title(row.purpose)}</small></div>}
function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function number(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:2})}
function date(value:string|null){return value?new Date(value).toLocaleString():"—"}
