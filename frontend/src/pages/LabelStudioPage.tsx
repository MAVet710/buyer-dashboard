import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDownload, apiGet, apiPost, apiPostForm } from "../lib/api";

type Rule = { key:string;kind:string;field?:string;value?:string|number;severity:"warning"|"fail";message:string;source?:string };
type Template = { id:string;name:string;version:number;jurisdiction:string;license_scope:string;status:string;layout:Record<string,unknown>;rules:Rule[] };
type Review = { id:string;status:"pass"|"warning"|"fail";reviewed_at:string;findings:Array<{key:string;status:string;message:string;field:string;source:string}>;disclaimer:string };
type CoaResult = { analysis:string;key:string;name:string;value:number|null;value_text:string;units:string;mg_g:number|null;limit:number|null;lod:number|null;loq:number|null;status:string };
type CoaSource = {
  available:boolean;lookup_key:string;fallback_allowed:boolean;needs_confirmation:boolean;document_id:string;source:string;status:string;verification_state:string;
  filename:string;file_url:string;lab_name:string;lab_license_number:string;lab_id:string;metrc_source_id:string;metrc_lab_id:string;date_tested:string;overall_status:string;
  total_thc:number|null;total_cbd:number|null;total_cannabinoids:number|null;total_terpenes:number|null;results:CoaResult[];
};
type InventoryLabelSource = {
  lot_id:string;product_id:string;package_id:string;lot_code:string;product_name:string;sku:string;location:string;status:string;
  on_hand:number;inventory_unit:string;label:Record<string,string>;coa:CoaSource;raw_text:string;
  source_summary:{facility:string;license_number:string;license_type:string;qa_source:string;coa_source:string;coa_verification:string};
};
type CoaMutationResult = { coa_document:Record<string,unknown>;source:InventoryLabelSource };

const FIELD_OPTIONS = [
  ["product_name","Product identity"],
  ["brand","Brand"],
  ["strain","Strain"],
  ["product_type","Product type / category"],
  ["net_contents","Net contents"],
  ["license_number","License / registration"],
  ["facility_name","Facility / manufacturer"],
  ["manufacturer","Manufacturer"],
  ["package_id","Package / traceability ID"],
  ["batch_number","Batch / lot number"],
  ["potency","Potency statement"],
  ["total_thc","Total THC"],
  ["total_cbd","Total CBD"],
  ["total_cannabinoids","Total cannabinoids / TAC"],
  ["total_terpenes","Total terpenes"],
  ["lab_testing_state","Lab testing state"],
  ["laboratory","Testing laboratory"],
  ["test_date","Test date"],
  ["coa_reference","COA reference"],
  ["ingredients","Ingredients"],
  ["allergens","Allergen statement"],
  ["harvest_date","Harvest date"],
  ["manufacture_date","Manufacture date"],
  ["package_date","Package date"],
  ["expiration_date","Expiration / best-by"],
  ["warning_text","Warning statement"],
] as const;

const PREVIEW_FIELDS = [
  "brand","strain","product_type","net_contents","potency","total_thc","total_cbd","total_cannabinoids","total_terpenes","license_number","facility_name","manufacturer","package_id","batch_number",
  "lab_testing_state","laboratory","test_date","coa_reference","ingredients","allergens","harvest_date","manufacture_date","package_date","expiration_date","warning_text",
] as const;

function fieldLabel(field:string){return FIELD_OPTIONS.find(item=>item[0]===field)?.[1]??field.replaceAll("_"," ");}
function templateFields(template:Template|null){const value=template?.layout?.fields;return Array.isArray(value)?value.filter((item):item is string=>typeof item==="string"):[];}
function sourceLabel(source:InventoryLabelSource){const packageRef=source.package_id||source.lot_code;return `${source.product_name} · ${source.lot_code}${packageRef&&packageRef!==source.lot_code?` · ${packageRef}`:""}`;}
function resultDisplay(result:CoaResult){if(result.value_text)return `${result.value_text}${result.units&&!result.value_text.includes(result.units)?` ${result.units}`:""}`;if(result.value==null)return "—";return `${result.value}${result.units?` ${result.units}`:""}`;}

