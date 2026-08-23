import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPostForm } from "../lib/api";

type Catalog={label:string;dataset_key:string;description:string;types:string[]};
type History={id:string;dataset_key:string;dataset_label:string;filename:string;payload_size:number;row_count:number;column_count:number;quality:string;status:string;imported_by:string;activated_at:string;missing_fields:string[];mapping:Record<string,string>};
type StatusRow={operations:string;dataset:string;status:string;source:string;rows:number|string;updated:string|null};
type DataHub={catalog:Catalog[];history:History[];status:StatusRow[];extraction_runs:number};
type Account={user:{role:string};facilities:{id:string;name:string}[];facility_id:string};
type Inspection={dataset_key:string;dataset_label:string;name:string;rows:number;columns:number;quality:string;matches:Record<string,string>;missing:string[];requirements:string[];source_columns:string[];preview:Record<string,unknown>[]};
type Suggestions={provider:string;proposals:{required_field:string;source_column:string;confidence:number;reason:string}[];unresolved:string[];privacy_note:string};
type PartnerInspection={filename:string;rows:number;columns:string[];suggestions:Record<string,{source:string;score:number}>;mapping_confidence:number;defaults:Record<string,string>;target_fields:string[];preview:Record<string,unknown>[];diagnostics:Record<string,unknown>};
type Tab="Readiness"|"Import Retail Data"|"Import Production Data"|"History";

const PUBLISH_ROLES=new Set(["dev","admin","buyer","planner","supervisor","operator","qa","trial"]);
const ARCHIVE_ROLES=new Set(["dev","admin","supervisor"]);

