import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RegulatoryIntelligencePanel } from "../components/RegulatoryIntelligencePanel";
import { StreamlitDialog } from "../components/StreamlitDialog";
import { apiGet, apiPost } from "../lib/api";

type Tx = {
  id:string; provider:string; license_number:string; operation_type:string; entity_type:string; entity_id:string;
  idempotency_key:string; status:string; request_payload_json:string; response_payload_json:string;
  external_reference:string; error_code:string; error_message:string; attempt_count:number; next_attempt_at:string|null;
  reason:string; requested_by:string; approved_by:string; requested_at:string; submitted_at:string|null; completed_at:string|null;
};
type Attempt = { id:string; attempt_number:number; http_status:number|null; error_code:string; error_message:string; started_at:string; completed_at:string|null };
type Event = { id:string; from_status:string; to_status:string; actor:string; reason:string; source:string; occurred_at:string };
type Queue = { summary:Record<string,number>; items:Tx[] };
type Detail = { transaction:Tx; events:Event[]; attempts:Attempt[] };
type Account = { user:{ role:string } };
type DetailTab = "Overview"|"Attempts"|"Lifecycle"|"Payloads";

const STATUS_OPTIONS:[string,string[]][] = [
  ["Needs reconciliation",["rejected","reconciliation_required"]],
  ["In flight",["requested","validated","queued","submitted","accepted"]],
  ["All",[]], ["Verified",["verified"]], ["Cancelled",["cancelled"]],
];
const PROVIDERS = ["All","METRC","BioTrack","Other"];
const MANAGE_ROLES = new Set(["dev","admin","supervisor","qa"]);

