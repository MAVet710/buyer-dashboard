import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import type { CultivationPlant } from "../types/inventory";
import type { CultivationIdentityResponse } from "./MetrcCultivationControls";

export type HarvestForMetrc = {
  id:string; harvest_code:string; status:string; plants:CultivationPlant[];
};

type Room = {id:string;room_code:string;display_name:string;active:boolean};
type Status = {ready:boolean;environment:string;license_number:string;promoted_actions:string[]};
type Preview = {
  ready:boolean;operation_type:string;summary:Record<string,unknown>;confirmation_id:string;confirmation_token:string;message:string;
  compliance_evidence:{method:string;path:string;license_number:string;environment:string;provider_request_body:unknown;provider_atomic:boolean};
};
type Result = {verified:boolean;status:string;transaction_id:string;external_reference:string;message:string;local_result?:unknown};
type Request = {
  operation_type:"harvest_start"|"harvest_waste"|"harvest_finish"|"harvest_unfinish";
  harvest_id:string;actual_date:string;plant_weights?:Array<{plant_id:string;wet_weight_g:number}>;drying_room_id?:string;
  waste_type?:string;waste_weight_g?:number;waste_method?:string;waste_reason?:string;waste_location?:string;
  measurement_basis?:"wet"|"dry";all_waste_reported?:boolean;reason:string;
};

export function useMetrcHarvestStatus(){
  return useQuery({queryKey:["metrc-harvest-status"],queryFn:({signal})=>apiGet<Status>("/api/v1/metrc-harvest/status",signal),retry:false,staleTime:30_000});
}

export function MetrcHarvestControls({harvest,canWrite,onChanged}:{harvest:HarvestForMetrc;canWrite:boolean;onChanged:()=>void|Promise<void>}){
  const client=useQueryClient();
  const identities=useQuery({queryKey:["metrc-cultivation-identities"],queryFn:({signal})=>apiGet<CultivationIdentityResponse>("/api/v1/metrc-cultivation/identities",signal),retry:false});
  const rooms=useQuery({queryKey:["cultivation-rooms"],queryFn:({signal})=>apiGet<{items:Room[]}>("/api/v1/inventory/production/plants/rooms",signal)});
  const harvestLink=(identities.data?.harvests??[]).find(row=>row.entity_id===harvest.id);
  const linkedRoomIds=new Set((identities.data?.rooms??[]).filter(row=>row.status==="verified").map(row=>row.entity_id));
  const linkedRooms=(rooms.data?.items??[]).filter(row=>row.active&&linkedRoomIds.has(row.id));
  const [active,setActive]=useState<"start"|"waste"|"finish"|"unfinish"|null>(null);
  const refresh=async()=>{await Promise.all([
    client.invalidateQueries({queryKey:["metrc-cultivation-identities"]}),
    client.invalidateQueries({queryKey:["cultivation-harvest",harvest.id]}),
    client.invalidateQueries({queryKey:["cultivation-harvests"]}),
    client.invalidateQueries({queryKey:["post-harvest-batches"]}),
    client.invalidateQueries({queryKey:["plants"]}),
    client.invalidateQueries({queryKey:["plants-overview"]}),
  ]);await onChanged()};
  if(!canWrite)return null;
  return <section className="inventory-panel">
    <div className="section-heading"><div><div className="eyebrow">METRC CHECKPOINT</div><h3>Regulated harvest actions</h3><p className="source-caption">DoobieLogic submits the provider action, verifies fresh Metrc state, then commits Harvest 360/Post-Harvest locally.</p></div>{harvestLink?<span className="badge">Metrc {harvestLink.provider_id}</span>:null}</div>
    {harvest.status==="planned"?<button className="primary" onClick={()=>setActive("start")}>Start harvest in Metrc</button>:null}
    {harvestLink&&["active","drying"].includes(harvest.status)?<div className="audit-actions"><button className="secondary" onClick={()=>setActive("waste")}>Record harvest waste</button><button className="primary" onClick={()=>setActive("finish")}>Finish harvest</button></div>:null}
    {harvestLink&&harvest.status==="completed"?<button className="primary" onClick={()=>setActive("unfinish")}>Reopen harvest</button>:null}
    {!harvestLink&&harvest.status!=="planned"?<div className="warning-banner"><strong>This local harvest has no verified Metrc harvest identity.</strong><br/><span>Do not manually confirm provider success. Reconcile the existing state before continuing regulated harvest actions.</span></div>:null}
    {active==="start"?<StartHarvest harvest={harvest} linkedRooms={linkedRooms} onClose={()=>setActive(null)} onDone={refresh}/>:null}
    {active==="waste"?<WasteHarvest harvest={harvest} onClose={()=>setActive(null)} onDone={refresh}/>:null}
    {active==="finish"?<FinishHarvest harvest={harvest} onClose={()=>setActive(null)} onDone={refresh}/>:null}
    {active==="unfinish"?<SimpleHarvestAction harvest={harvest} operation="harvest_unfinish" title="Reopen harvest" onClose={()=>setActive(null)} onDone={refresh}/>:null}
  </section>;
}

