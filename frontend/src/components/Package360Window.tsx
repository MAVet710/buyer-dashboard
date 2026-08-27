import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import { WorkspaceWindow } from "./WorkspaceWindow";

type TimelineEvent = { occurred_at:string|null;area:string;event_type:string;title:string;detail:string;actor:string;reference:string;status:string;quantity:number|null;unit:string };
type LineageRow = { run_id:string;lot_id:string|null;lot_code:string;package_id:string;product_name:string;quantity:number;unit:string;purpose:string };
type Snapshot = {
  package:{id:string;lot_code:string;package_id:string;location:string;status:string;received_at:string|null;expiration_at:string|null;balance:number;unit:string};
  product:{id:string;sku:string;name:string;item_type:string};
  lineage:{inputs:LineageRow[];outputs:LineageRow[];run_count:number};
  summary:{inventory_events:number;package_studio_runs:number;audits:number;order_allocations:number;traceability_actions:number};
  timeline:TimelineEvent[];
};

export function Package360Window({ code, open, onClose, onNavigate }: { code:string; open:boolean; onClose:()=>void; onNavigate?:(page:string)=>void }) {
  const snapshot=useQuery({queryKey:["package-360-window",code],enabled:open&&Boolean(code),queryFn:({signal})=>apiGet<Snapshot>(`/api/v1/package-360/resolve?code=${encodeURIComponent(code)}`,signal)});
  const data=snapshot.data;
  const title=data?.product.name??"Package 360";
  const subtitle=data?`${data.package.package_id||data.package.lot_code} · ${data.package.location||"Unassigned"} · ${formatTitle(data.package.status)}`:"Building facility-scoped package history…";
  const footer=data&&onNavigate?<><button className="secondary" type="button" onClick={()=>onNavigate("Package Studio")}>Work package</button><button className="secondary" type="button" onClick={()=>onNavigate("Compliance")}>Traceability</button></>:null;
  return <WorkspaceWindow open={open} onClose={onClose} eyebrow="PACKAGE 360 · source trail" title={title} subtitle={subtitle} footer={footer} ariaLabel="Package 360" windowKey={`package-360:${code}`} className="package-360-window">
    {snapshot.isLoading?<div className="state">Building package source trail…</div>:null}
    {snapshot.isError?<div className="warning-banner">{snapshot.error.message}</div>:null}
    {data?<>
      <section className="metrics four"><Metric label="On hand" value={`${number(data.package.balance)} ${data.package.unit}`}/><Metric label="Lineage runs" value={data.summary.package_studio_runs}/><Metric label="Audits" value={data.summary.audits}/><Metric label="Traceability" value={data.summary.traceability_actions}/></section>
      <section className="inventory-panel"><div className="eyebrow">CURRENT STATE</div><Row label="Package ID" value={data.package.package_id||"—"}/><Row label="Lot code" value={data.package.lot_code}/><Row label="Location" value={data.package.location||"—"}/><Row label="Status" value={formatTitle(data.package.status)}/><Row label="Received" value={date(data.package.received_at)}/><Row label="Expiration" value={date(data.package.expiration_at)}/><Row label="Inventory events" value={String(data.summary.inventory_events)}/><Row label="Order allocations" value={String(data.summary.order_allocations)}/></section>
      <section className="inventory-panel"><div className="eyebrow">GENEALOGY</div><h3>Inputs</h3>{data.lineage.inputs.length?data.lineage.inputs.map((row,index)=><Lineage key={`in-${index}`} row={row}/>):<div className="info-banner">No source inputs are linked to this package yet.</div>}<h3>Outputs</h3>{data.lineage.outputs.length?data.lineage.outputs.map((row,index)=><Lineage key={`out-${index}`} row={row}/>):<div className="info-banner">No child outputs are linked to this package yet.</div>}</section>
      <section className="inventory-panel"><div className="eyebrow">UNIFIED EVENT TIMELINE</div><h3>What happened, in order</h3>{!data.timeline.length?<div className="info-banner">No durable events have been recorded for this package yet.</div>:<div className="package-timeline">{data.timeline.map((event,index)=><article className="commercial-order-card" key={`${event.occurred_at}-${event.area}-${index}`}><div><strong>{event.title}</strong><span className="status-pill">{event.area}</span></div><p>{event.detail||formatTitle(event.event_type)}</p><small>{event.occurred_at?new Date(event.occurred_at).toLocaleString():"Unknown time"}{event.quantity!=null?` · ${event.quantity>0?"+":""}${number(event.quantity)} ${event.unit}`:""}{event.status?` · ${formatTitle(event.status)}`:""}{event.actor?` · ${event.actor}`:""}{event.reference?` · ${event.reference}`:""}</small></article>)}</div>}</section>
    </>:null}
  </WorkspaceWindow>;
}

function Metric({label,value}:{label:string;value:string|number}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function Row({label,value}:{label:string;value:string}){return <div className="catalog-row"><strong>{label}</strong><span>{value||"—"}</span></div>}
function Lineage({row}:{row:LineageRow}){return <div className="catalog-row"><strong>{row.product_name}</strong><span>{row.package_id||row.lot_code}</span><small>{number(row.quantity)} {row.unit} · {formatTitle(row.purpose)}</small></div>}
function formatTitle(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function number(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:2})}
function date(value:string|null){return value?new Date(value).toLocaleString():"—"}
