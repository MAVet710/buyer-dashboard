import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type LabResult = Record<string, unknown>;
type Payload = {
  provider:string;
  linked:boolean;
  network_request_made:boolean;
  provider_package_id:string;
  provider_package_label:string;
  environment:string;
  license_number:string;
  identity_status:string;
  last_synced_at:string|null;
  age_seconds:number|null;
  result_count:number;
  results:LabResult[];
  provider_verified?:boolean;
  complete?:boolean;
  page_count?:number;
};

export function MetrcPackageLabResults({ lotId, environment="" }:{ lotId:string; environment?:"sandbox"|"production"|"" }) {
  const queryClient=useQueryClient();
  const cachePath=`/api/v1/inventory/regulatory-detail/local/inventory_lot/${encodeURIComponent(lotId)}/lab-results${environment?`?environment=${environment}`:""}`;
  const livePath=`/api/v1/inventory/regulatory-detail/local/inventory_lot/${encodeURIComponent(lotId)}/lab-results/live`;
  const queryKey=["metrc-package-lab-results",lotId,environment];
  const cached=useQuery({queryKey,enabled:Boolean(lotId),queryFn:({signal})=>apiGet<Payload>(cachePath,signal)});
  const live=useMutation({
    mutationFn:()=>apiGet<Payload>(livePath),
    onSuccess:(data)=>queryClient.setQueryData(queryKey,data),
  });
  const data=(live.data??cached.data) as Payload|undefined;

  return <section className="inventory-panel">
    <div className="eyebrow">TESTING · METRC PACKAGE</div>
    <div className="section-heading-row"><div><h3>Lab results</h3><p className="source-caption">Cached package-specific regulatory evidence loads from DoobieLogic. Live verification contacts Metrc only when you request it.</p></div><button className="secondary" type="button" disabled={!data?.linked||live.isPending} onClick={()=>live.mutate()}>{live.isPending?"Verifying…":"Verify live"}</button></div>
    {cached.isLoading?<div className="state">Loading synchronized package testing evidence…</div>:null}
    {cached.isError?<div className="warning-banner">{cached.error.message}</div>:null}
    {live.isError?<div className="warning-banner">{live.error.message}</div>:null}
    {data&&!data.linked?<div className="info-banner">This package does not have an exact Metrc package identity in the selected environment yet.</div>:null}
    {data?.linked?<>
      <div className="catalog-row"><strong>Package</strong><span>{data.provider_package_label||data.provider_package_id}</span><small>{[data.license_number,data.environment].filter(Boolean).join(" · ")}</small></div>
      <div className="catalog-row"><strong>Testing evidence</strong><span>{data.result_count?`${data.result_count} result${data.result_count===1?"":"s"}`:"No cached results"}</span><small>{freshness(data.age_seconds,data.last_synced_at)}</small></div>
      {live.data?.provider_verified?<div className="info-banner">Metrc live verification completed for this exact package{live.data.complete===false?"; the provider response was incomplete, so existing cached membership was not destructively replaced.":"."}</div>:null}
      {data.results.length?<div className="package-timeline">{data.results.map((row,index)=><article className="commercial-order-card" key={resultKey(row,index)}><div><strong>{resultName(row)}</strong>{resultStatus(row)?<span className="status-pill">{resultStatus(row)}</span>:null}</div><p>{resultValue(row)}</p><small>{resultDetail(row)}</small></article>)}</div>:<div className="info-banner">No package-specific lab results are cached yet. Use Verify live when you need the current Metrc testing record.</div>}
      {data.results.length?<details className="streamlit-expander"><summary>Raw package lab evidence</summary><pre>{JSON.stringify(data.results,null,2)}</pre></details>:null}
    </>:null}
  </section>;
}

function source(row:LabResult):Record<string,unknown>{const value=row.source;return value&&typeof value==="object"&&!Array.isArray(value)?value as Record<string,unknown>:row}
function pick(row:LabResult,...keys:string[]):unknown{const raw=source(row);for(const key of keys){const value=raw[key]??row[key];if(value!==undefined&&value!==null&&String(value).trim()!=="")return value}return ""}
function resultName(row:LabResult){return String(pick(row,"TestTypeName","TestType","AnalyteName","Analyte","Name")||"Lab result")}
function resultStatus(row:LabResult){return String(pick(row,"TestResultStatus","Status","LabTestResultStatus")||"")}
function resultValue(row:LabResult){const value=pick(row,"TestResultLevel","TestResult","Result","Value");const unit=pick(row,"TestResultUnit","UnitOfMeasureName","UnitOfMeasureAbbreviation","Unit");return value!==""?`${String(value)}${unit?` ${String(unit)}`:""}`:"Result value not supplied"}
function resultDetail(row:LabResult){const tested=pick(row,"TestPerformedDate","TestDate","ResultDate","CreatedDate","LastModified");const lab=pick(row,"LabFacilityName","LabName","FacilityName");return [lab?`Lab: ${String(lab)}`:"",tested?`Tested: ${formatDate(String(tested))}`:""].filter(Boolean).join(" · ")||"Package-specific Metrc testing record"}
function resultKey(row:LabResult,index:number){return String(pick(row,"Id","TestResultId","LabTestResultId")||`${resultName(row)}-${index}`)}
function formatDate(value:string){const parsed=new Date(value);return Number.isNaN(parsed.getTime())?value:parsed.toLocaleString()}
function freshness(seconds:number|null,last:string|null){if(seconds==null)return last?formatDate(last):"Not synchronized";if(seconds<60)return "Synced less than a minute ago";if(seconds<3600)return `Synced ${Math.floor(seconds/60)} min ago`;if(seconds<86400)return `Synced ${Math.floor(seconds/3600)} hr ago`;return `Synced ${Math.floor(seconds/86400)} day(s) ago`}