function StartHarvest({harvest,linkedRooms,onClose,onDone}:{harvest:HarvestForMetrc;linkedRooms:Room[];onClose:()=>void;onDone:()=>void|Promise<void>}){
  const [roomId,setRoomId]=useState("");
  const [date,setDate]=useState(today());
  const [weights,setWeights]=useState<Record<string,string>>(()=>Object.fromEntries(harvest.plants.map(row=>[row.id,""])));
  const rows=useMemo(()=>harvest.plants.map(plant=>({plant,raw:weights[plant.id]??"",weight:Number(weights[plant.id]||0)})),[harvest.plants,weights]);
  const valid=Boolean(roomId)&&rows.length>0&&rows.every(row=>row.raw!==""&&Number.isFinite(row.weight)&&row.weight>=0);
  const request:Request={operation_type:"harvest_start",harvest_id:harvest.id,actual_date:date,drying_room_id:roomId,plant_weights:rows.map(row=>({plant_id:row.plant.id,wet_weight_g:row.weight})),reason:"Operator confirmed harvest wet weights and drying location"};
  return <ActionPanel request={request} disabled={!valid} onClose={onClose} onDone={onDone} beforeReview={<>
    <div className="form-grid two"><label>Harvest date<input type="date" value={date} onChange={e=>setDate(e.target.value)}/></label><label>Drying room<select value={roomId} onChange={e=>setRoomId(e.target.value)}><option value="">Choose linked room</option>{linkedRooms.map(room=><option key={room.id} value={room.id}>{room.display_name||room.room_code} · {room.room_code}</option>)}</select></label></div>
    <div className="table-wrap"><table><thead><tr><th>Plant</th><th>Strain</th><th>Wet weight (g)</th></tr></thead><tbody>{rows.map(({plant,raw})=><tr key={plant.id}><td><strong>{plant.plant_tag}</strong></td><td>{plant.strain_name}</td><td><input aria-label={`Wet weight ${plant.plant_tag}`} type="number" min="0" step="0.01" value={raw} onChange={e=>setWeights(current=>({...current,[plant.id]:e.target.value}))}/></td></tr>)}</tbody></table></div>
    <div className="warning-banner"><strong>Metrc does not make this multi-plant action atomic.</strong><br/><span>DoobieLogic verifies each plant against one harvest. If Metrc partly succeeds or becomes uncertain, execution stops and reconciliation is required; the local harvest is not blindly committed.</span></div>
    {!linkedRooms.length?<div className="warning-banner">Link a drying room to an exact Metrc Location before starting this harvest.</div>:null}
  </>}/>;
}

function WasteHarvest({harvest,onClose,onDone}:{harvest:HarvestForMetrc;onClose:()=>void;onDone:()=>void|Promise<void>}){
  const [form,setForm]=useState({waste_type:"",weight:"",method:"",reason:"",location:"",basis:"wet" as "wet"|"dry",date:today()});
  const weight=Number(form.weight||0);
  const valid=Boolean(form.waste_type.trim()&&form.weight!==""&&weight>0&&form.method.trim()&&form.reason.trim()&&form.location.trim());
  const request:Request={operation_type:"harvest_waste",harvest_id:harvest.id,actual_date:form.date,waste_type:form.waste_type.trim(),waste_weight_g:weight,waste_method:form.method.trim(),waste_reason:form.reason.trim(),waste_location:form.location.trim(),measurement_basis:form.basis,reason:form.reason.trim()||"Harvest waste"};
  return <ActionPanel request={request} disabled={!valid} onClose={onClose} onDone={onDone} beforeReview={<div className="form-grid two"><label>Waste type<input value={form.waste_type} onChange={e=>setForm({...form,waste_type:e.target.value})}/></label><label>Weight (g)<input type="number" min="0" step="0.01" value={form.weight} onChange={e=>setForm({...form,weight:e.target.value})}/></label><label>Measurement basis<select value={form.basis} onChange={e=>setForm({...form,basis:e.target.value as "wet"|"dry"})}><option value="wet">Wet</option><option value="dry">Dry</option></select></label><label>Waste date<input type="date" value={form.date} onChange={e=>setForm({...form,date:e.target.value})}/></label><label>Disposal method<input value={form.method} onChange={e=>setForm({...form,method:e.target.value})}/></label><label>Physical location<input value={form.location} onChange={e=>setForm({...form,location:e.target.value})}/></label><label className="span-2">Reason<input value={form.reason} onChange={e=>setForm({...form,reason:e.target.value})}/></label></div>}/>;
}

