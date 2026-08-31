import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type Product = { id:string; sku:string; name:string; item_type:string; base_unit:string };
type OutputRow = { product_id:string; lot_code:string; quantity:string; unit:string; purpose:string; measurement_basis:"dry"|"wet"; location_code:string; status:string; compliance_package_id:string };
type LossRow = { quantity:string; unit:string; loss_type:string; measurement_basis:"dry"|"wet"; reason:string };
type Reconciliation = { measured:number; already_allocated:number; requested:number; allocated_after:number; remaining:number };
type Preview = { harvest_id:string;harvest_code:string;status:string;outputs:Array<Record<string,unknown>>;losses:Array<Record<string,unknown>>;reconciliation:Record<string,Reconciliation>;warnings:Array<{severity:string;message:string}>;blocker_count:number;preview_key:string };

type Props = {
  harvestId:string;
  wetWeight:number;
  dryWeight:number;
  status:string;
  onChanged:()=>void|Promise<void>;
};

const PURPOSES = [
  ["finished_flower","Finished flower"],
  ["smalls","Smalls"],
  ["trim","Trim"],
  ["biomass","Biomass"],
  ["fresh_frozen","Fresh frozen"],
  ["recoverable_material","Recoverable material"],
  ["other","Other"],
] as const;

export function HarvestOutputAllocation({harvestId,wetWeight,dryWeight,status,onChanged}:Props) {
  const products=useQuery({queryKey:["inventory-products"],queryFn:({signal})=>apiGet<Product[]>("/api/v1/inventory/products",signal)});
  const cannabisProducts=useMemo(()=>(products.data??[]).filter(row=>row.item_type==="cannabis"||row.item_type==="wip"),[products.data]);
  const [rows,setRows]=useState<OutputRow[]>([]);
  const [losses,setLosses]=useState<LossRow[]>([]);
  const [preview,setPreview]=useState<Preview|null>(null);
  const [message,setMessage]=useState("");

  useEffect(()=>{setRows([]);setLosses([]);setPreview(null);setMessage("")},[harvestId]);
  useEffect(()=>{
    if(rows.length||!cannabisProducts.length)return;
    const product=cannabisProducts[0];
    setRows([emptyOutput(product)]);
  },[cannabisProducts,rows.length]);

  const payload=()=>({
    outputs:rows.filter(row=>row.product_id&&row.lot_code.trim()&&Number(row.quantity)>0).map(row=>({...row,quantity:Number(row.quantity)})),
    losses:losses.filter(row=>Number(row.quantity)>0).map(row=>({...row,quantity:Number(row.quantity)})),
  });
  const previewMutation=useMutation({
    mutationFn:()=>apiPost<Preview>(`/api/v1/inventory/production/plants/harvests/${harvestId}/outputs/preview`,payload()),
    onSuccess:data=>{setPreview(data);setMessage("")},
  });
  const commitMutation=useMutation({
    mutationFn:()=>{
      if(!preview)throw new Error("Preview this harvest allocation before posting inventory.");
      return apiPost<{harvest_code:string;output_lot_ids:string[]}>(`/api/v1/inventory/production/plants/harvests/${harvestId}/outputs/commit`,{...payload(),preview_key:preview.preview_key});
    },
    onSuccess:async data=>{setMessage(`${data.output_lot_ids.length} harvest output lot${data.output_lot_ids.length===1?"":"s"} posted to Production Inventory.`);setRows([]);setLosses([]);setPreview(null);await onChanged();},
  });

  const addOutput=()=>{
    const product=cannabisProducts[0];
    if(product)setRows(current=>[...current,emptyOutput(product)]);
  };
  const addLoss=()=>setLosses(current=>[...current,{quantity:"",unit:"g",loss_type:"process_loss",measurement_basis:"dry",reason:""}]);
  const updateOutput=(index:number,patch:Partial<OutputRow>)=>{setRows(current=>current.map((row,rowIndex)=>rowIndex===index?{...row,...patch}:row));setPreview(null)};
  const updateLoss=(index:number,patch:Partial<LossRow>)=>{setLosses(current=>current.map((row,rowIndex)=>rowIndex===index?{...row,...patch}:row));setPreview(null)};
  const open=status==="active"||status==="drying";

  return <section className="inventory-panel">
    <div className="section-heading"><div><div className="eyebrow">HARVEST → INVENTORY</div><h3>Allocate physical harvest output</h3><p className="source-caption">DoobieLogic already knows the harvest, plants, strain and facility. Choose only what the material became, how much exists, and where it is now. Wet and dry measurements stay separate so fresh-frozen and dried material are never falsely added together.</p></div><div className="audit-actions"><button className="secondary" type="button" disabled={!open||!cannabisProducts.length} onClick={addOutput}>Add output</button><button className="secondary" type="button" disabled={!open} onClick={addLoss}>Add loss</button></div></div>
    <div className="metrics four"><Metric label="Measured wet" value={`${num(wetWeight)} g`}/><Metric label="Measured dry" value={`${num(dryWeight)} g`}/><Metric label="Output rows" value={rows.length}/><Metric label="Loss rows" value={losses.length}/></div>
    {status==="completed"?<div className="info-banner">This harvest is completed. Material disposition is closed and cannot be changed without a future governed correction/reopen workflow.</div>:!open?<div className="info-banner">Start this harvest before allocating physical output.</div>:null}
    {products.isLoading?<div className="state">Loading Product Master…</div>:null}{products.isError?<div className="state error">{products.error.message}</div>:null}
    {open&&!products.isLoading&&!cannabisProducts.length?<div className="warning-banner">Create at least one active cannabis or WIP Product Master item before posting harvest output.</div>:null}
    {rows.length?<div className="table-wrap"><table><thead><tr><th>Material</th><th>Lot code</th><th>Purpose</th><th>Basis</th><th>Quantity</th><th>Location / status</th><th></th></tr></thead><tbody>{rows.map((row,index)=><tr key={index}><td><select value={row.product_id} onChange={event=>{const product=cannabisProducts.find(item=>item.id===event.target.value);updateOutput(index,{product_id:event.target.value,unit:product?.base_unit==="g"?"g":row.unit})}}>{cannabisProducts.map(item=><option key={item.id} value={item.id}>{item.sku} · {item.name}</option>)}</select></td><td><input value={row.lot_code} placeholder="GP-0830-FLOWER" onChange={event=>updateOutput(index,{lot_code:event.target.value})}/><input value={row.compliance_package_id} placeholder="External package/tag optional" onChange={event=>updateOutput(index,{compliance_package_id:event.target.value})}/></td><td><select value={row.purpose} onChange={event=>updateOutput(index,{purpose:event.target.value})}>{PURPOSES.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></td><td><select value={row.measurement_basis} onChange={event=>updateOutput(index,{measurement_basis:event.target.value as "dry"|"wet"})}><option value="dry">Dry basis</option><option value="wet">Wet basis</option></select></td><td><div className="inline-field"><input aria-label="Harvest output quantity" type="number" min="0" step="any" value={row.quantity} onChange={event=>updateOutput(index,{quantity:event.target.value})}/><span>g</span></div></td><td><input value={row.location_code} placeholder="DRY-ROOM-1" onChange={event=>updateOutput(index,{location_code:event.target.value})}/><select value={row.status} onChange={event=>updateOutput(index,{status:event.target.value})}><option value="quarantine">QA quarantine</option><option value="hold">Hold</option><option value="available">Available</option><option value="released">Released</option></select></td><td><button className="secondary" type="button" onClick={()=>{setRows(current=>current.filter((_,rowIndex)=>rowIndex!==index));setPreview(null)}}>Remove</button></td></tr>)}</tbody></table></div>:null}
    {losses.length?<><h4>Measured loss / waste</h4><div className="table-wrap"><table><thead><tr><th>Basis</th><th>Quantity</th><th>Classification</th><th>Reason</th><th></th></tr></thead><tbody>{losses.map((row,index)=><tr key={index}><td><select value={row.measurement_basis} onChange={event=>updateLoss(index,{measurement_basis:event.target.value as "dry"|"wet"})}><option value="dry">Dry basis</option><option value="wet">Wet basis</option></select></td><td><div className="inline-field"><input type="number" min="0" step="any" value={row.quantity} onChange={event=>updateLoss(index,{quantity:event.target.value})}/><span>g</span></div></td><td><input value={row.loss_type} onChange={event=>updateLoss(index,{loss_type:event.target.value})}/></td><td><input value={row.reason} onChange={event=>updateLoss(index,{reason:event.target.value})}/></td><td><button className="secondary" type="button" onClick={()=>{setLosses(current=>current.filter((_,rowIndex)=>rowIndex!==index));setPreview(null)}}>Remove</button></td></tr>)}</tbody></table></div></>:null}
    <div className="audit-actions"><button className="primary" type="button" disabled={!open||!payload().outputs.length||previewMutation.isPending} onClick={()=>previewMutation.mutate()}>{previewMutation.isPending?"Checking balance…":"Preview allocation"}</button>{preview?<button className="primary" type="button" disabled={preview.blocker_count>0||commitMutation.isPending} onClick={()=>commitMutation.mutate()}>{commitMutation.isPending?"Posting…":"Post exact allocation"}</button>:null}{preview?<button className="secondary" type="button" onClick={()=>setPreview(null)}>Cancel preview</button>:null}</div>
    {previewMutation.isError?<div className="form-error">{previewMutation.error.message}</div>:null}{commitMutation.isError?<div className="form-error">{commitMutation.error.message}</div>:null}{message?<div className="success-banner">{message}</div>:null}
    {preview?<div className={preview.blocker_count?"warning-banner":"info-banner"}><strong>Exact harvest allocation preview</strong>{(["dry","wet"] as const).map(basis=>{const row=preview.reconciliation[basis];return row?<div key={basis}><strong>{basis.toUpperCase()}:</strong> measured {num(row.measured)} g · already allocated {num(row.already_allocated)} g · this post {num(row.requested)} g · remaining {num(row.remaining)} g</div>:null})}{preview.warnings.map((row,index)=><div key={index}><strong>{row.severity.toUpperCase()}:</strong> {row.message}</div>)}</div>:null}
  </section>;
}

function emptyOutput(product:Product):OutputRow {return {product_id:product.id,lot_code:"",quantity:"",unit:"g",purpose:"finished_flower",measurement_basis:"dry",location_code:"HARVEST-OUTPUT",status:"quarantine",compliance_package_id:""}}
function num(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:4})}
function Metric({label,value}:{label:string;value:string|number}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}