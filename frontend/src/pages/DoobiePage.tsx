import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPost } from "../lib/api";

type Proposal = {
  id:string; action_type:string; title:string; rationale:string; payload:Record<string,unknown>;
  preview:Record<string,unknown>; financial_impact_usd:number; risk_level:string; status:string;
  created_by:string; approved_by:string; created_at:string;
};
type Actions = { allowed_actions:string[]; items:Proposal[] };
type RegulatoryRecommendation = {
  operation_type:string; entity_id:string; finding_code:string; severity:string; title:string; message:string;
  provider_dispatch_enabled:boolean; human_approval_required:boolean;
};
type WriteContract = {
  operation_type:string; capability:string; method:string; path:string; entity_type:string; risk_level:string;
  approval_required:boolean; dispatch_enabled:boolean; payload_contract_verified:boolean; jurisdictions:string[];
  environments:string[]; verification_resource:string; evidence_endpoint:string; note:string;
};
type RegulatoryRecommendations = { read_only_analysis:boolean; provider_payloads_generated_by_model:boolean; recommendations:RegulatoryRecommendation[]; catalog:WriteContract[] };
type RegulatoryCatalog = {
  configured:boolean; connected:boolean; trusted_mapping:boolean; jurisdiction_code:string; environment:string; license_number:string;
  approval_roles:string[]; items:WriteContract[]; receiving_policy:{operation_type:string;provider_submission_enabled:boolean;message:string};
};
type SubmitResult = { status?:string; dispatch?:{status?:string}; message?:string };