export function CompliancePage() {
  const client=useQueryClient();
  const [queueView,setQueueView]=useState("Needs reconciliation"); const [provider,setProvider]=useState("All");
  const [selected,setSelected]=useState(""); const [tab,setTab]=useState<DetailTab>("Overview");
  const [reason,setReason]=useState(""); const [confirmed,setConfirmed]=useState(false); const [message,setMessage]=useState("");
  const statuses=STATUS_OPTIONS.find(([label])=>label===queueView)?.[1]??[];
  const query=new URLSearchParams(); statuses.forEach(value=>query.append("status",value)); if(provider!=="All")query.set("provider",provider.toLowerCase());
  const queue=useQuery({queryKey:["traceability",queueView,provider],queryFn:({signal})=>apiGet<Queue>(`/api/v1/compliance/traceability?${query}`,signal)});
  const detail=useQuery({queryKey:["traceability-detail",selected],enabled:Boolean(selected),queryFn:({signal})=>apiGet<Detail>(`/api/v1/compliance/traceability/${selected}`,signal)});
  const account=useQuery({queryKey:["account-context"],queryFn:({signal})=>apiGet<Account>("/api/v1/account/context",signal)});
  const resolve=useMutation({mutationFn:(action:string)=>apiPost<Tx>(`/api/v1/compliance/traceability/${selected}/resolve`,{action,reason,confirmed}),onSuccess:async(_row,action)=>{setMessage(action==="requeue"?"Transaction returned to the traceability queue.":action==="verify"?"Transaction marked verified with reconciliation evidence.":"Transaction cancelled with an audit reason.");setReason("");setConfirmed(false);await Promise.all([client.invalidateQueries({queryKey:["traceability"]}),client.invalidateQueries({queryKey:["traceability-detail",selected]})])}});
  const canManage=MANAGE_ROLES.has(account.data?.user.role?.toLowerCase()??"");
  return <div className="page exact-traceability">
    <div className="eyebrow">TRACEABILITY OPERATIONS · BACKOFFICE</div><h1>Queue &amp; Reconciliation</h1><p className="section-note">Buyer Dash keeps the internal operational record visible even when the state system rejects, delays, or conflicts with an action.</p>
    <RegulatoryIntelligencePanel/>
    <section className="metrics four"><Metric label="Needs reconciliation" value={queue.data?.summary.needs_reconciliation??"—"}/><Metric label="In flight" value={queue.data?.summary.in_flight??"—"}/><Metric label="Verified" value={queue.data?.summary.verified??"—"}/><Metric label="Total actions" value={queue.data?.summary.total??"—"}/></section>
    <div className="form-grid two traceability-filters"><label>Queue view<select value={queueView} onChange={event=>setQueueView(event.target.value)}>{STATUS_OPTIONS.map(([label])=><option key={label}>{label}</option>)}</select></label><label>Provider<select value={provider} onChange={event=>setProvider(event.target.value)}>{PROVIDERS.map(value=><option key={value}>{value}</option>)}</select></label></div>
    {queue.isError?<div className="warning-banner">Traceability Operations is unavailable: {queue.error.message}</div>:null}
    {queue.data&&!queue.data.items.length?<div className="info-banner">No traceability actions match this queue view.</div>:null}
    {queue.data?.items.length?<><section className="inventory-panel"><TraceabilityTable rows={queue.data.items}/></section><label className="traceability-inspect">Inspect transaction<select value={selected} onChange={event=>setSelected(event.target.value)}><option value="">Choose a transaction</option>{queue.data.items.map(row=><option value={row.id} key={row.id}>{title(row.status)} · {row.operation_type} · {row.entity_id}</option>)}</select></label></>:null}
    <StreamlitDialog open={Boolean(selected)} onClose={()=>setSelected("")} title="Traceability Operations">
      {detail.isLoading?<div className="state">Loading transaction detail…</div>:null}
      {detail.isError?<div className="form-error">{detail.error.message}</div>:null}
      {detail.data?<div className="traceability-detail"><h3>Transaction detail</h3><section className="metrics four"><Metric label="Status" value={title(detail.data.transaction.status)}/><Metric label="Provider" value={detail.data.transaction.provider.toUpperCase()}/><Metric label="Attempts" value={detail.data.transaction.attempt_count}/><Metric label="Entity" value={detail.data.transaction.entity_type}/></section><p>{detail.data.transaction.operation_type} · {detail.data.transaction.entity_id} · requested by {detail.data.transaction.requested_by}</p>{detail.data.transaction.external_reference?<p>External reference: {detail.data.transaction.external_reference}</p>:null}{detail.data.transaction.error_message||detail.data.transaction.error_code?<div className="form-error">{detail.data.transaction.error_message||detail.data.transaction.error_code}</div>:null}
        <div className="view-tabs parity-tabs" role="tablist">{(["Overview","Attempts","Lifecycle","Payloads"] as DetailTab[]).map(value=><button role="tab" aria-selected={tab===value} className={tab===value?"active":""} onClick={()=>setTab(value)} key={value}>{value}</button>)}</div>
        {tab==="Overview"?<Overview tx={detail.data.transaction}/>:null}{tab==="Attempts"?<Attempts rows={detail.data.attempts}/>:null}{tab==="Lifecycle"?<Lifecycle rows={detail.data.events}/>:null}{tab==="Payloads"?<Payloads tx={detail.data.transaction}/>:null}
        {!canManage?<div className="info-banner">Your role can review traceability state but cannot change queue or reconciliation status.</div>:<Reconciliation tx={detail.data.transaction} reason={reason} confirmed={confirmed} pending={resolve.isPending} onReason={setReason} onConfirmed={setConfirmed} onAction={action=>{setMessage("");resolve.mutate(action)}}/>}
        {message?<div className="success-banner">{message}</div>:null}{resolve.isError?<div className="form-error">{resolve.error.message}</div>:null}
      </div>:null}
    </StreamlitDialog>
  </div>;
}

