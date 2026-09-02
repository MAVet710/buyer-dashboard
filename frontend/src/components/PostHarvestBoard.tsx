import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import { StreamlitDialog } from "./StreamlitDialog";

const stages = ["harvested", "drying", "bucking", "trimming", "curing", "testing_hold", "ready"] as const;
type Stage = typeof stages[number];
type WeightType = "wip" | "finished_flower" | "trim" | "biomass" | "waste";
type CurrentWeights = Record<WeightType, number>;

type PostHarvestBatch = {
  id:string; harvest_id:string; harvest_code:string; strain_name:string; source_room:string; harvest_status:string;
  stage:Stage; location_code:string; notes:string; started_at:string|null; completed_at:string|null;
  wet_weight_g:number; dry_weight_g:number; starting_weight_g:number; current_weights:CurrentWeights;
  accounted_output_g:number; remaining_wip_g:number; weight_event_count:number; needs_attention:boolean; attention_reason:string;
};
type WeightHistory = {id:string;stage:string;weight_type:WeightType;quantity_g:number;container_code:string;note:string;correction_reason:string;actor:string;occurred_at:string};
type AuditHistory = {id:string;event_type:string;from_value:string;to_value:string;note:string;actor:string;occurred_at:string};
type PostHarvestDetail = PostHarvestBatch & { weight_history:WeightHistory[]; audit_history:AuditHistory[] };
type Props = { canWrite:boolean; onOpenHarvest:(harvestId:string)=>void };

const managerRoles = new Set(["dev", "admin", "supervisor", "qa"]);
const filters:Array<[string,string]> = [
  ["attention","Needs Attention"],
  ["harvested","Harvested"],
  ["drying","Drying"],
  ["bucking","Ready for Trim"],
  ["trimming","Trimming"],
  ["curing","Curing"],
  ["testing_hold","Testing / Hold"],
  ["ready","Ready"],
  ["all","All"],
];