export function DoobiePage() {
  const client = useQueryClient();
  const [selected,setSelected] = useState<Proposal|null>(null);
  const [message,setMessage] = useState("");
  const actions = useQuery({queryKey:["doobie-actions"],queryFn:({signal})=>apiGet<Actions>("/api/v1/doobie/actions",signal)});
  const regulatory = useQuery({queryKey:["doobie-regulatory-recommendations"],queryFn:({signal})=>apiGet<RegulatoryRecommendations>("/api/v1/doobie/regulatory-actions/recommendations",signal),retry:false});
  const catalog = useQuery({queryKey:["doobie-regulatory-catalog"],queryFn:({signal})=>apiGet<RegulatoryCatalog>("/api/v1/doobie/regulatory-actions/catalog",signal),retry:false});

  const refresh = async()=>{await Promise.all([
    client.invalidateQueries({queryKey:["doobie-actions"]}),
    client.invalidateQueries({queryKey:["doobie-regulatory-recommendations"]}),
    client.invalidateQueries({queryKey:["doobie-regulatory-catalog"]}),
  ])};
  const decision = useMutation({
    mutationFn:(action:string)=>apiPost(`/api/v1/doobie/actions/${selected?.id}/${action}`,{}),
    onSuccess:async()=>{setMessage("Action state updated.");setSelected(null);await refresh()},
  });
  const regulatorySubmit = useMutation({
    mutationFn:(id:string)=>apiPost<SubmitResult>(`/api/v1/doobie/regulatory-actions/${id}/submit`,{}),
    onSuccess:async result=>{setMessage(result.message||`Regulatory submission status: ${result.dispatch?.status||result.status||"submitted"}.`);setSelected(null);await refresh()},
  });

  const writeRows=catalog.data?.items??regulatory.data?.catalog??[];
  const enabledWrites=writeRows.filter(row=>row.dispatch_enabled).length;
  const lockedWrites=writeRows.filter(row=>!row.dispatch_enabled).length;
  const error=decision.error||regulatorySubmit.error;

  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">Doobie Agent</div><h1>Action Center</h1><p>Doobie can surface regulatory and operational next moves, but provider payloads remain deterministic and regulated changes stay human-controlled.</p></div></div>

    <section className="metrics">
      <Metric label="Proposed" value={actions.data?.items.filter(row=>row.status==="proposed").length??"—"}/>
      <Metric label="Approved" value={actions.data?.items.filter(row=>row.status==="approved").length??"—"}/>
      <Metric label="Regulatory writes enabled" value={catalog.data?enabledWrites:"—"}/>
      <Metric label="Write contracts locked" value={catalog.data?lockedWrites:"—"}/>
    </section>

    <section className="inventory-panel">
      <div className="eyebrow">REGULATORY ACTION ENGINE</div>
      <div className="manifest-draft-heading"><div><h2>Provider controls</h2><p className="section-note">The action registry separates documented endpoint families from operations whose exact deterministic payload contract is actually approved for execution.</p></div><span className="read-only-chip">Human approved</span></div>
      {catalog.data?<div className={catalog.data.configured&&catalog.data.connected&&catalog.data.trusted_mapping?"success-banner":"warning-banner"}>
        <strong>{catalog.data.jurisdiction_code||"No jurisdiction"} · {catalog.data.environment||"environment not set"}</strong><br/>
        <span>{catalog.data.configured&&catalog.data.connected&&catalog.data.trusted_mapping?"Exact facility mapping is trusted for governed operations.":"Provider writes remain blocked until the exact facility/license/environment mapping is connected and trusted."}</span>
      </div>:null}
      {catalog.data?.receiving_policy?<div className="info-banner"><strong>Receiving:</strong> {catalog.data.receiving_policy.message}</div>:null}
      <div className="table-wrap"><table><thead><tr><th>Operation</th><th>Endpoint evidence</th><th>Payload</th><th>Provider dispatch</th><th>Verification</th></tr></thead><tbody>{writeRows.map(row=><tr key={row.operation_type}><td>{row.operation_type.replaceAll("_"," ")}</td><td>{row.evidence_endpoint||"No provider endpoint promoted"}</td><td>{row.payload_contract_verified?"Verified":"Locked"}</td><td>{row.dispatch_enabled?"Enabled":"Blocked"}</td><td>{row.verification_resource||"Manual / pending contract"}</td></tr>)}</tbody></table></div>
    </section>

    <section className="inventory-panel">
      <div className="eyebrow">DOOBIE REGULATORY INTELLIGENCE</div>
      <h2>Recommended reviews</h2>
      <p className="section-note">These recommendations come from the deterministic facility regulatory snapshot. Doobie does not invent Metrc JSON or autonomously submit them.</p>
      {regulatory.isLoading?<div className="state">Checking current facility evidence…</div>:null}
      {regulatory.isError?<div className="warning-banner">Regulatory recommendations are unavailable until this facility&apos;s regulatory context is ready.</div>:null}
      {regulatory.data?.recommendations.length?<div className="role-home-inbox">{regulatory.data.recommendations.map((row,index)=><article className="role-home-alert" key={`${row.operation_type}:${row.entity_id}:${index}`}>
        <div className="role-home-alert-area"><span>{row.operation_type.replaceAll("_"," ").toUpperCase()}</span><em className={`severity ${row.severity}`}>{row.severity}</em></div>
        <div className="role-home-alert-body"><strong>{row.title}</strong><p>{row.message}</p>{row.entity_id?<small>{row.entity_id}</small>:null}</div>
        <span className={row.provider_dispatch_enabled?"success-text":"warning-text"}>{row.provider_dispatch_enabled?"Governed write available":"Review only"}</span>
      </article>)}</div>:!regulatory.isLoading&&!regulatory.isError?<div className="empty">No regulatory action recommendations are currently produced from the loaded facility evidence.</div>:null}
    </section>

    <section className="inventory-panel">
      <div className="eyebrow">EMPLOYEE APPROVAL QUEUE</div>
      <div className="table-wrap"><table><thead><tr><th>Recommendation</th><th>Action</th><th>Risk</th><th>Impact</th><th>Status</th><th>Created</th></tr></thead><tbody>{actions.data?.items.map(row=><tr key={row.id} onClick={()=>setSelected(row)}><td>{row.title}</td><td>{row.action_type.replaceAll("_"," ")}</td><td>{row.risk_level}</td><td>${row.financial_impact_usd.toFixed(2)}</td><td>{row.status}</td><td>{new Date(row.created_at).toLocaleString()}</td></tr>)}</tbody></table>{actions.data?.items.length===0?<div className="empty">No proposed actions. Doobie cannot execute operational changes without a preview and approval.</div>:null}</div>
    </section>

    {message?<div className="success-banner">{message}</div>:null}
    {selected?<div className="modal-backdrop"><div className="modal"><div className="modal-heading"><div><div className="eyebrow">Action preview</div><h2>{selected.title}</h2><p>{selected.rationale}</p></div><button className="secondary" onClick={()=>setSelected(null)}>Close</button></div><div className="preview-json"><h3>Preview</h3><pre>{JSON.stringify(selected.preview,null,2)}</pre><h3>Execution payload</h3><pre>{JSON.stringify(selected.payload,null,2)}</pre></div><div className="audit-actions">
      {selected.status!=="executed"?<button className="secondary" disabled={decision.isPending} onClick={()=>decision.mutate("reject")}>Reject</button>:null}
      {["proposed","failed"].includes(selected.status)?<button className="primary" disabled={decision.isPending} onClick={()=>decision.mutate("approve")}>Approve preview</button>:null}
      {selected.status==="approved"&&selected.action_type==="prepare_regulatory_action"?<button className="primary" disabled={regulatorySubmit.isPending} onClick={()=>regulatorySubmit.mutate(selected.id)}>{regulatorySubmit.isPending?"Submitting…":"Submit approved regulatory action"}</button>:null}
      {selected.status==="approved"&&selected.action_type==="prepare_transfer_manifest"?<span className="warning-text">Submit this manifest from Wholesale Ops so its provider readback lifecycle stays visible.</span>:null}
      {selected.status==="approved"&&!selected.action_type.startsWith("prepare_")?<button className="primary" disabled={decision.isPending} onClick={()=>decision.mutate("execute")}>Execute approved action</button>:null}
      {selected.status==="executed"&&selected.action_type==="prepare_regulatory_action"?<button className="primary" disabled={regulatorySubmit.isPending} onClick={()=>regulatorySubmit.mutate(selected.id)}>Check / submit regulatory transaction</button>:null}
    </div>{error?<div className="form-error">{error.message}</div>:null}</div></div>:null}
  </div>;
}

function Metric({label,value}:{label:string;value:string|number}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