export function LabelStudioPage(){
  const client=useQueryClient();
  const templates=useQuery({queryKey:["label-studio-templates"],queryFn:({signal})=>apiGet<Template[]>("/api/v1/control-tower/label-templates",signal)});
  const inventory=useQuery({queryKey:["label-studio-inventory-sources"],queryFn:({signal})=>apiGet<InventoryLabelSource[]>("/api/v1/label-printing/inventory-sources",signal)});
  const [name,setName]=useState(""); const [jurisdiction,setJurisdiction]=useState(""); const [scope,setScope]=useState(""); const [source,setSource]=useState("");
  const [required,setRequired]=useState<string[]>(["product_name","net_contents","license_number","warning_text"]); const [contains,setContains]=useState(""); const [containsSource,setContainsSource]=useState("");
  const [selected,setSelected]=useState(""); const [inventoryLotId,setInventoryLotId]=useState(""); const [fields,setFields]=useState<Record<string,string>>({}); const [rawText,setRawText]=useState("");
  const [coaMessage,setCoaMessage]=useState("");
  const active=useMemo(()=>templates.data?.find(row=>row.id===selected)??null,[templates.data,selected]);
  const activeSource=useMemo(()=>inventory.data?.find(row=>row.lot_id===inventoryLotId)??null,[inventory.data,inventoryLotId]);
  const rules=useMemo<Rule[]>(()=>[
    ...required.map(field=>({key:`required-${field}`,kind:"required_field",field,severity:"fail" as const,message:`${fieldLabel(field)} is present.`,source})),
    ...(contains.trim()?[{key:"required-warning-language",kind:"contains",field:"warning_text",value:contains.trim(),severity:"fail" as const,message:"Configured required warning language is present.",source:containsSource||source}]:[]),
  ],[required,contains,containsSource,source]);
  const requiredForReview=useMemo(()=>{const configured=templateFields(active);return configured.length?configured:required},[active,required]);
  const missingRequired=useMemo(()=>requiredForReview.filter(field=>!String(fields[field]??"").trim()),[fields,requiredForReview]);
  const populatedCount=useMemo(()=>FIELD_OPTIONS.filter(([field])=>String(fields[field]??"").trim()).length,[fields]);
  const cannabinoids=useMemo(()=>activeSource?.coa.results.filter(row=>row.analysis==="cannabinoids")??[],[activeSource]);
  const terpenes=useMemo(()=>activeSource?.coa.results.filter(row=>row.analysis==="terpenes")??[],[activeSource]);
  const create=useMutation({mutationFn:()=>apiPost("/api/v1/control-tower/label-templates",{name,jurisdiction,license_scope:scope,layout:{fields:required},rules,activate:true}),onSuccess:()=>{setName("");void client.invalidateQueries({queryKey:["label-studio-templates"]});}});
  const review=useMutation({mutationFn:()=>apiPost<Review>("/api/v1/control-tower/label-reviews",{template_id:selected||null,product_id:activeSource?.product_id??null,package_id:activeSource?.package_id??fields.package_id??"",label:{...fields,raw_text:rawText},rules:selected?[]:rules,rule_set_reference:selected?"":`${name||"Ad hoc"} configured review`})});
  const syncSource=(next:InventoryLabelSource)=>{
    client.setQueryData<InventoryLabelSource[]>(["label-studio-inventory-sources"],rows=>rows?.map(row=>row.lot_id===next.lot_id?next:row)??[next]);
    setFields({...next.label});setRawText(next.raw_text);review.reset();
  };
  const uploadCoa=useMutation({
    mutationFn:async(file:File)=>{if(!inventoryLotId)throw new Error("Choose an inventory batch first.");const body=new FormData();body.set("file",file);return apiPostForm<CoaMutationResult>(`/api/v1/label-printing/inventory-sources/${encodeURIComponent(inventoryLotId)}/coa`,body)},
    onSuccess:value=>{syncSource(value.source);setCoaMessage(value.source.coa.needs_confirmation?"COA parsed. The METRC tag was not readable in the PDF, so explicit confirmation is required before it becomes the label source.":"COA matched to the selected METRC tag and is now the label test source.")},
  });
  const confirmCoa=useMutation({
    mutationFn:()=>{if(!inventoryLotId||!activeSource?.coa.document_id)throw new Error("No pending COA is available to confirm.");return apiPost<CoaMutationResult>(`/api/v1/label-printing/inventory-sources/${encodeURIComponent(inventoryLotId)}/coa/${encodeURIComponent(activeSource.coa.document_id)}/confirm`,{})},
    onSuccess:value=>{syncSource(value.source);setCoaMessage("COA association confirmed for this METRC package tag.")},
  });
  const toggle=(field:string)=>setRequired(current=>current.includes(field)?current.filter(value=>value!==field):[...current,field]);
  const chooseInventorySource=(lotId:string)=>{
    setInventoryLotId(lotId); review.reset();setCoaMessage("");uploadCoa.reset();confirmCoa.reset();
    const next=inventory.data?.find(row=>row.lot_id===lotId);
    if(!next){setFields({});setRawText("");return;}
    setFields({...next.label});setRawText(next.raw_text);
    const activeTemplates=templates.data?.filter(row=>row.status==="active")??[];
    if(!selected&&activeTemplates.length===1)setSelected(activeTemplates[0].id);
  };
  const openCoa=async()=>{
    if(!activeSource?.coa.file_url)return;
    const blob=await apiDownload(activeSource.coa.file_url);
    const url=URL.createObjectURL(blob);window.open(url,"_blank","noopener,noreferrer");window.setTimeout(()=>URL.revokeObjectURL(url),60_000);
  };
  const canPrint=Boolean(Object.keys(fields).length&&!missingRequired.length&&review.data&&review.data.status!=="fail"&&!activeSource?.coa.needs_confirmation);
  return <div className="page"><div className="eyebrow">COMPLIANCE · LABELS</div><h1>Label Studio + LabelGuard</h1><p className="section-note">Select an inventory batch to build the label from Product Master, the active facility, its METRC package tag, and the COA already indexed to that exact tag. COA test results are normalized into individual analytes and totals. Manual COA upload only appears when automatic package matching has no usable certificate.</p>
    <div className="view-tabs parity-tabs"><button className="active" type="button">Build & review</button><button type="button" disabled={!canPrint} title={canPrint?"Print reviewed label preview":activeSource?.coa.needs_confirmation?"Confirm the pending COA association before printing":missingRequired.length?`Complete required fields: ${missingRequired.map(fieldLabel).join(", ")}`:"Run LabelGuard before printing"} onClick={()=>window.print()}>Print reviewed preview</button></div>

    <section className="inventory-panel"><div className="eyebrow">BUILD FROM INVENTORY</div><h2>Select a batch or package</h2><p className="section-note">Only on-hand inventory in the active facility is available here. The METRC package/tag on the selected lot is the COA lookup key.</p>
      {inventory.isLoading?<div className="state">Loading active-facility inventory…</div>:null}{inventory.isError?<div className="form-error">{inventory.error.message}</div>:null}
      {inventory.data?<div className="form-grid two"><label className="full">Inventory batch<select value={inventoryLotId} onChange={event=>chooseInventorySource(event.target.value)}><option value="">Choose a batch or package…</option>{inventory.data.map(row=><option value={row.lot_id} key={row.lot_id}>{sourceLabel(row)}</option>)}</select></label></div>:null}
      {inventory.data&&!inventory.data.length?<div className="info-banner">No on-hand inventory batches were found in this facility.</div>:null}
      {activeSource?<><div className="metrics four"><Metric label="Product" value={activeSource.product_name}/><Metric label="Batch" value={activeSource.lot_code}/><Metric label="On hand" value={`${activeSource.on_hand.toLocaleString()} ${activeSource.inventory_unit}`}/><Metric label="Location" value={activeSource.location||"—"}/></div><div className={missingRequired.length?"warning-banner":"success-banner"}><strong>{populatedCount} label fields populated from inventory.</strong> {missingRequired.length?<>Required information still missing: {missingRequired.map(fieldLabel).join(", ")}. Complete or correct the source data before final release.</>:<>All fields required by the current rule set are populated.</>}</div><p className="section-note">Source: {activeSource.source_summary.facility}{activeSource.source_summary.license_number?` · ${activeSource.source_summary.license_number}`:""}{activeSource.source_summary.qa_source?` · QA ${activeSource.source_summary.qa_source}`:""}</p></>:null}
    </section>

    {activeSource?<section className="inventory-panel"><div className="eyebrow">COA SOURCE</div><h2>Test results for {activeSource.package_id||"this inventory batch"}</h2>
      {activeSource.coa.available?<><div className="success-banner"><strong>Matched automatically by METRC package tag.</strong> {activeSource.coa.filename||"Stored COA"} is the test source for this working label. {activeSource.coa.lab_name?`Laboratory: ${activeSource.coa.lab_name}.`:""}</div><div className="audit-actions"><button className="secondary" type="button" onClick={()=>void openCoa()}>Open source COA</button></div></>:null}
      {activeSource.coa.needs_confirmation?<div className="warning-banner"><strong>COA parsed, identity confirmation required.</strong> The PDF did not expose a readable METRC tag. Confirm only if this certificate belongs to <strong>{activeSource.package_id}</strong>. A certificate that contains a different METRC tag is rejected before this stage.<div className="audit-actions"><button className="primary" disabled={confirmCoa.isPending} type="button" onClick={()=>confirmCoa.mutate()}>{confirmCoa.isPending?"Confirming…":"Confirm COA for this tag"}</button><button className="secondary" type="button" onClick={()=>void openCoa()}>Review PDF first</button></div></div>:null}
      {!activeSource.coa.available&&!activeSource.coa.needs_confirmation&&activeSource.package_id?<div className="info-banner"><strong>No stored COA matched METRC tag {activeSource.package_id}.</strong> Label Studio did not substitute METRC lab rows or another batch's certificate. Use the PDF fallback below only for the COA that belongs to this package.</div>:null}
      {!activeSource.package_id?<div className="warning-banner"><strong>No METRC package/tag is stored on this inventory lot.</strong> Automatic COA matching and fallback attachment stay disabled until traceability identity is present.</div>:null}
      {!activeSource.coa.available&&!activeSource.coa.needs_confirmation&&activeSource.package_id?<label className="file-drop">Fallback: upload the COA for {activeSource.package_id}<input type="file" accept="application/pdf,.pdf" disabled={uploadCoa.isPending} onChange={event=>{const file=event.target.files?.[0];if(file)uploadCoa.mutate(file);event.currentTarget.value=""}}/></label>:null}
      {uploadCoa.isPending?<div className="state">Reading COA and verifying the METRC package tag…</div>:null}{uploadCoa.isError?<div className="form-error">{uploadCoa.error.message}</div>:null}{confirmCoa.isError?<div className="form-error">{confirmCoa.error.message}</div>:null}{coaMessage?<div className="success-banner">{coaMessage}</div>:null}
      {activeSource.coa.document_id?<><div className="metrics four"><Metric label="COA status" value={activeSource.coa.overall_status||activeSource.coa.status}/><Metric label="Test date" value={activeSource.coa.date_tested||"—"}/><Metric label="Total THC" value={activeSource.coa.total_thc==null?"—":`${activeSource.coa.total_thc}%`}/><Metric label="Total terpenes" value={activeSource.coa.total_terpenes==null?"—":`${activeSource.coa.total_terpenes}%`}/></div>{cannabinoids.length?<AnalyteTable title="Cannabinoids" rows={cannabinoids}/>:null}{terpenes.length?<AnalyteTable title="Terpenes" rows={terpenes}/>:null}</>:null}
    </section>:null}

    <div className="two-column-grid"><section className="inventory-panel"><div className="eyebrow">VERSIONED RULE SET</div><h2>Create an approved label template</h2><div className="form-grid two"><label>Template name<input value={name} onChange={e=>setName(e.target.value)} placeholder="MA Adult Use Retail Label"/></label><label>Jurisdiction<input value={jurisdiction} onChange={e=>setJurisdiction(e.target.value)} placeholder="Massachusetts"/></label><label>License scope<input value={scope} onChange={e=>setScope(e.target.value)} placeholder="Adult Use / Manufacturing"/></label><label>Source / citation<input value={source} onChange={e=>setSource(e.target.value)} placeholder="Approved regulation or SOP reference"/></label><label className="full">Required warning phrase<input value={contains} onChange={e=>setContains(e.target.value)} placeholder="Optional exact phrase required by the reviewed source"/></label><label className="full">Warning phrase source<input value={containsSource} onChange={e=>setContainsSource(e.target.value)} placeholder="Citation or SOP section"/></label></div><div className="inventory-panel"><strong>Required fields</strong><div className="role-home-task-grid">{FIELD_OPTIONS.map(([field,label])=><label key={field}><input type="checkbox" checked={required.includes(field)} onChange={()=>toggle(field)}/> {label}</label>)}</div></div><button className="primary" type="button" disabled={!name.trim()||create.isPending} onClick={()=>create.mutate()}>{create.isPending?"Saving…":"Save & activate template"}</button>{create.isError?<div className="form-error">{create.error.message}</div>:null}</section>
      <section className="inventory-panel"><div className="eyebrow">LIVE LABEL PREVIEW</div><h2>{fields.product_name||"Product Name"}</h2><div className="inventory-panel label-print-preview"><strong>{fields.product_name||"PRODUCT NAME"}</strong>{PREVIEW_FIELDS.map(field=>fields[field]?<p key={field}><small>{fieldLabel(field)}</small><br/>{fields[field]}</p>:null)}{cannabinoids.length?<><hr/><strong>Cannabinoids</strong>{cannabinoids.slice(0,8).map(row=><p key={row.key}><small>{row.name}</small><br/>{resultDisplay(row)}</p>)}</>:null}{terpenes.length?<><hr/><strong>Terpenes</strong>{terpenes.slice(0,8).map(row=><p key={row.key}><small>{row.name}</small><br/>{resultDisplay(row)}</p>)}</>:null}</div></section></div>
    <section className="inventory-panel"><div className="eyebrow">LABELGUARD</div><h2>Pre-release review</h2><div className="form-grid two"><label>Approved template<select value={selected} onChange={e=>{setSelected(e.target.value);review.reset()}}><option value="">Use builder rules above</option>{templates.data?.filter(row=>row.status==="active").map(row=><option value={row.id} key={row.id}>{row.name} v{row.version} · {row.jurisdiction||"Internal"}</option>)}</select></label>{FIELD_OPTIONS.map(([field,label])=><label key={field}>{label}<input value={fields[field]??""} onChange={e=>{setFields(current=>({...current,[field]:e.target.value}));review.reset()}}/></label>)}<label className="full">Extracted / rendered label text<textarea rows={6} value={rawText} onChange={e=>{setRawText(e.target.value);review.reset()}} placeholder="Inventory selection prebuilds this text; edit it if the final rendered label differs."/></label></div>{missingRequired.length?<div className="warning-banner"><strong>Not ready for release.</strong> Missing required fields: {missingRequired.map(fieldLabel).join(", ")}.</div>:null}{activeSource?.coa.needs_confirmation?<div className="warning-banner"><strong>Not ready for release.</strong> Confirm the pending COA association before running the final label review.</div>:null}<button className="primary" type="button" disabled={review.isPending||Boolean(missingRequired.length)||Boolean(activeSource?.coa.needs_confirmation)||(!selected&&!rules.length)} onClick={()=>review.mutate()}>{review.isPending?"Checking…":"Run LabelGuard"}</button>{review.isError?<div className="form-error">{review.error.message}</div>:null}{review.data?<div className="inventory-panel"><h3>{review.data.status.toUpperCase()}</h3>{review.data.findings.map(item=><div className={item.status==="fail"?"warning-banner":item.status==="warning"?"info-banner":"success-banner"} key={item.key}><strong>{item.status.toUpperCase()}</strong> · {item.message}{item.source?<><br/><small>{item.source}</small></>:null}</div>)}<p className="section-note">{review.data.disclaimer}</p></div>:null}{active?<p className="section-note">Reviewing against {active.name} v{active.version} ({active.jurisdiction||"internal scope"}).</p>:null}</section>
  </div>;
}

function AnalyteTable({title,rows}:{title:string;rows:CoaResult[]}){return <details className="streamlit-expander" open><summary>{title} · {rows.length} result{rows.length===1?"":"s"}</summary><div className="streamlit-expander-body"><div className="table-wrap"><table><thead><tr><th>Analyte</th><th>Result</th><th>Status</th></tr></thead><tbody>{rows.map(row=><tr key={row.key}><td>{row.name}</td><td>{resultDisplay(row)}</td><td>{row.status||"—"}</td></tr>)}</tbody></table></div></div></details>}
function Metric({label,value}:{label:string;value:string}){return <div className="metric"><span>{label}</span><strong>{value}</strong></div>}
