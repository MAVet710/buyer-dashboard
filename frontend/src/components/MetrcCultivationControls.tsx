import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

export type MetrcObjectLink = {
  id:string; provider:string; jurisdiction:string; environment:string; license_number:string;
  entity_type:string; entity_id:string; provider_resource:string; provider_id:string; provider_label:string;
  status:"verified"|"stale"|"reconciliation_required"; source_transaction_id:string|null;
  verified_at:string|null; last_seen_at:string|null; mismatch_reason:string;
};

export type CultivationIdentityResponse = {
  environment:string; license_number:string;
  rooms:MetrcObjectLink[]; plant_batches:MetrcObjectLink[]; plants:MetrcObjectLink[]; harvests:MetrcObjectLink[]; packages:MetrcObjectLink[];
};

export type CultivationActionRequest = {
  operation_type:"plant_batch_sync"|"plant_batch_vegetative"|"plant_move";
  entity_id:string;
  actual_date:string;
  destination_room_id?:string;
  starting_tag?:string;
  reason:string;
};

type ActionPreview = {
  ready:boolean; operation_type:string; summary:Record<string,string|number|boolean|null>;
  confirmation_id:string; confirmation_token:string; message:string;
  compliance_evidence:{method:string;path:string;license_number:string;environment:string;provider_request_body:unknown};
};

type ActionResult = {
  ok:boolean; verified:boolean; status:string; transaction_id:string; external_reference:string;
  summary:Record<string,string|number|boolean|null>; http_status:number; stage:string; local_result:unknown; message:string;
};

type MetrcLocation = {provider_id:string;name:string;status:string;last_modified:string};
type LocationList = {items:MetrcLocation[];truncated:boolean;page_size:number;max_pages:number};

export function MetrcCultivationActionDialog({request,onClose,onChanged}:{request:CultivationActionRequest;onClose:()=>void;onChanged:()=>void|Promise<void>}) {
  const preview=useQuery({queryKey:["metrc-cultivation-action-preview",request],queryFn:()=>apiPost<ActionPreview>("/api/v1/metrc-cultivation/actions/preview",request),retry:false});
  const execute=useMutation({
    mutationFn:()=>apiPost<ActionResult>("/api/v1/metrc-cultivation/actions/execute",{
      ...request,
      confirmation_id:preview.data?.confirmation_id,
      confirmation_token:preview.data?.confirmation_token,
    }),
    onSuccess:async row=>{if(row.verified)await onChanged()},
  });
  const result=execute.data;
  const title=String(preview.data?.summary?.title||actionTitle(request.operation_type));
  return <section className="inventory-panel compact metrc-action-review">
    <div className="section-heading"><div><div className="eyebrow">Cultivation · Metrc</div><h4>{title}</h4><p className="source-caption">DoobieLogic verifies the exact provider state before changing local cultivation state.</p></div><button className="secondary" type="button" onClick={onClose}>Close</button></div>
    {preview.isLoading?<div className="state">Checking current DoobieLogic and Metrc state…</div>:null}
    {preview.isError?<div className="state error">{preview.error.message}</div>:null}
    {preview.data&&!result?<>
      <div className="info-banner"><strong>Review before submitting.</strong><br/><span>{preview.data.message}</span></div>
      <div className="detail-facts">{Object.entries(preview.data.summary).filter(([key])=>key!=="title").map(([key,value])=><div key={key}><span>{friendly(key)}</span><strong>{display(value)}</strong></div>)}</div>
      <button className="primary submit" type="button" disabled={execute.isPending} onClick={()=>execute.mutate()}>{execute.isPending?"Submitting to Metrc…":"Confirm & submit to Metrc"}</button>
      {execute.isError?<div className="form-error">{execute.error.message}</div>:null}
      <details className="compliance-details"><summary>Compliance evidence details</summary><pre>{JSON.stringify(preview.data.compliance_evidence,null,2)}</pre></details>
    </>:null}
    {result?<div className={result.verified?"success-banner":"warning-banner"}><strong>{result.verified?"Verified":"Reconciliation required"}</strong><br/><span>{result.message}</span><br/><small>Transaction {result.transaction_id}{result.external_reference?` · Metrc ${result.external_reference}`:""}</small></div>:null}
    {result?<button className="secondary submit" type="button" onClick={onClose}>Done</button>:null}
  </section>;
}