export function PostHarvestBoard({canWrite,onOpenHarvest}:Props) {
  const client=useQueryClient();
  const account=useQuery({queryKey:["account-context"],queryFn:({signal})=>apiGet<{user:{role:string}}>("/api/v1/account/context",signal)});
  const role=account.data?.user.role??"";
  const canManage=managerRoles.has(role);
  const query=useQuery({queryKey:["post-harvest"],queryFn:({signal})=>apiGet<{items:PostHarvestBatch[]}>("/api/v1/inventory/production/plants/post-harvest",signal)});
  const syncStarted=useRef(false);
  const sync=useMutation({
    mutationFn:()=>apiPost<{items:PostHarvestBatch[]}>("/api/v1/inventory/production/plants/post-harvest/sync",{}),
    onSuccess:data=>client.setQueryData(["post-harvest"],data),
  });
  useEffect(()=>{
    if(!canWrite||syncStarted.current)return;
    syncStarted.current=true;
    sync.mutate();
  },[canWrite]);
  const [filter,setFilter]=useState("attention");
  const [weightBatchId,setWeightBatchId]=useState("");
  const [advanceBatchId,setAdvanceBatchId]=useState("");
  const items=query.data?.items??[];
  const visible=useMemo(()=>items.filter(row=>filter==="all"?true:filter==="attention"?row.needs_attention:row.stage===filter),[items,filter]);
  const count=(stage:string)=>stage==="attention"?items.filter(row=>row.needs_attention).length:items.filter(row=>row.stage===stage).length;

  return <section className="inventory-panel post-harvest-board">
    <div className="section-heading"><div><div className="eyebrow">CULTIVATION · POST-HARVEST</div><h3>Post-Harvest</h3><p className="source-caption">The operator sees the next physical job. DoobieLogic keeps the harvest source, stages, weight history, actor, timestamps and reconciliation underneath. Recording a weight never overwrites a prior reading and never creates a Metrc mutation.</p></div></div>
    <div className="metrics four"><Metric label="Needs attention" value={count("attention")}/><Metric label="Drying" value={count("drying")}/><Metric label="Trimming" value={count("trimming")}/><Metric label="Ready" value={count("ready")}/></div>
    <div className="audit-actions post-harvest-filters">{filters.map(([value,label])=><button key={value} type="button" className={filter===value?"primary":"secondary"} onClick={()=>setFilter(value)}>{label}{value!=="all"?` · ${count(value)}`:""}</button>)}</div>
    {query.isLoading?<div className="state">Loading post-harvest work…</div>:null}
    {query.isError?<div className="state error">{query.error.message}</div>:null}
    {sync.isError?<div className="warning-banner">Open harvests could not be synchronized into Post-Harvest: {sync.error.message}</div>:null}
    {visible.length?<div className="two-col post-harvest-cards">{visible.map(batch=><article className="inventory-panel" key={batch.id}>
      <div className="section-heading"><div><div className="eyebrow">{stageLabel(batch.stage).toUpperCase()}</div><h4>{batch.harvest_code}</h4><p className="source-caption">{batch.strain_name||"Unknown strain"} · {batch.location_code||batch.source_room||"Location not assigned"}</p></div><span className="badge">{stageLabel(batch.stage)}</span></div>
      {batch.needs_attention?<div className="warning-banner"><strong>Needs attention:</strong> {batch.attention_reason}</div>:null}
      <div className="metrics"><Metric label="Flower" value={`${num(batch.current_weights.finished_flower)} g`}/><Metric label="Trim" value={`${num(batch.current_weights.trim)} g`}/><Metric label="Remaining / WIP" value={`${num(batch.remaining_wip_g)} g`}/></div>
      <p className="source-caption">Wet {num(batch.wet_weight_g)} g · Dry {num(batch.dry_weight_g)} g · {batch.weight_event_count} recorded weight event{batch.weight_event_count===1?"":"s"}</p>
      <div className="audit-actions">
        {canWrite&&batch.stage!=="ready"?<button className="primary" type="button" onClick={()=>setWeightBatchId(batch.id)}>Update weights</button>:null}
        {canWrite&&batch.stage==="ready"&&canManage?<button className="secondary" type="button" onClick={()=>setWeightBatchId(batch.id)}>Correct locked weights</button>:null}
        {canWrite&&nextStage(batch.stage)?<button className="secondary" type="button" onClick={()=>setAdvanceBatchId(batch.id)}>Advance stage</button>:null}
        <button className="secondary" type="button" onClick={()=>onOpenHarvest(batch.harvest_id)}>Open Harvest 360</button>
      </div>
    </article>)}</div>:query.data?<div className="empty">No post-harvest jobs match this view.</div>:null}
    {weightBatchId?<WeightDialog batchId={weightBatchId} canManage={canManage} onClose={()=>setWeightBatchId("")} onSaved={async()=>{setWeightBatchId("");await client.invalidateQueries({queryKey:["post-harvest"]})}}/>:null}
    {advanceBatchId?<AdvanceDialog batchId={advanceBatchId} onClose={()=>setAdvanceBatchId("")} onSaved={async()=>{setAdvanceBatchId("");await client.invalidateQueries({queryKey:["post-harvest"]})}}/>:null}
  </section>;
}

function WeightDialog({batchId,canManage,onClose,onSaved}:{batchId:string;canManage:boolean;onClose:()=>void;onSaved:()=>void|Promise<void>}) {
  const query=useQuery({queryKey:["post-harvest-detail",batchId],queryFn:({signal})=>apiGet<PostHarvestDetail>(`/api/v1/inventory/production/plants/post-harvest/${batchId}`,signal)});
  if(query.isLoading)return <StreamlitDialog open onClose={onClose} eyebrow="Post-Harvest" title="Update weights" subtitle="Loading current physical weights…"><div className="state">Loading…</div></StreamlitDialog>;
  if(query.isError||!query.data)return <StreamlitDialog open onClose={onClose} eyebrow="Post-Harvest" title="Update weights"><div className="state error">{query.error?.message||"Post-harvest job could not be loaded."}</div></StreamlitDialog>;
  return <WeightForm key={`${query.data.id}-${query.data.weight_event_count}`} batch={query.data} canManage={canManage} onClose={onClose} onSaved={onSaved}/>;
}

