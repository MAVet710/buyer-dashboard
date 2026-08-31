import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type Reservation = { id:string; lot_id:string; quantity:number; unit:string; status:string };
type InventoryLot = { id:string; lot_code:string; product_id:string; product_name:string; on_hand:number; available:number; reserved:number; production_reserved:number; unit:string; status:string; location:string };
type InventoryResponse = { items:InventoryLot[] };
type MaterialRow = { lot_id:string; quantity:string; unit:string; purpose:string };
type Preview = { title:string; summary:string; preview_key:string; blocker_count:number; consequences:Array<{label:string;before:string;after:string}>; warnings:Array<{severity:string;message:string}>; details?:{material_variance?:Array<Record<string,unknown>>} };

type Props = {
  orderId:string;
  requirements:Array<Record<string,unknown>>;
  reservations:Reservation[];
  onChanged:()=>void|Promise<void>;
};

export function ProductionActualMaterials({orderId,requirements,reservations,onChanged}:Props) {
  const inventory=useQuery({
    queryKey:["production-actual-material-lots",orderId],
    queryFn:({signal})=>apiGet<InventoryResponse>("/api/v1/inventory/production/packages?view=all",signal),
  });
  const requiredProductIds=useMemo(()=>new Set(requirements.map(row=>String(row.product_id??"")).filter(Boolean)),[requirements]);
  const reservedLotIds=useMemo(()=>new Set(reservations.filter(row=>row.status==="reserved"&&row.quantity>0).map(row=>row.lot_id)),[reservations]);
  const eligible=useMemo(()=>(inventory.data?.items??[]).filter(row=>
    requiredProductIds.has(row.product_id)&&(row.available>0||reservedLotIds.has(row.id))
  ),[inventory.data?.items,requiredProductIds,reservedLotIds]);
  const [rows,setRows]=useState<MaterialRow[]>([]);
  const [preview,setPreview]=useState<Preview|null>(null);
  const [message,setMessage]=useState("");

  useEffect(()=>{
    if(rows.length||!eligible.length)return;
    const first=eligible[0];
    const reservation=reservations.find(row=>row.lot_id===first.id&&row.status==="reserved");
    setRows([{lot_id:first.id,quantity:String(reservation?.quantity??""),unit:first.unit,purpose:"source_material"}]);
  },[eligible,reservations,rows.length]);
  useEffect(()=>{setRows([]);setPreview(null);setMessage("")},[orderId]);

  const payload=()=>({materials:rows.filter(row=>row.lot_id&&Number(row.quantity)>0).map(row=>({
    lot_id:row.lot_id,quantity:Number(row.quantity),unit:row.unit,purpose:row.purpose||"source_material",
  }))});
  const previewMutation=useMutation({
    mutationFn:()=>apiPost<Preview>(`/api/v1/production/orders/${orderId}/mutations/preview`,{action_type:"consume_materials",payload:payload()}),
    onSuccess:data=>{setPreview(data);setMessage("")},
  });
  const commitMutation=useMutation({
    mutationFn:()=>{
      if(!preview)throw new Error("Preview actual consumption before applying it.");
      return apiPost<{summary:string}>(`/api/v1/production/orders/${orderId}/mutations/commit`,{action_type:"consume_materials",payload:payload(),preview_key:preview.preview_key});
    },
    onSuccess:async data=>{setMessage(data.summary||"Actual material consumption posted.");setPreview(null);setRows([]);await onChanged();},
  });

  const update=(index:number,patch:Partial<MaterialRow>)=>setRows(current=>current.map((row,rowIndex)=>rowIndex===index?{...row,...patch}:row));
  const remove=(index:number)=>setRows(current=>current.filter((_,rowIndex)=>rowIndex!==index));
  const add=()=>{
    const used=new Set(rows.map(row=>row.lot_id));
    const candidate=eligible.find(row=>!used.has(row.id))??eligible[0];
    if(!candidate)return;
    const reservation=reservations.find(row=>row.lot_id===candidate.id&&row.status==="reserved");
    setRows(current=>[...current,{lot_id:candidate.id,quantity:String(reservation?.quantity??""),unit:candidate.unit,purpose:"source_material"}]);
  };
  const blockers=preview?.blocker_count??0;

  return <section className="inventory-panel">
    <div className="section-heading"><div><div className="eyebrow">ACTUAL MATERIALS</div><h3>Record what physically went into this run</h3><p className="source-caption">Reservations are the plan. This step decrements the actual source lot, reconciles the reservation and becomes the finished product's source genealogy.</p></div><button className="secondary" type="button" disabled={!eligible.length} onClick={add}>Add source lot</button></div>
    {inventory.isLoading?<div className="state">Loading production material lots…</div>:null}
    {inventory.isError?<div className="state error">{inventory.error.message}</div>:null}
    {!inventory.isLoading&&!eligible.length?<div className="info-banner">No eligible on-hand or reserved lots match this run's BOM requirements.</div>:null}
    {rows.length?<div className="table-wrap"><table><thead><tr><th>Source lot</th><th>Physical / available</th><th>Actual used</th><th>Purpose</th><th></th></tr></thead><tbody>{rows.map((row,index)=>{
      const lot=eligible.find(item=>item.id===row.lot_id);
      return <tr key={`${index}-${row.lot_id}`}><td><select value={row.lot_id} onChange={event=>{const next=eligible.find(item=>item.id===event.target.value);update(index,{lot_id:event.target.value,unit:next?.unit??row.unit});setPreview(null)}}>{eligible.map(item=><option key={item.id} value={item.id}>{item.product_name} · {item.lot_code}</option>)}</select><small>{lot?.location||"Unassigned"} · {lot?.status||""}</small></td><td>{lot?`${number(lot.on_hand)} ${lot.unit} on hand · ${number(lot.available)} ${lot.unit} uncommitted`:"—"}</td><td><div className="inline-field"><input aria-label="Actual quantity used" type="number" min="0" step="any" value={row.quantity} onChange={event=>{update(index,{quantity:event.target.value});setPreview(null)}}/><span>{row.unit}</span></div></td><td><input value={row.purpose} onChange={event=>{update(index,{purpose:event.target.value});setPreview(null)}}/></td><td><button className="secondary" type="button" onClick={()=>{remove(index);setPreview(null)}}>Remove</button></td></tr>})}</tbody></table></div>:null}
    <div className="audit-actions"><button className="primary" type="button" disabled={!rows.some(row=>row.lot_id&&Number(row.quantity)>0)||previewMutation.isPending} onClick={()=>previewMutation.mutate()}>{previewMutation.isPending?"Checking…":"Preview actual consumption"}</button>{preview?<button className="primary" type="button" disabled={blockers>0||commitMutation.isPending} onClick={()=>commitMutation.mutate()}>{commitMutation.isPending?"Applying…":"Apply physical consumption"}</button>:null}{preview?<button className="secondary" type="button" onClick={()=>setPreview(null)}>Cancel preview</button>:null}</div>
    {previewMutation.isError?<div className="form-error">{previewMutation.error.message}</div>:null}{commitMutation.isError?<div className="form-error">{commitMutation.error.message}</div>:null}{message?<div className="success-banner">{message}</div>:null}
    {preview?<div className={blockers?"warning-banner":"info-banner"}><strong>{preview.title}</strong><br/><span>{preview.summary}</span>{preview.consequences.map((row,index)=><div key={index}><strong>{row.label}:</strong> {row.before} → {row.after}</div>)}{preview.warnings.map((row,index)=><div key={`w-${index}`}><strong>{row.severity.toUpperCase()}:</strong> {row.message}</div>)}</div>:null}
  </section>;
}

function number(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:4})}