export function MetrcRoomLinkDialog({room,onClose,onLinked}:{room:{id:string;room_code:string;display_name:string};onClose:()=>void;onLinked:()=>void|Promise<void>}) {
  const [search,setSearch]=useState("");
  const [selected,setSelected]=useState("");
  const locations=useQuery({queryKey:["metrc-cultivation-locations"],queryFn:({signal})=>apiGet<LocationList>("/api/v1/metrc-cultivation/locations",signal),retry:false});
  const filtered=useMemo(()=>{const needle=search.trim().toLowerCase();const rows=locations.data?.items??[];return needle?rows.filter(row=>`${row.name} ${row.provider_id}`.toLowerCase().includes(needle)):rows},[locations.data,search]);
  const link=useMutation({mutationFn:()=>apiPost(`/api/v1/metrc-cultivation/rooms/${room.id}/link`,{provider_location_id:selected}),onSuccess:async()=>{await onLinked()}});
  return <section className="inventory-panel compact metrc-room-link">
    <div className="section-heading"><div><div className="eyebrow">Cultivation · Metrc identity</div><h4>Link {room.display_name||room.room_code}</h4><p className="source-caption">Choose the exact Metrc Location identity. DoobieLogic never guesses this link from matching room names.</p></div><button className="secondary" type="button" onClick={onClose}>Close</button></div>
    {locations.isLoading?<div className="state">Loading active Metrc locations…</div>:null}
    {locations.isError?<div className="state error">{locations.error.message}</div>:null}
    {locations.data&&!link.isSuccess?<>
      <label>Find Metrc location<input value={search} onChange={event=>setSearch(event.target.value)} placeholder="Search name or Metrc ID"/></label>
      <div className="table-wrap"><table><thead><tr><th></th><th>Metrc location</th><th>Provider ID</th></tr></thead><tbody>{filtered.slice(0,200).map(row=><tr key={row.provider_id} className="selectable-row" onClick={()=>setSelected(row.provider_id)}><td><input type="radio" checked={selected===row.provider_id} onChange={()=>setSelected(row.provider_id)} onClick={event=>event.stopPropagation()}/></td><td><strong>{row.name||"Unnamed location"}</strong></td><td>{row.provider_id}</td></tr>)}</tbody></table></div>
      {!filtered.length?<div className="empty">No active Metrc locations match this search.</div>:null}
      {locations.data.truncated?<div className="warning-banner">Metrc returned more locations than this bounded lookup displays. Narrow the facility/location setup before linking.</div>:null}
      <button className="primary submit" type="button" disabled={!selected||link.isPending} onClick={()=>link.mutate()}>{link.isPending?"Verifying exact location…":"Verify & link exact location"}</button>
      {link.isError?<div className="form-error">{link.error.message}</div>:null}
    </>:null}
    {link.isSuccess?<><div className="success-banner"><strong>Metrc location verified and linked.</strong><br/><span>The provider ID is now the durable identity; the display name is only an operator label.</span></div><button className="secondary submit" type="button" onClick={onClose}>Done</button></>:null}
  </section>;
}

export function useMetrcCultivationIdentities(enabled=true){
  return useQuery({queryKey:["metrc-cultivation-identities"],queryFn:({signal})=>apiGet<CultivationIdentityResponse>("/api/v1/metrc-cultivation/identities",signal),enabled,retry:false});
}

function actionTitle(value:string){return value==="plant_batch_sync"?"Create Metrc plant batch":value==="plant_batch_vegetative"?"Move plant batch to vegetative":"Move plant"}
function friendly(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function display(value:unknown){if(value===null||value===undefined||value==="")return "—";if(typeof value==="boolean")return value?"Yes":"No";return String(value)}
