import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type Lot={id:string;lot_code:string;package_id:string;barcode:string;location:string;status:string;on_hand:number;received_at:string|null;expiration_at:string|null};
type PickLine={order_id:string;order_number:string;due_at:string|null;order_status:string;line_id:string;position:number;product_id:string;product_name:string;sku:string;unit:string;ordered:number;fulfilled:number;remaining:number;recommended_lot:Lot|null;available_lots:Lot[]};
type Queue={facility_id:string;open_sales_orders:number;lines_to_pick:number;queue:PickLine[]};
type PickResult={action:string;status?:string;quantity?:number;quantity_delta?:number;unit?:string};

export function WarehousePickPackPage({onNavigate}:{onNavigate:(page:string)=>void}){
  const client=useQueryClient();
  const queue=useQuery({queryKey:["warehouse-pick-queue"],queryFn:({signal})=>apiGet<Queue>("/api/v1/warehouse/pick-queue",signal)});
  const [index,setIndex]=useState(0);
  const current=queue.data?.queue[index]??queue.data?.queue[0];
  useEffect(()=>{if(queue.data&&index>=queue.data.queue.length)setIndex(Math.max(0,queue.data.queue.length-1))},[queue.data,index]);
  return <div className="page warehouse-pick-pack"><div className="page-heading"><div><div className="eyebrow">WAREHOUSE · MOBILE PICK / PACK</div><h1>Scan it. Verify it. Move it.</h1><p>DoobieLogic recommends the earliest-expiring available lot first, but the scan is the final identity check before anything is reserved or shipped.</p></div><div className="heading-actions"><button className="secondary" onClick={()=>onNavigate("Orders")}>Orders</button><button className="secondary" onClick={()=>onNavigate("Package 360")}>Package 360</button></div></div>
    {queue.isLoading?<div className="state">Building pick queue…</div>:null}{queue.isError?<div className="warning-banner">{queue.error.message}</div>:null}
    {queue.data?<section className="metrics four"><Metric label="Open sales orders" value={queue.data.open_sales_orders}/><Metric label="Lines to pick" value={queue.data.lines_to_pick}/><Metric label="Current line" value={queue.data.lines_to_pick?`${Math.min(index+1,queue.data.lines_to_pick)} / ${queue.data.lines_to_pick}`:"—"}/><Metric label="Mode" value="FEFO + scan"/></section>:null}
    {queue.data&&!queue.data.queue.length?<div className="success-banner"><strong>Pick queue is clear.</strong><br/>No open sales-order lines need warehouse fulfillment.</div>:null}
    {current?<PickCard line={current} onDone={async()=>{await client.invalidateQueries({queryKey:["warehouse-pick-queue"]});setIndex(value=>value+1)}} onPrevious={()=>setIndex(value=>Math.max(0,value-1))} onNext={()=>setIndex(value=>Math.min((queue.data?.queue.length??1)-1,value+1))}/>:null}
  </div>;
}