function WeightForm({batch,canManage,onClose,onSaved}:{batch:PostHarvestDetail;canManage:boolean;onClose:()=>void;onSaved:()=>void|Promise<void>}) {
  const [form,setForm]=useState<Record<WeightType,string>>({
    wip:String(batch.current_weights.wip||batch.remaining_wip_g||0),
    finished_flower:String(batch.current_weights.finished_flower||0),
    trim:String(batch.current_weights.trim||0),
    biomass:String(batch.current_weights.biomass||0),
    waste:String(batch.current_weights.waste||0),
  });
  const [containerCode,setContainerCode]=useState("");
  const [note,setNote]=useState("");
  const [correctionReason,setCorrectionReason]=useState("");
  const locked=batch.stage==="ready";
  const changed=(Object.keys(form) as WeightType[]).filter(kind=>Number(form[kind]||0)!==Number(batch.current_weights[kind]||0) && !(kind==="wip"&&Number(form[kind]||0)===Number(batch.remaining_wip_g||0)&&Number(batch.current_weights.wip||0)===0));
  const mutation=useMutation({
    mutationFn:()=>apiPost<PostHarvestDetail>(`/api/v1/inventory/production/plants/post-harvest/${batch.id}/weights`,{
      measurements:changed.map(weight_type=>({weight_type,quantity_g:Number(form[weight_type]||0),container_code:containerCode.trim(),note:note.trim()})),
      correction_reason:correctionReason.trim(),
    }),
    onSuccess:onSaved,
  });
  return <StreamlitDialog open onClose={onClose} eyebrow={`POST-HARVEST · ${stageLabel(batch.stage).toUpperCase()}`} title={`${batch.harvest_code} · Update weights`} subtitle="Enter what the scale says. DoobieLogic appends the reading and keeps every prior value underneath.">
    <div className="info-banner"><strong>{batch.strain_name}</strong> · Wet {num(batch.wet_weight_g)} g · Dry {num(batch.dry_weight_g)} g<br/><span>Current remaining/WIP: {num(batch.remaining_wip_g)} g</span></div>
    {locked?<div className="warning-banner"><strong>This batch is locked.</strong> Only a supervisor/QA/admin can append a correction, and a reason is required. Historical readings are never edited.</div>:null}
    <div className="form-grid two">
      <WeightField label="Remaining / WIP (g)" value={form.wip} onChange={value=>setForm({...form,wip:value})}/>
      <WeightField label="Finished flower (g)" value={form.finished_flower} onChange={value=>setForm({...form,finished_flower:value})}/>
      <WeightField label="Trim (g)" value={form.trim} onChange={value=>setForm({...form,trim:value})}/>
      <WeightField label="Biomass (g)" value={form.biomass} onChange={value=>setForm({...form,biomass:value})}/>
      <WeightField label="Waste (g)" value={form.waste} onChange={value=>setForm({...form,waste:value})}/>
      <label>Container / bin<input value={containerCode} onChange={event=>setContainerCode(event.target.value)} placeholder="BIN-12 / TOTE-3 (optional)"/></label>
      <label className="span-2">Shift note<input value={note} onChange={event=>setNote(event.target.value)} placeholder="Optional physical-work note"/></label>
      {locked?<label className="span-2">Correction reason<input value={correctionReason} onChange={event=>setCorrectionReason(event.target.value)} placeholder="Required for a locked batch"/></label>:null}
    </div>
    <div className="audit-actions"><button className="primary" type="button" disabled={mutation.isPending||!changed.length||(locked&&(!canManage||!correctionReason.trim()))} onClick={()=>mutation.mutate()}>{mutation.isPending?"Saving…":locked?"Append governed correction":"Save weight update"}</button><button className="secondary" type="button" onClick={onClose}>Cancel</button></div>
    {mutation.isError?<div className="form-error">{mutation.error.message}</div>:null}
    <details><summary>Audit history</summary><div className="table-wrap"><table><thead><tr><th>When</th><th>Stage</th><th>Weight</th><th>Actor</th><th>Note</th></tr></thead><tbody>{batch.weight_history.slice(0,20).map(row=><tr key={row.id}><td>{dateTime(row.occurred_at)}</td><td>{stageLabel(row.stage as Stage)}</td><td>{weightLabel(row.weight_type)} · {num(row.quantity_g)} g</td><td>{row.actor}</td><td>{row.correction_reason?`Correction: ${row.correction_reason}`:row.note||"—"}</td></tr>)}</tbody></table>{!batch.weight_history.length?<div className="empty">No weight history yet.</div>:null}</div></details>
  </StreamlitDialog>;
}