export function DataSettingsPage({onNavigate}:{onNavigate?:(page:string)=>void}){
  const client=useQueryClient();
  const [tab,setTab]=useState<Tab>("Readiness");
  const [datasetKey,setDatasetKey]=useState("inventory");
  const [file,setFile]=useState<File|null>(null);
  const [inspection,setInspection]=useState<Inspection|null>(null);
  const [mapping,setMapping]=useState<Record<string,string>>({});
  const [confirmed,setConfirmed]=useState(false);
  const [message,setMessage]=useState("");
  const data=useQuery({queryKey:["data-hub"],queryFn:({signal})=>apiGet<DataHub>("/api/v1/data-hub/datasets",signal)});
  const account=useQuery({queryKey:["account-context"],queryFn:({signal})=>apiGet<Account>("/api/v1/account/context",signal)});
  const role=account.data?.user.role??"";
  const spec=data.data?.catalog.find(row=>row.dataset_key===datasetKey)??data.data?.catalog[0];
  const active=data.data?.history.find(row=>row.dataset_key===datasetKey&&row.status==="active");
  const inspect=useMutation({
    mutationFn:async(next:File)=>{const body=new FormData();body.set("dataset_key",datasetKey);body.set("file",next);return apiPostForm<Inspection>("/api/v1/data-hub/datasets/inspect",body)},
    onSuccess:value=>{setInspection(value);setMapping(value.matches);setConfirmed(false);setMessage("")},
  });
  const suggest=useMutation({
    mutationFn:()=>apiPost<Suggestions>("/api/v1/data-hub/datasets/mapping-suggestions",{dataset_key:datasetKey,columns:inspection?.source_columns??[],existing_matches:mapping}),
    onSuccess:value=>setMapping(current=>({...current,...Object.fromEntries(value.proposals.map(row=>[row.required_field,row.source_column]))})),
  });
  const publish=useMutation({
    mutationFn:async()=>{const body=new FormData();body.set("dataset_key",datasetKey);body.set("mapping_json",JSON.stringify(mapping));body.set("file",file!);return apiPostForm<History>("/api/v1/data-hub/datasets/publish",body)},
    onSuccess:async()=>{setMessage(`${inspection?.name} is saved to Supabase and available across Retail Operations.`);setConfirmed(false);await client.invalidateQueries({queryKey:["data-hub"]})},
  });
  const archive=useMutation({
    mutationFn:()=>apiPost<{archived:number}>("/api/v1/data-hub/archive",{}),
    onSuccess:async result=>{setMessage(`${result.archived} active source(s) archived.`);await client.invalidateQueries({queryKey:["data-hub"]})},
  });
  const duplicate=Object.values(mapping).filter(Boolean).length!==new Set(Object.values(mapping).filter(Boolean)).size;
  const missing=inspection?.requirements.filter(field=>!mapping[field])??[];
  const ready=Boolean(file&&inspection&&confirmed&&!missing.length&&!duplicate);
  const status=data.data?.status??[];
  const readyCount=status.filter(row=>row.status==="Ready").length;
  const retailReady=status.filter(row=>row.operations==="Retail Ops"&&row.status==="Ready").length;
  const facility=account.data?.facilities.find(row=>row.id===account.data?.facility_id)?.name??"Not selected";
  function chooseDataset(key:string){setDatasetKey(key);setFile(null);setInspection(null);setMapping({});setConfirmed(false);setMessage("");inspect.reset();suggest.reset();publish.reset()}
  function chooseFile(next?:File){setFile(next??null);setInspection(null);setMapping({});setConfirmed(false);setMessage("");if(next)inspect.mutate(next)}
  return <div className="page exact-data-hub">
    <h1>Data Hub</h1>
    <p className="section-note">Load operational data once, verify its status, and reuse it across Retail Ops and Production Ops. Existing workspace-specific uploaders remain available.</p>
    <section className="metrics four"><Metric label="Sources Ready" value={`${readyCount}/${status.length||10}`}/><Metric label="Retail Sources" value={retailReady}/><Metric label="Extraction Runs" value={data.data?.extraction_runs??"—"}/><Metric label="Active Facility" value={facility}/></section>
    <div className="view-tabs parity-tabs data-hub-tabs" role="tablist">{(["Readiness","Import Retail Data","Import Production Data","History"] as Tab[]).map(value=><button role="tab" aria-selected={tab===value} className={tab===value?"active":""} onClick={()=>setTab(value)} key={value}>{value}</button>)}</div>
    {tab==="Readiness"?<Readiness rows={status}/>:null}
    {tab==="Import Retail Data"?<section className="data-hub-import">
      <h2>Import retail data</h2><p>Choose one source, upload it, review the detected structure, then publish it for reuse.</p>
      <label>1. Choose the dataset<select value={datasetKey} onChange={event=>chooseDataset(event.target.value)}>{data.data?.catalog.map(row=><option value={row.dataset_key} key={row.dataset_key}>{row.label}</option>)}</select></label>
      {spec?<div className="info-banner">{spec.description}</div>:null}{active?<div className="success-banner">Current source: {active.filename} · saved to Supabase</div>:null}
      {PUBLISH_ROLES.has(role)?<label className="file-drop">2. Upload the source file<input type="file" accept={spec?.types.map(value=>`.${value}`).join(",")} onChange={event=>chooseFile(event.target.files?.[0])}/></label>:<div className="info-banner">Read-only access · publishing disabled</div>}
      {!file?<p>Nothing changes until a file is uploaded and published.</p>:null}{inspect.isPending?<div className="state">Inspecting source structure…</div>:null}{inspect.isError?<div className="form-error">The file could not be inspected: {inspect.error.message}</div>:null}
      {inspection?<Review inspection={inspection} mapping={mapping} duplicate={duplicate} missing={missing} confirmed={confirmed} active={Boolean(active)} suggestions={suggest.data} suggestionPending={suggest.isPending} publishPending={publish.isPending} onMapping={(field,value)=>setMapping(current=>({...current,[field]:value}))} onSuggest={()=>suggest.mutate()} onConfirmed={setConfirmed} onPublish={()=>publish.mutate()} ready={ready}/>:null}
    </section>:null}
    {tab==="Import Production Data"?<ProductionImport onNavigate={onNavigate}/>:null}
    {tab==="History"?<section className="data-hub-history">{!data.data?.history.length?<div className="info-banner">No sources have been published for this facility yet.</div>:<HistoryTable rows={data.data.history}/>} {ARCHIVE_ROLES.has(role)?<details className="streamlit-expander"><summary>Archive durable sources</summary><div className="streamlit-expander-body"><p>Archive every currently active source for this facility. Historical revisions remain visible.</p><button className="secondary" disabled={archive.isPending} onClick={()=>archive.mutate()}>Archive active sources</button></div></details>:null}</section>:null}
    {message?<div className="success-banner">{message}</div>:null}{publish.isError||archive.isError?<div className="form-error">{publish.error?.message??archive.error?.message}</div>:null}
  </div>;
}

function Readiness({rows}:{rows:StatusRow[]}){return <section className="data-hub-readiness"><h2>Operational source status</h2>{rows.length?<Table columns={["Operations","Dataset","Status","Source","Rows","Updated"]} rows={rows.map(row=>[row.operations,row.dataset,row.status,row.source||"—",row.rows,row.updated?new Date(row.updated).toLocaleString():"—"])}/>:<div className="state">Loading source status…</div>}<div className="info-banner">Recommended flow: upload or connect a source, review its mapping and quality, then open the destination workspace to publish operational decisions.</div></section>}

