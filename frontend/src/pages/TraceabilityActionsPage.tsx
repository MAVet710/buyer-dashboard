import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type ActionSpec={operation_type:string;operator_label:string;entity_type:string;required_fields:string[];roles:string[];verification_resource:string;supports_bulk:boolean};
type Catalog={actions:ActionSpec[];execution_boundary:string};
type QueueResult={id:string;provider:string;operation_type:string;entity_type:string;entity_id:string;status:string;idempotency_key:string;provider_execution:string};
type PreviewResult={ready:boolean;preview_token:string;summary:{title:string;entity:{type:string;id:string};affected_count:number;environment:string;license_number:string;verification:string};blockers:{code:string;message:string}[];revalidate_on_execute:boolean};
type TraceabilityPrefill={operation_type?:string;entity_id?:string;reason?:string;fields?:Record<string,string>};
type LedgerException={id:string;entity_type:string;entity_id:string;operation:string;machine_status:string;latest_error:string;error_classification:string;retry_eligible:boolean;requested_at:string;provider_tag:string;provider_reference:string};
type ExceptionResult={healthy:boolean;count:number;exceptions:LedgerException[]};

const PREFILL_KEY="buyer-dash-traceability-prefill";

export function TraceabilityActionsPage({onNavigate}:{onNavigate:(page:string)=>void}){
  const catalog=useQuery({queryKey:["traceability-action-catalog"],queryFn:({signal})=>apiGet<Catalog>("/api/v1/traceability-actions/catalog",signal)});
  const [prefill]=useState<TraceabilityPrefill>(()=>readPrefill());
  const [prefillApplied,setPrefillApplied]=useState(false);
  const [operation,setOperation]=useState("");
  const selected=useMemo(()=>catalog.data?.actions.find(row=>row.operation_type===operation)??catalog.data?.actions[0],[catalog.data,operation]);
  const [provider,setProvider]=useState("metrc"),[jurisdiction,setJurisdiction]=useState(""),[environment,setEnvironment]=useState(""),[entityId,setEntityId]=useState(""),[license,setLicense]=useState(""),[reason,setReason]=useState(""),[fields,setFields]=useState<Record<string,string>>({});
  const [idempotencyKey,setIdempotencyKey]=useState("");

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
  const intent=(key:string,previewToken="")=>({provider,jurisdiction,environment,operation_type:selected?.operation_type,entity_id:entityId,license_number:license,payload:payload(),reason,idempotency_key:key,client_action_id:key,queue_source:"web",preview_token:previewToken});
  const preview=useMutation({mutationFn:(key:string)=>apiPost<PreviewResult>("/api/v1/traceability-actions/preview",intent(key)),onSuccess:(_result,key)=>setIdempotencyKey(key)});
  const queue=useMutation({mutationFn:()=>apiPost<QueueResult>("/api/v1/traceability-actions/queue",intent(idempotencyKey,preview.data?.preview_token??""))});
  const review=()=>preview.mutate(`ui:${selected?.operation_type}:${entityId}:${Date.now()}`);
  return <div className="page traceability-actions"><div className="page-heading"><div><div className="eyebrow">TRACEABILITY · TYPED ACTIONS</div><h1>Queue the operational intent once.</h1><p>DoobieLogic validates the action and records it in the durable provider-neutral queue. A queued action is never presented as accepted by Metrc or BioTrack until the provider actually confirms it.</p></div><div className="heading-actions"><button className="secondary" onClick={()=>onNavigate("Compliance")}>Reconciliation queue</button><button className="secondary" onClick={()=>onNavigate("Package 360")}>Package 360</button></div></div>
    <ExceptionCenter onNavigate={onNavigate}/>
    {catalog.isLoading?<div className="state">Loading role-authorized traceability actions…</div>:null}{catalog.isError?<div className="warning-banner">{catalog.error.message}</div>:null}
    {prefillApplied&&prefill.operation_type?<div className="info-banner"><strong>Inventory action loaded.</strong> Review the prefilled package/action details, complete any required fields, then validate and queue it.</div>:null}
    {catalog.data?<><div className="info-banner">{catalog.data.execution_boundary}</div>{!catalog.data.actions.length?<div className="warning-banner">Your role has no typed state-system actions available.</div>:<section className="inventory-panel"><div className="form-grid three"><label>Action<select value={selected?.operation_type??""} onChange={e=>{setOperation(e.target.value);setFields({});preview.reset();queue.reset()}}>{catalog.data.actions.map(row=><option value={row.operation_type} key={row.operation_type}>{row.operator_label||title(row.operation_type)} · {title(row.entity_type)}</option>)}</select></label><label>Provider<select value={provider} onChange={e=>setProvider(e.target.value)}><option value="metrc">Metrc</option><option value="biotrack">BioTrack</option><option value="other">Other regulated system</option></select></label><label>Entity identifier<input value={entityId} placeholder={selected?.entity_type||"entity"} onChange={e=>setEntityId(e.target.value)}/></label><label>Jurisdiction<input value={jurisdiction} placeholder="State code, e.g. MA" maxLength={16} onChange={e=>setJurisdiction(e.target.value.toUpperCase())}/></label><label>Environment<select value={environment} onChange={e=>setEnvironment(e.target.value)}><option value="">Choose exact environment</option><option value="sandbox">Sandbox</option><option value="production">Production</option></select></label><label>License number<input value={license} onChange={e=>setLicense(e.target.value)}/></label>{selected?.required_fields.map(field=><label key={field}>{title(field)}<input value={fields[field]??""} placeholder={field.endsWith("_ids")||field==="source_ids"?"comma-separated IDs":"required"} onChange={e=>setFields({...fields,[field]:e.target.value})}/></label>)}<label className="full">Reason<textarea value={reason} placeholder="Operational reason and source context" onChange={e=>setReason(e.target.value)}/></label></div><button className="primary" disabled={!entityId.trim()||provider!=="other"&&(!jurisdiction.trim()||!environment||!license.trim())||reason.trim().length<3||preview.isPending||!complete(selected,fields)} onClick={review}>{preview.isPending?"Checking…":"Review action"}</button>{preview.isError?<div className="form-error">{preview.error.message}</div>:null}{preview.data?<div className={preview.data.ready?"success-banner":"warning-banner"}><strong>{preview.data.summary.title}</strong><br/>{preview.data.summary.affected_count} {title(preview.data.summary.entity.type)} record(s) · {preview.data.summary.license_number} · {title(preview.data.summary.environment)}{preview.data.blockers.map(row=><p key={row.code}>{row.message}</p>)}{preview.data.ready?<div className="audit-actions"><button className="primary" disabled={queue.isPending} onClick={()=>queue.mutate()}>{queue.isPending?"Queuing…":"Confirm & queue"}</button></div>:null}</div>:null}{queue.isError?<div className="form-error">{queue.error.message}</div>:null}{queue.data?<div className="success-banner"><strong>{title(queue.data.operation_type)} queued.</strong><br/>Status: {title(queue.data.status)} · Provider execution: {title(queue.data.provider_execution)} · Transaction {queue.data.id}</div>:null}</section>}</>:null}
  </div>;
}

