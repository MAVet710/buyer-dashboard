import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type Identity = {
  provider:string;jurisdiction:string;environment:string;license_number:string;
  entity_type:string;entity_id:string;provider_resource:string;provider_id:string;
  provider_label:string;status:string;verified_at:string|null;last_seen_at:string|null;mismatch_reason:string;
};
type ProviderSnapshot = {
  provider:string;environment:string;resource:string;external_id:string;provider_label:string;
  present:boolean;snapshot_run_id:string;fingerprint:string;last_seen_at:string|null;age_seconds:number|null;
  normalized_provider_record:Record<string,unknown>;raw_provider_record:Record<string,unknown>;
};
type SyncEvidence = {
  status:string;environment:string;cursor:string;last_started_at:string|null;last_completed_at:string|null;
  last_success_at:string|null;last_error:string;records_seen:number;records_written:number;
};
type Entry = {
  identity:Identity|null;current_snapshot:ProviderSnapshot|null;sync:SyncEvidence|null;
  reconciliation_required:boolean;current_in_provider:boolean;
};
type LocalDetail = {provider:string;entity_type:string;entity_id:string;network_request_made:boolean;linked:boolean;entries:Entry[]};
type ProviderDetail = {provider:string;network_request_made:boolean;current_in_provider:boolean;reconciliation_required:boolean;identity:Identity|null;current_snapshot:ProviderSnapshot;sync:SyncEvidence|null};
type LedgerEvent = {id:string;direction:string;operation:string;machine_status:string;operator_status:string;requested_at:string;latest_error:string;error_classification:string;reconciliation_state:string;provider_reference:string;retry_eligible:boolean};
type EntityHistory = {current_state:string;unresolved_exception_count:number;last_successful_inbound:string|null;last_successful_outbound:string|null;events:LedgerEvent[]};

type Props = {
  entityType?:string;
  entityId?:string;
  providerResource?:string;
  providerId?:string;
  environment?:"sandbox"|"production"|"";
  title?:string;
};

export function RegulatoryDetailPanel({entityType="",entityId="",providerResource="",providerId="",environment="",title="Metrc Regulatory Details"}:Props){
  const local=Boolean(entityType&&entityId);
  const provider=Boolean(providerResource&&providerId);
  const path=local
    ? `/api/v1/inventory/regulatory-detail/local/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}${environment?`?environment=${environment}`:""}`
    : provider
      ? `/api/v1/inventory/regulatory-detail/provider/${encodeURIComponent(providerResource)}/${encodeURIComponent(providerId)}${environment?`?environment=${environment}`:""}`
      : "";
  const detail=useQuery({queryKey:["regulatory-detail",path],enabled:Boolean(path),queryFn:({signal})=>apiGet<LocalDetail|ProviderDetail>(path,signal)});
  const historyPath=local?`/api/v1/traceability-actions/entities/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/history${environment?`?environment=${environment}`:""}`:"";
  const history=useQuery({queryKey:["traceability-entity-history",historyPath],enabled:Boolean(historyPath),queryFn:({signal})=>apiGet<EntityHistory>(historyPath,signal)});
  if(!path)return null;
  if(detail.isLoading)return <section className="inventory-panel"><div className="eyebrow">REGULATORY SOURCE</div><div className="state">Loading synchronized regulatory evidence…</div></section>;
  if(detail.isError)return <section className="inventory-panel"><div className="eyebrow">REGULATORY SOURCE</div><div className="warning-banner">{detail.error.message}</div></section>;
  const data=detail.data;
  const entries:Entry[]=data&&"entries" in data?data.entries:data?[{identity:data.identity,current_snapshot:data.current_snapshot,sync:data.sync,reconciliation_required:data.reconciliation_required,current_in_provider:data.current_in_provider}]:[];
  return <section className="inventory-panel regulatory-detail-panel">
    <div className="eyebrow">REGULATORY SOURCE · LOCAL SNAPSHOT</div><h3>{title}</h3>
    <p className="source-caption">This view reads DoobieLogic's last successfully synchronized provider snapshot. Opening it does not contact Metrc.</p>
    {!entries.length?<div className="info-banner">No exact Metrc identity is linked to this DoobieLogic object yet.</div>:entries.map((entry,index)=><RegulatoryEntry key={`${entry.identity?.provider_id||entry.current_snapshot?.external_id||index}`} entry={entry}/>) }
    {history.data?<LedgerHistory data={history.data}/>:history.isLoading?<div className="state">Loading traceability history…</div>:null}
  </section>;
}