function Review({inspection,mapping,duplicate,missing,confirmed,active,suggestions,suggestionPending,publishPending,onMapping,onSuggest,onConfirmed,onPublish,ready}:{inspection:Inspection;mapping:Record<string,string>;duplicate:boolean;missing:string[];confirmed:boolean;active:boolean;suggestions?:Suggestions;suggestionPending:boolean;publishPending:boolean;onMapping:(field:string,value:string)=>void;onSuggest:()=>void;onConfirmed:(value:boolean)=>void;onPublish:()=>void;ready:boolean}){return <section className="data-hub-review">
  <h3>3. Review detected structure</h3><section className="metrics three"><Metric label="Rows" value={inspection.rows.toLocaleString()}/><Metric label="Columns" value={inspection.columns}/><Metric label="Quality" value={missing.length||duplicate?"Review mapping":"Ready"}/></section>
  {inspection.missing.length?<><div className="warning-banner">These required fields were not detected automatically: {inspection.missing.join(", ")}. Use the Mapping Agent or choose the source columns manually before publishing.</div><button className="secondary" disabled={suggestionPending} onClick={onSuggest}>Ask Mapping Agent</button></>:null}
  {suggestions?.proposals.length?<><h4>Mapping Agent suggestions</h4><Table columns={["Required field","Suggested column","Confidence","Why"]} rows={suggestions.proposals.map(row=>[row.required_field,row.source_column,row.confidence,row.reason])}/><p>{suggestions.privacy_note}</p></>:null}
  <h4>Confirm column mapping</h4>{inspection.requirements.map(field=><label key={field}>{field}<select value={mapping[field]??""} onChange={event=>onMapping(field,event.target.value)}><option value="">Not mapped</option>{inspection.source_columns.map(column=><option key={column}>{column}</option>)}</select></label>)}
  {duplicate?<div className="form-error">One source column is assigned to more than one required field. Choose a unique column for each field.</div>:!missing.length?<div className="success-banner">Required fields are mapped and ready to normalize for Buyer Dashboard.</div>:null}
  <details className="streamlit-expander" open={Boolean(missing.length)}><summary>Preview first 8 rows</summary><div className="streamlit-expander-body"><ObjectTable rows={inspection.preview}/></div></details>
  <label className="toggle"><input type="checkbox" checked={confirmed} onChange={event=>onConfirmed(event.target.checked)}/>I reviewed the source and want it available to Retail Operations.</label><button className="primary" disabled={!ready||publishPending} onClick={onPublish}>4. {active?"Replace current source":"Publish source"}</button>
</section>}