function FinishHarvest({harvest,onClose,onDone}:{harvest:HarvestForMetrc;onClose:()=>void;onDone:()=>void|Promise<void>}){
  const [confirmed,setConfirmed]=useState(false);
  const request:Request={operation_type:"harvest_finish",harvest_id:harvest.id,actual_date:today(),all_waste_reported:confirmed,reason:"Operator confirmed harvest closeout and all actual waste reporting"};
  return <ActionPanel request={request} disabled={!confirmed} onClose={onClose} onDone={onDone} beforeReview={<label className="checkbox-row"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> All actual harvest waste has been reported. Remaining balanced mass may be classified by the existing closeout rules.</label>}/>;
}

function SimpleHarvestAction({harvest,operation,title,onClose,onDone}:{harvest:HarvestForMetrc;operation:"harvest_unfinish";title:string;onClose:()=>void;onDone:()=>void|Promise<void>}){
  const request:Request={operation_type:operation,harvest_id:harvest.id,actual_date:today(),reason:`Operator confirmed ${title.toLowerCase()}`};
  return <ActionPanel request={request} disabled={false} onClose={onClose} onDone={onDone}/>;
}

function ActionPanel({request,disabled,onClose,onDone,beforeReview}:{request:Request;disabled:boolean;onClose:()=>void;onDone:()=>void|Promise<void>;beforeReview?:React.ReactNode}){
  const [reviewing,setReviewing]=useState(false);
  const preview=useQuery({queryKey:["metrc-harvest-preview",request],queryFn:()=>apiPost<Preview>("/api/v1/metrc-harvest/actions/preview",request),enabled:reviewing&&!disabled,retry:false});
  const execute=useMutation({mutationFn:()=>apiPost<Result>("/api/v1/metrc-harvest/actions/execute",{...request,confirmation_id:preview.data?.confirmation_id,confirmation_token:preview.data?.confirmation_token}),onSuccess:async row=>{if(row.verified)await onDone()}});
  const result=execute.data;
  return <div className="inventory-panel">
    {beforeReview}
    {!reviewing?<div className="audit-actions"><button className="primary" disabled={disabled} onClick={()=>setReviewing(true)}>Review Metrc change</button><button className="secondary" onClick={onClose}>Cancel</button></div>:null}
    {reviewing&&preview.isLoading?<div className="state">Checking current DoobieLogic and Metrc state…</div>:null}
    {reviewing&&preview.isError?<><div className="state error">{preview.error.message}</div><button className="secondary" onClick={()=>setReviewing(false)}>Edit values</button></>:null}
    {preview.data&&!result?<><div className="info-banner"><strong>Review before submitting.</strong><br/><span>{preview.data.message}</span></div><div className="detail-facts">{Object.entries(preview.data.summary).filter(([key])=>key!=="title").map(([key,value])=><div key={key}><span>{friendly(key)}</span><strong>{display(value)}</strong></div>)}</div><div className="audit-actions"><button className="primary" disabled={execute.isPending} onClick={()=>execute.mutate()}>{execute.isPending?"Submitting to Metrc…":"Confirm & submit to Metrc"}</button><button className="secondary" disabled={execute.isPending} onClick={()=>setReviewing(false)}>Edit values</button></div>{execute.isError?<div className="form-error">{execute.error.message}</div>:null}<details className="compliance-details"><summary>Compliance evidence details</summary><pre>{JSON.stringify(preview.data.compliance_evidence,null,2)}</pre></details></>:null}
    {result?<><div className={result.verified?"success-banner":"warning-banner"}><strong>{resultTitle(result)}</strong><br/><span>{result.message}</span><br/><small>Transaction {result.transaction_id}{result.external_reference?` · Metrc ${result.external_reference}`:""}</small></div><button className="secondary submit" onClick={onClose}>Done</button></>:null}
  </div>;
}

function today(){const value=new Date();const year=value.getFullYear();const month=String(value.getMonth()+1).padStart(2,"0");const day=String(value.getDate()).padStart(2,"0");return `${year}-${month}-${day}`}
function resultTitle(result:Result){if(result.verified)return "Verified";if(result.status==="rejected")return "Rejected by Metrc";if(result.status==="reconciliation_required")return "Reconciliation required";return friendly(result.status)||"Not verified"}
function friendly(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function display(value:unknown){if(value===null||value===undefined||value==="")return "—";if(typeof value==="boolean")return value?"Yes":"No";return String(value)}