function PickCard({line,onDone,onPrevious,onNext}:{line:PickLine;onDone:()=>void;onPrevious:()=>void;onNext:()=>void}){
  const [lotId,setLotId]=useState(line.recommended_lot?.id??line.available_lots[0]?.id??"");
  const selected=useMemo(()=>line.available_lots.find(row=>row.id===lotId)??line.recommended_lot??line.available_lots[0],[line,lotId]);
  const [quantity,setQuantity]=useState(Math.min(line.remaining,selected?.on_hand??line.remaining));
  const [scan,setScan]=useState(""); const [reference,setReference]=useState(line.order_number); const [message,setMessage]=useState("");
  useEffect(()=>{const next=line.recommended_lot??line.available_lots[0];setLotId(next?.id??"");setQuantity(Math.min(line.remaining,next?.on_hand??line.remaining));setScan("");setMessage("");setReference(line.order_number)},[line.line_id,line.order_number,line.remaining,line.recommended_lot,line.available_lots]);
  const reserve=useMutation({mutationFn:()=>apiPost<PickResult>("/api/v1/warehouse/pick",{order_line_id:line.line_id,lot_id:selected?.id,quantity,scan_code:scan,action:"reserve",reference}),onSuccess:()=>setMessage("Lot reserved. Scan remains verified for this selected package.")});
  const ship=useMutation({mutationFn:()=>apiPost<PickResult>("/api/v1/warehouse/pick",{order_line_id:line.line_id,lot_id:selected?.id,quantity,scan_code:scan,action:"ship",reference}),onSuccess:()=>{setMessage("Shipment posted to the immutable inventory ledger.");void onDone()}});
  if(!line.available_lots.length)return <section className="inventory-panel"><div className="eyebrow">{line.order_number} · LINE {line.position}</div><h2>{line.product_name}</h2><div className="warning-banner">No released/available lot has positive inventory for this line. Resolve inventory before picking.</div></section>;
  const scanned=selected?matches(selected,scan):false;
  return <section className="inventory-panel"><div className="eyebrow">{line.order_number} · LINE {line.position}</div><div className="page-heading"><div><h2>{line.product_name}</h2><p>{line.sku} · {number(line.remaining)} {line.unit} remaining · Due {date(line.due_at)}</p></div><span className="status-pill">{title(line.order_status)}</span></div>
    <div className="two-column-grid"><section><div className="eyebrow">1 · PICK LOT</div><label>Inventory lot<select value={selected?.id??""} onChange={event=>{const next=line.available_lots.find(row=>row.id===event.target.value);setLotId(event.target.value);setQuantity(Math.min(line.remaining,next?.on_hand??line.remaining));setScan("");setMessage("")}}>{line.available_lots.map((row,index)=><option value={row.id} key={row.id}>{index===0?"Recommended · ":""}{row.package_id||row.lot_code} · {number(row.on_hand)} {line.unit} · {row.location}</option>)}</select></label><div className="catalog-row"><strong>Recommended policy</strong><span>FEFO, then oldest receipt</span></div><div className="catalog-row"><strong>Expiration</strong><span>{date(selected?.expiration_at??null)}</span></div><div className="catalog-row"><strong>Location</strong><span>{selected?.location||"—"}</span></div><div className="catalog-row"><strong>Available</strong><span>{number(selected?.on_hand??0)} {line.unit}</span></div></section>
    <section><div className="eyebrow">2 · SCAN & VERIFY</div><label>Scan package / barcode<input autoFocus inputMode="text" autoComplete="off" value={scan} placeholder={selected?.package_id||selected?.lot_code||"Scan selected lot"} onChange={event=>setScan(event.target.value)}/></label>{scan?<div className={scanned?"success-banner":"warning-banner"}>{scanned?"Scan verified against the selected facility lot.":"Scan does not match this lot. No action can post."}</div>:<div className="info-banner">A matching package, lot, barcode, or internal lot ID is required before reserve/ship.</div>}<label>Quantity<input type="number" min="0.0001" max={Math.min(line.remaining,selected?.on_hand??line.remaining)} step="0.0001" value={quantity} onChange={event=>setQuantity(Number(event.target.value))}/></label><label>Shipment reference<input value={reference} onChange={event=>setReference(event.target.value)}/></label></section></div>
    <div className="audit-actions"><button className="secondary" onClick={onPrevious}>Previous</button><button className="secondary" onClick={onNext}>Next</button><button className="primary" disabled={!scanned||quantity<=0||reserve.isPending||ship.isPending} onClick={()=>reserve.mutate()}>Reserve scanned lot</button><button className="primary" disabled={!scanned||quantity<=0||reserve.isPending||ship.isPending} onClick={()=>ship.mutate()}>Post shipment</button></div>{message?<div className="success-banner">{message}</div>:null}{reserve.isError||ship.isError?<div className="form-error">{reserve.error?.message??ship.error?.message}</div>:null}
  </section>;
}
function matches(lot:Lot,value:string){const needle=value.trim().toLowerCase();return Boolean(needle&&[lot.id,lot.lot_code,lot.package_id,lot.barcode].some(item=>String(item||"").trim().toLowerCase()===needle))}
function Metric({label,value}:{label:string;value:string|number}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function number(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:2})}
function date(value:string|null){return value?new Date(value).toLocaleDateString():"No date"}