function ProductionImport({onNavigate}:{onNavigate?:(page:string)=>void}){
  const client=useQueryClient();
  const [file,setFile]=useState<File|null>(null);
  const [inspection,setInspection]=useState<PartnerInspection|null>(null);
  const [mapping,setMapping]=useState<Record<string,string>>({});
  const [defaults,setDefaults]=useState({method:"BHO",state:"MA",client_name:"In House",status:"Processing",coa_status:"Pending"});
  const inspect=useMutation({
    mutationFn:async(next:File)=>{const body=new FormData();body.set("file",next);return apiPostForm<PartnerInspection>("/api/v1/extraction-parity/partner-import/inspect",body)},
    onSuccess:value=>{setInspection(value);setMapping(Object.fromEntries(Object.entries(value.suggestions).map(([field,suggestion])=>[field,suggestion.source])))},
  });
  const publish=useMutation({
    mutationFn:async()=>{const body=new FormData();body.set("file",file!);body.set("mapping_json",JSON.stringify(mapping));body.set("defaults_json",JSON.stringify(defaults));return apiPostForm<{added:number;duplicates:number;rows:number;filename:string}>("/api/v1/extraction-parity/partner-import/publish",body)},
    onSuccess:()=>{client.invalidateQueries({queryKey:["data-hub"]});client.invalidateQueries({queryKey:["extraction-parity-overview"]});client.invalidateQueries({queryKey:["extraction-runs"]})},
  });
  const mapped=inspection?mapPartnerPreview(inspection.preview,inspection.target_fields,mapping,defaults):[];
  return <section className="data-hub-import production-import">
    <h2>Production Ops source intake</h2><p>Extraction run imports use automatic header detection, field mapping, deduplication, and a review preview before rows are appended.</p><h3>Raw Data Upload Staging</h3>
    <label className="file-drop">Upload extraction runs file<input type="file" accept=".csv,.xlsx,.xls" onChange={event=>{const next=event.target.files?.[0]??null;setFile(next);setInspection(null);if(next)inspect.mutate(next)}}/></label>
    {inspect.isPending?<div className="state">Inspecting extraction run log…</div>:null}{inspect.isError?<div className="form-error">Could not read uploaded run log: {inspect.error.message}</div>:null}
    {inspection?<><h4>Default values for missing mapped fields</h4><div className="form-grid three">
      <label>Default Method<select value={defaults.method} onChange={event=>setDefaults({...defaults,method:event.target.value})}>{["BHO","CO2","Rosin","Ethanol"].map(value=><option key={value}>{value}</option>)}</select></label>
      <label>Default State<select value={defaults.state} onChange={event=>setDefaults({...defaults,state:event.target.value})}>{["MA","ME","NY","NJ","MI","NV","CA","Other"].map(value=><option key={value}>{value}</option>)}</select></label>
      <label>Default Client Name<input value={defaults.client_name} onChange={event=>setDefaults({...defaults,client_name:event.target.value})}/></label>
      <label>Default Status<select value={defaults.status} onChange={event=>setDefaults({...defaults,status:event.target.value})}>{["Processing","Queued","Complete","Hold","Failed"].map(value=><option key={value}>{value}</option>)}</select></label>
      <label>Default COA Status<select value={defaults.coa_status} onChange={event=>setDefaults({...defaults,coa_status:event.target.value})}>{["Pending","Passed","Failed","Not Submitted"].map(value=><option key={value}>{value}</option>)}</select></label>
    </div>{inspection.mapping_confidence<.75?<><div className="warning-banner">Auto-mapping confidence is low. Please confirm field mapping.</div><div className="partner-mapping">{inspection.target_fields.map(field=><label key={field}>{field} → source column<select value={mapping[field]??"IGNORE"} onChange={event=>setMapping(current=>({...current,[field]:event.target.value}))}><option>IGNORE</option>{inspection.columns.map(column=><option key={column}>{column}</option>)}</select>{mapping[field]&&mapping[field]!=="IGNORE"?<small>Sample values: {inspection.preview.slice(0,3).map(row=>String(row[mapping[field]]??"")).filter(Boolean).join(", ")||"—"}</small>:null}</label>)}</div></>:<div className="success-banner">Auto-mapping confidence: {inspection.mapping_confidence.toFixed(2)}</div>}
      <p>Mapped run preview</p><ObjectTable rows={mapped}/><button className="primary" disabled={publish.isPending} onClick={()=>publish.mutate()}>Append mapped runs to Extraction Command Center</button>
      {publish.data?<><div className="success-banner">Added {publish.data.added} runs to Extraction Command Center</div>{publish.data.duplicates?<div className="info-banner">Skipped {publish.data.duplicates} duplicate runs based on run_date + batch_id_internal + method.</div>:null}</>:null}{publish.isError?<div className="form-error">{publish.error.message}</div>:null}
      <details className="streamlit-expander"><summary>Upload diagnostics</summary><div className="streamlit-expander-body"><pre className="readiness-json">{JSON.stringify(inspection.diagnostics,null,2)}</pre></div></details></>:null}
    <hr/><h3>Co-Man durable data</h3><div className="success-banner">Organization and facility are selected. Products, lots, customers, machines, schedules, and production history are stored in Supabase.</div><p>Use Co-Man Production for product, lot, BOM, machine, crew, and customer setup. Those records are master data and should be entered once, not re-uploaded per job.</p><button className="secondary" onClick={()=>onNavigate?.("Production")}>Open Co-Man Production</button>
  </section>;
}

function mapPartnerPreview(rows:Record<string,unknown>[],fields:string[],mapping:Record<string,string>,defaults:Record<string,string>){return rows.map(row=>{const mapped=Object.fromEntries(fields.map(field=>{const source=mapping[field];let value=source&&source!=="IGNORE"?row[source]:defaults[field]??"";if(["input_weight_g","intermediate_output_g","finished_output_g","residual_loss_g","yield_pct","post_process_efficiency_pct"].includes(field))value=Number(value)||0;return [field,value]}));if(!mapped.yield_pct&&mapped.input_weight_g)mapped.yield_pct=Number(mapped.finished_output_g)/Number(mapped.input_weight_g)*100;if(!mapped.post_process_efficiency_pct&&mapped.intermediate_output_g)mapped.post_process_efficiency_pct=Number(mapped.finished_output_g)/Number(mapped.intermediate_output_g)*100;return mapped})}
function Metric({label,value}:{label:string;value:string|number}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function HistoryTable({rows}:{rows:History[]}){return <Table columns={["Dataset","File","Size","Status","Imported At","Imported By","Rows"]} rows={rows.map(row=>[row.dataset_label,row.filename,`${(row.payload_size/1024).toFixed(0)} KB`,title(row.status),new Date(row.activated_at).toLocaleString(),row.imported_by||"—",row.row_count])}/>}
function ObjectTable({rows}:{rows:Record<string,unknown>[]}){const columns=Object.keys(rows[0]??{});return <Table columns={columns} rows={rows.map(row=>columns.map(column=>String(row[column]??"—")))}/>}
function Table({columns,rows}:{columns:string[];rows:(string|number)[][]}){return <div className="table-wrap"><table><thead><tr>{columns.map(value=><th key={value}>{value}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{row.map((value,column)=><td key={columns[column]}>{value}</td>)}</tr>)}</tbody></table></div>}
function title(value:string){return value.replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