function ExceptionCenter({onNavigate}:{onNavigate:(page:string)=>void}){
  const client=useQueryClient();
  const query=useQuery({queryKey:["traceability-exceptions"],queryFn:({signal})=>apiGet<ExceptionResult>("/api/v1/traceability-actions/ledger/exceptions?limit=50",signal)});
  const [working,setWorking]=useState("");
  const retry=useMutation({mutationFn:(id:string)=>apiPost(`/api/v1/traceability-actions/ledger/${id}/retry`,{note:"Operator reviewed exception and prepared a safe retry."}),onSuccess:async()=>{setWorking("");await client.invalidateQueries({queryKey:["traceability-exceptions"]})}});
  const resolve=useMutation({mutationFn:(id:string)=>apiPost(`/api/v1/traceability-actions/ledger/${id}/resolve`,{note:"Operator reviewed provider evidence and resolved this exception."}),onSuccess:async()=>{setWorking("");await client.invalidateQueries({queryKey:["traceability-exceptions"]})}});
  if(query.isLoading)return <section className="inventory-panel"><div className="state">Checking Metrc synchronization health…</div></section>;
  if(query.isError)return <section className="inventory-panel"><div className="warning-banner">Synchronization health could not load: {query.error.message}</div></section>;
  if(query.data?.healthy)return <section className="inventory-panel"><div className="eyebrow">METRC SYNC</div><h2>Metrc Sync Healthy</h2><p className="source-caption">No unresolved provider exceptions require attention in this facility.</p></section>;
  return <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">METRC SYNC</div><h2>{query.data?.count??0} issue(s) require attention</h2><p className="source-caption">Review the operational meaning, then take the safe next action.</p></div></div>
    {query.data?.exceptions.map(row=><article className="commercial-order-card" key={row.id}><div><strong>{title(row.error_classification||row.operation)}</strong><span className="status-pill">{title(row.machine_status)}</span></div><p><strong>{title(row.entity_type)}:</strong> {row.entity_id}{row.provider_tag?` · Tag ${row.provider_tag}`:""}</p><p>{exceptionMeaning(row)}</p><small>Last attempt {new Date(row.requested_at).toLocaleString()}</small><div className="audit-actions">{row.retry_eligible?<button className="primary" disabled={retry.isPending} onClick={()=>{setWorking(row.id);retry.mutate(row.id)}}>{working===row.id&&retry.isPending?"Preparing…":"Prepare safe retry"}</button>:null}<button className="secondary" onClick={()=>openEntity(row,onNavigate)}>Open {title(row.entity_type)} 360</button><button className="secondary" disabled={resolve.isPending} onClick={()=>{setWorking(row.id);resolve.mutate(row.id)}}>Mark reviewed</button></div></article>)}
    {retry.isError?<div className="form-error">{retry.error.message}</div>:null}{resolve.isError?<div className="form-error">{resolve.error.message}</div>:null}
  </section>;
}

