import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type ActionSpec={operation_type:string;entity_type:string;required_fields:string[];roles:string[]};
type Catalog={actions:ActionSpec[];execution_boundary:string};
type QueueResult={id:string;provider:string;operation_type:string;entity_type:string;entity_id:string;status:string;idempotency_key:string;provider_execution:string};
type TraceabilityPrefill={operation_type?:string;entity_id?:string;reason?:string;fields?:Record<string,string>};

const PREFILL_KEY="buyer-dash-traceability-prefill";

export function TraceabilityActionsPage({onNavigate}:{onNavigate:(page:string)=>void}){
  const catalog=useQuery({queryKey:["traceability-action-catalog"],queryFn:({signal})=>apiGet<Catalog>("/api/v1/traceability-actions/catalog",signal)});
  const [prefill]=useState<TraceabilityPrefill>(()=>readPrefill());
  const [prefillApplied,setPrefillApplied]=useState(false);
  const [operation,setOperation]=useState("");
  const selected=useMemo(()=>catalog.data?.actions.find(row=>row.operation_type===operation)??catalog.data?.actions[0],[catalog.data,operation]);
  const [provider,setProvider]=useState("metrc"),[entityId,setEntityId]=useState(""),[license,setLicense]=useState(""),[reason,setReason]=useState(""),[fields,setFields]=useState<Record<string,string>>({});

  useEffect(()=>{
    if(prefillApplied||!catalog.data?.actions.length)return;
    const requested=prefill.operation_type&&catalog.data.actions.some(row=>row.operation_type===prefill.operation_type)?prefill.operation_type:catalog.data.actions[0].operation_type;
    setOperation(requested);
    if(prefill.entity_id)setEntityId(prefill.entity_id);
    if(prefill.reason)setReason(prefill.reason);
    if(prefill.fields)setFields(prefill.fields);
    setPrefillApplied(true);
    sessionStorage.removeItem(PREFILL_KEY);
  },[catalog.data,prefill,prefillApplied]);

  useEffect(()=>{if(prefillApplied||operation||!catalog.data?.actions[0])return;setOperation(catalog.data.actions[0].operation_type)},[catalog.data,operation,prefillApplied]);
  const payload=()=>Object.fromEntries((selected?.required_fields??[]).map(field=>[field,parseField(field,fields[field]??"")]));
  const queue=useMutation({mutationFn:()=>apiPost<QueueResult>("/api/v1/traceability-actions/queue",{provider,operation_type:selected?.operation_type,entity_id:entityId,license_number:license,payload:payload(),reason,idempotency_key:`ui:${selected?.operation_type}:${entityId}:${Date.now()}`})});
  return <div className="page traceability-actions"><div className="page-heading"><div><div className="eyebrow">TRACEABILITY · TYPED ACTIONS</div><h1>Queue the operational intent once.</h1><p>DoobieLogic validates the action and records it in the durable provider-neutral queue. A queued action is never presented as accepted by Metrc or BioTrack until the provider actually confirms it.</p></div><div className="heading-actions"><button className="secondary" onClick={()=>onNavigate("Compliance")}>Reconciliation queue</button><button className="secondary" onClick={()=>onNavigate("Package 360")}>Package 360</button></div></div>
    {catalog.isLoading?<div className="state">Loading role-authorized traceability actions…</div>:null}{catalog.isError?<div className="warning-banner">{catalog.error.message}</div>:null}
    {prefillApplied&&prefill.operation_type?<div className="info-banner"><strong>Inventory action loaded.</strong> Review the prefilled package/action details, complete any required fields, then validate and queue it.</div>:null}
    {catalog.data?<><div className="info-banner">{catalog.data.execution_boundary}</div>{!catalog.data.actions.length?<div className="warning-banner">Your role has no typed state-system actions available.</div>:<section className="inventory-panel"><div className="form-grid three"><label>Action<select value={selected?.operation_type??""} onChange={e=>{setOperation(e.target.value);setFields({});queue.reset()}}>{catalog.data.actions.map(row=><option value={row.operation_type} key={row.operation_type}>{title(row.operation_type)} · {title(row.entity_type)}</option>)}</select></label><label>Provider<select value={provider} onChange={e=>setProvider(e.target.value)}><option value="metrc">Metrc</option><option value="biotrack">BioTrack</option><option value="other">Other regulated system</option></select></label><label>Entity identifier<input value={entityId} placeholder={selected?.entity_type||"entity"} onChange={e=>setEntityId(e.target.value)}/></label><label>License number<input value={license} onChange={e=>setLicense(e.target.value)}/></label>{selected?.required_fields.map(field=><label key={field}>{title(field)}<input value={fields[field]??""} placeholder={field.endsWith("_ids")||field==="source_ids"?"comma-separated IDs":"required"} onChange={e=>setFields({...fields,[field]:e.target.value})}/></label>)}<label className="full">Reason<textarea value={reason} placeholder="Operational reason and source context" onChange={e=>setReason(e.target.value)}/></label></div><button className="primary" disabled={!entityId.trim()||reason.trim().length<3||queue.isPending||!complete(selected,fields)} onClick={()=>queue.mutate()}>{queue.isPending?"Validating…":"Validate & queue"}</button>{queue.isError?<div className="form-error">{queue.error.message}</div>:null}{queue.data?<div className="success-banner"><strong>{title(queue.data.operation_type)} queued.</strong><br/>Status: {title(queue.data.status)} · Provider execution: {title(queue.data.provider_execution)} · Transaction {queue.data.id}</div>:null}</section>}</>:null}
  </div>;
}
function readPrefill():TraceabilityPrefill{try{return JSON.parse(sessionStorage.getItem(PREFILL_KEY)||"{}") as TraceabilityPrefill}catch{return {}}}
function complete(spec:ActionSpec|undefined,fields:Record<string,string>){return Boolean(spec&&spec.required_fields.every(field=>(fields[field]??"").trim()))}
function parseField(field:string,value:string):unknown{const clean=value.trim();if(field.endsWith("_ids")||field==="source_ids"||field==="package_ids"||field==="plant_ids"||field==="input_package_ids"||field==="output_package_ids")return clean.split(",").map(item=>item.trim()).filter(Boolean);if(["quantity","quantity_delta"].includes(field)){const numeric=Number(clean);return Number.isFinite(numeric)?numeric:clean}return clean}
function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