function Metric({label,value}:{label:string;value:string|number}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function TraceabilityTable({rows}:{rows:Tx[]}){return <div className="table-wrap"><table><thead><tr><th>Status</th><th>Provider</th><th>Operation</th><th>Entity Type</th><th>Entity</th><th>External Ref</th><th>Attempts</th><th>Requested By</th><th>Requested At</th><th>Error</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{title(row.status)}</td><td>{row.provider.toUpperCase()}</td><td>{row.operation_type}</td><td>{row.entity_type}</td><td>{row.entity_id}</td><td>{row.external_reference||"—"}</td><td>{row.attempt_count}</td><td>{row.requested_by}</td><td>{date(row.requested_at)}</td><td>{row.error_message||row.error_code||"—"}</td></tr>)}</tbody></table></div>}
function Overview({tx}:{tx:Tx}){const rows:{label:string;value:string}[]=[{label:"license",value:tx.license_number},{label:"reason",value:tx.reason},{label:"requested_at",value:date(tx.requested_at)},{label:"submitted_at",value:date(tx.submitted_at)},{label:"completed_at",value:date(tx.completed_at)},{label:"next_attempt_at",value:date(tx.next_attempt_at)},{label:"idempotency_key",value:tx.idempotency_key}];return <div className="traceability-overview">{rows.map(row=><div key={row.label}><strong>{row.label}</strong><span>{row.value||"—"}</span></div>)}</div>}
function Attempts({rows}:{rows:Attempt[]}){if(!rows.length)return <div className="info-banner">No provider submission attempts have been recorded yet.</div>;return <Table columns={["Attempt","HTTP","Error","Started","Completed"]} rows={rows.map(row=>[row.attempt_number,row.http_status??"—",row.error_message||row.error_code||"—",date(row.started_at),date(row.completed_at)])}/>}
function Lifecycle({rows}:{rows:Event[]}){if(!rows.length)return <div className="info-banner">No lifecycle transitions have been recorded for this transaction yet.</div>;return <Table columns={["From","To","Actor","Reason","Source","When"]} rows={rows.map(row=>[title(row.from_status),title(row.to_status),row.actor,row.reason,row.source,date(row.occurred_at)])}/>}
function Payloads({tx}:{tx:Tx}){return <div className="two-column-grid payload-grid"><section><div className="eyebrow">SANITIZED REQUEST</div><pre>{pretty(tx.request_payload_json)}</pre></section><section><div className="eyebrow">SANITIZED RESPONSE</div><pre>{pretty(tx.response_payload_json)}</pre></section></div>}
function Reconciliation({tx,reason,confirmed,pending,onReason,onConfirmed,onAction}:{tx:Tx;reason:string;confirmed:boolean;pending:boolean;onReason:(value:string)=>void;onConfirmed:(value:boolean)=>void;onAction:(value:string)=>void}){const requeue=["rejected","reconciliation_required"].includes(tx.status);const verify=["accepted","reconciliation_required"].includes(tx.status);const cancel=!["verified","cancelled"].includes(tx.status);if(!requeue&&!verify&&!cancel)return null;const disabled=!reason.trim()||!confirmed||pending;return <section className="reconciliation-action"><h3>Reconciliation action</h3><label>Reason / reconciliation evidence *<textarea rows={4} placeholder="Describe what was checked and why this lifecycle change is appropriate." value={reason} onChange={event=>onReason(event.target.value)}/></label><label className="toggle"><input type="checkbox" checked={confirmed} onChange={event=>onConfirmed(event.target.checked)}/>I reviewed the external state and understand this action is audit logged.</label><div className="audit-actions">{requeue?<button className="primary" disabled={disabled} onClick={()=>onAction("requeue")}>Requeue</button>:null}{verify?<button className="secondary" disabled={disabled} onClick={()=>onAction("verify")}>Mark verified</button>:null}{cancel?<button className="secondary" disabled={disabled} onClick={()=>onAction("cancel")}>Cancel action</button>:null}</div></section>}
function Table({columns,rows}:{columns:string[];rows:(string|number)[][]}){return <div className="table-wrap"><table><thead><tr>{columns.map(value=><th key={value}>{value}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{row.map((value,column)=><td key={columns[column]}>{value}</td>)}</tr>)}</tbody></table></div>}
function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function date(value:string|null){return value?new Date(value).toLocaleString():""}
function pretty(raw:string){try{return JSON.stringify(JSON.parse(raw||"{}"),null,2)}catch{return JSON.stringify({raw:raw||""},null,2)}}