function AdvanceDialog({batchId,onClose,onSaved}:{batchId:string;onClose:()=>void;onSaved:()=>void|Promise<void>}) {
  const query=useQuery({queryKey:["post-harvest-detail",batchId],queryFn:({signal})=>apiGet<PostHarvestDetail>(`/api/v1/inventory/production/plants/post-harvest/${batchId}`,signal)});
  const batch=query.data;
  const target=batch?nextStage(batch.stage):null;
  const [location,setLocation]=useState("");
  const [notes,setNotes]=useState("");
  useEffect(()=>{if(batch)setLocation(batch.location_code||"")},[batch?.id]);
  const mutation=useMutation({mutationFn:()=>apiPost<PostHarvestDetail>(`/api/v1/inventory/production/plants/post-harvest/${batchId}/transition`,{stage:target,location_code:location.trim(),notes:notes.trim()}),onSuccess:onSaved});
  return <StreamlitDialog open onClose={onClose} eyebrow="Post-Harvest" title={batch&&target?`${batch.harvest_code} · ${stageLabel(target)}`:"Advance post-harvest"} subtitle={batch&&target?`Move this physical work from ${stageLabel(batch.stage)} to ${stageLabel(target)}.`:"Loading stage…"}>
    {query.isLoading?<div className="state">Loading…</div>:null}{query.isError?<div className="state error">{query.error.message}</div>:null}
    {batch&&target?<><div className="form-grid"><label>Current location / room<input value={location} onChange={event=>setLocation(event.target.value)} placeholder="DRY-2 / TRIM-1 / CURE-A"/></label><label>Handoff note<input value={notes} onChange={event=>setNotes(event.target.value)} placeholder="Optional note for the next team"/></label></div><div className="info-banner">This advances the operational post-harvest stage only. It does not create inventory or submit a Metrc action.</div><div className="audit-actions"><button className="primary" type="button" disabled={mutation.isPending} onClick={()=>mutation.mutate()}>{mutation.isPending?"Moving…":`Move to ${stageLabel(target)}`}</button><button className="secondary" type="button" onClick={onClose}>Cancel</button></div>{mutation.isError?<div className="form-error">{mutation.error.message}</div>:null}</>:null}
  </StreamlitDialog>;
}

function WeightField({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}) {return <label>{label}<input type="number" min="0" step="any" value={value} onChange={event=>onChange(event.target.value)}/></label>}
function Metric({label,value}:{label:string;value:string|number}) {return <article className="metric"><span>{label}</span><strong>{typeof value==="number"?value.toLocaleString():value}</strong></article>}
function nextStage(stage:Stage):Stage|null {const index=stages.indexOf(stage);return index>=0&&index<stages.length-1?stages[index+1]:null}
function stageLabel(stage:Stage|string){return ({harvested:"Harvested",drying:"Drying",bucking:"Ready for Trim / Bucking",trimming:"Trimming",curing:"Curing",testing_hold:"Testing / Hold",ready:"Ready"} as Record<string,string>)[stage]??stage.replaceAll("_"," ")}
function weightLabel(kind:WeightType){return ({wip:"WIP",finished_flower:"Flower",trim:"Trim",biomass:"Biomass",waste:"Waste"} as Record<WeightType,string>)[kind]}
function num(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:2})}
function dateTime(value:string){const parsed=new Date(value);return Number.isNaN(parsed.getTime())?value:parsed.toLocaleString()}