function LedgerHistory({data}:{data:EntityHistory}){
  return <div className="regulatory-detail-entry">
    <div className="section-heading"><div><div className="eyebrow">TRACEABILITY LEDGER</div><h4>{title(data.current_state)}</h4></div>{data.unresolved_exception_count?<span className="badge">{data.unresolved_exception_count} need attention</span>:<span className="read-only-chip">Healthy</span>}</div>
    <div className="detail-facts"><p><strong>Last inbound:</strong> {dateTime(data.last_successful_inbound)}</p><p><strong>Last outbound:</strong> {dateTime(data.last_successful_outbound)}</p></div>
    {data.events.slice(0,8).map(event=><article className="plant-event" key={event.id}><strong>{title(event.operation)}</strong><span>{title(event.machine_status)} · {title(event.direction)}</span><small>{dateTime(event.requested_at)}{event.provider_reference?` · Metrc ${event.provider_reference}`:""}</small>{event.latest_error?<div className="warning-banner">{humanError(event)}</div>:null}</article>)}
    {!data.events.length?<div className="empty">No ledger events are linked to this entity yet.</div>:null}
  </div>;
}

function humanError(event:LedgerEvent){
  if(event.error_classification==="rate_limited")return "Metrc temporarily limited requests. This action can be retried after the wait period.";
  if(event.error_classification==="authentication_configuration_failure")return "The facility credential or Metrc permission needs review.";
  if(event.error_classification==="provider_validation_rejection")return `Metrc rejected the mapped record. ${event.latest_error}`;
  return event.latest_error;
}

function RegulatoryEntry({entry}:{entry:Entry}){
  const identity=entry.identity;const snapshot=entry.current_snapshot;const sync=entry.sync;
  return <div className="regulatory-detail-entry">
    {entry.reconciliation_required?<div className="warning-banner"><strong>Reconciliation required.</strong> {identity?.mismatch_reason||"The local and provider identities require operator review."}</div>:null}
    <div className="catalog-row"><strong>Provider identity</strong><span>{identity?.provider_label||snapshot?.provider_label||identity?.provider_id||snapshot?.external_id||"—"}</span><small>{identity?`${identity.provider_resource} · ${identity.provider_id}`:snapshot?`${snapshot.resource} · ${snapshot.external_id}`:""}</small></div>
    <div className="catalog-row"><strong>Current in provider</strong><span>{entry.current_in_provider?"Yes":"No / last seen only"}</span></div>
    <div className="catalog-row"><strong>License scope</strong><span>{identity?.license_number||"—"}</span><small>{[identity?.jurisdiction,identity?.environment||snapshot?.environment].filter(Boolean).join(" · ")}</small></div>
    <div className="catalog-row"><strong>Identity status</strong><span>{title(identity?.status||"unlinked")}</span></div>
    <div className="catalog-row"><strong>Last provider sync</strong><span>{relative(snapshot?.age_seconds)}</span><small>{snapshot?.last_seen_at?new Date(snapshot.last_seen_at).toLocaleString():"No current snapshot"}</small></div>
    {sync?<><div className="catalog-row"><strong>Resource sync</strong><span>{title(sync.status)}</span><small>{sync.last_success_at?`Last success ${new Date(sync.last_success_at).toLocaleString()}`:"No successful sync recorded"}</small></div>{sync.last_error?<div className="warning-banner">{sync.last_error}</div>:null}</>:null}
    {snapshot?<details className="streamlit-expander"><summary>Normalized regulatory record</summary><pre>{JSON.stringify(snapshot.normalized_provider_record,null,2)}</pre></details>:null}
    {snapshot?<details className="streamlit-expander"><summary>Raw provider record</summary><p className="source-caption">Lossless synchronized provider payload for compliance review and troubleshooting.</p><pre>{JSON.stringify(snapshot.raw_provider_record,null,2)}</pre></details>:null}
  </div>;
}

function relative(seconds:number|null|undefined){if(seconds==null)return "Not synchronized";if(seconds<60)return "Synced less than a minute ago";if(seconds<3600)return `Synced ${Math.floor(seconds/60)} min ago`;if(seconds<86400)return `Synced ${Math.floor(seconds/3600)} hr ago`;return `Synced ${Math.floor(seconds/86400)} day(s) ago`}
function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function dateTime(value:string|null|undefined){if(!value)return "Not recorded";const parsed=new Date(value);return Number.isNaN(parsed.getTime())?value:parsed.toLocaleString()}