function exceptionMeaning(row:LedgerException){if(row.error_classification==="rate_limited")return "Metrc temporarily limited requests. The same action can be retried after the wait period.";if(row.error_classification==="authentication_configuration_failure")return "The facility license mapping or Metrc credential needs attention before this can sync.";if(row.error_classification==="provider_validation_rejection")return `Metrc rejected the mapped record. ${row.latest_error}`;return row.latest_error||"DoobieLogic and the synchronized Metrc state require review."}
function openEntity(row:LedgerException,onNavigate:(page:string)=>void){const page=row.entity_type==="plant"?"Plant Inventory":row.entity_type==="harvest"?"Cultivation":row.entity_type==="production_order"?"Production Run 360":row.entity_type==="product"?"Retail Product 360":"Package 360";onNavigate(page)}
function readPrefill():TraceabilityPrefill{try{return JSON.parse(sessionStorage.getItem(PREFILL_KEY)||"{}") as TraceabilityPrefill}catch{return {}}}
function complete(spec:ActionSpec|undefined,fields:Record<string,string>){return Boolean(spec&&spec.required_fields.every(field=>(fields[field]??"").trim()))}
function parseField(field:string,value:string):unknown{const clean=value.trim();if(field.endsWith("_ids")||field==="source_ids"||field==="package_ids"||field==="plant_ids"||field==="input_package_ids"||field==="output_package_ids")return clean.split(",").map(item=>item.trim()).filter(Boolean);if(["quantity","quantity_delta"].includes(field)){const numeric=Number(clean);return Number.isFinite(numeric)?numeric:clean}return clean}
function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
