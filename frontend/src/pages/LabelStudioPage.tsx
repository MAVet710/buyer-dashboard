import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type Rule = { key:string;kind:string;field?:string;value?:string|number;severity:"warning"|"fail";message:string;source?:string };
type Template = { id:string;name:string;version:number;jurisdiction:string;license_scope:string;status:string;layout:Record<string,unknown>;rules:Rule[] };
type Review = { id:string;status:"pass"|"warning"|"fail";reviewed_at:string;findings:Array<{key:string;status:string;message:string;field:string;source:string}>;disclaimer:string };
type InventoryLabelSource = {
  lot_id:string;product_id:string;package_id:string;lot_code:string;product_name:string;sku:string;location:string;status:string;
  on_hand:number;inventory_unit:string;label:Record<string,string>;raw_text:string;
  source_summary:{facility:string;license_number:string;license_type:string;qa_source:string};
};

const FIELD_OPTIONS = [
  ["product_name","Product identity"],
  ["brand","Brand"],
  ["strain","Strain"],
  ["product_type","Product type / category"],
  ["net_contents","Net contents"],
  ["license_number","License / registration"],
  ["facility_name","Facility / manufacturer"],
  ["package_id","Package / traceability ID"],
  ["batch_number","Batch / lot number"],
  ["potency","Potency statement"],
  ["lab_testing_state","Lab testing state"],
  ["laboratory","Testing laboratory"],
  ["test_date","Test date"],
  ["coa_reference","COA reference"],
  ["ingredients","Ingredients"],
  ["allergens","Allergen statement"],
  ["manufacture_date","Manufacture date"],
  ["package_date","Package date"],
  ["expiration_date","Expiration / best-by"],
  ["warning_text","Warning statement"],
] as const;

const PREVIEW_FIELDS = [
  "brand","strain","product_type","net_contents","potency","license_number","facility_name","package_id","batch_number",
  "lab_testing_state","laboratory","test_date","coa_reference","ingredients","allergens","manufacture_date","package_date","expiration_date","warning_text",
] as const;

function fieldLabel(field:string){return FIELD_OPTIONS.find(item=>item[0]===field)?.[1]??field.replaceAll("_"," ");}
function templateFields(template:Template|null){const value=template?.layout?.fields;return Array.isArray(value)?value.filter((item):item is string=>typeof item==="string"):[];}
function sourceLabel(source:InventoryLabelSource){const packageRef=source.package_id||source.lot_code;return `${source.product_name} · ${source.lot_code}${packageRef&&packageRef!==source.lot_code?` · ${packageRef}`:""}`;}

export function LabelStudioPage(){
  const client=useQueryClient();
  const templates=useQuery({queryKey:["label-studio-templates"],queryFn:({signal})=>apiGet<Template[]>("/api/v1/control-tower/label-templates",signal)});
  const inventory=useQuery({queryKey:["label-studio-inventory-sources"],queryFn:({signal})=>apiGet<InventoryLabelSource[]>("/api/v1/label-printing/inventory-sources",signal)});
  const [name,setName]=useState(""); const [jurisdiction,setJurisdiction]=useState(""); const [scope,setScope]=useState(""); const [source,setSource]=useState("");
  const [required,setRequired]=useState<string[]>(["product_name","net_contents","license_number","warning_text"]); const [contains,setContains]=useState(""); const [containsSource,setContainsSource]=useState("");
  const [selected,setSelected]=useState(""); const [inventoryLotId,setInventoryLotId]=useState(""); const [fields,setFields]=useState<Record<string,string>>({}); const [rawText,setRawText]=useState("");
  const active=useMemo(()=>templates.data?.find(row=>row.id===selected)??null,[templates.data,selected]);
  const activeSource=useMemo(()=>inventory.data?.find(row=>row.lot_id===inventoryLotId)??null,[inventory.data,inventoryLotId]);
  const rules=useMemo<Rule[]>(()=>[
    ...required.map(field=>({key:`required-${field}`,kind:"required_field",field,severity:"fail" as const,message:`${fieldLabel(field)} is present.`,source})),
    ...(contains.trim()?[{key:"required-warning-language",kind:"contains",field:"warning_text",value:contains.trim(),severity:"fail" as const,message:"Configured required warning language is present.",source:containsSource||source}]:[]),
  ],[required,contains,containsSource,source]);
  const requiredForReview=useMemo(()=>{const configured=templateFields(active);return configured.length?configured:required},[active,required]);
  const missingRequired=useMemo(()=>requiredForReview.filter(field=>!String(fields[field]??"").trim()),[fields,requiredForReview]);
  const populatedCount=useMemo(()=>FIELD_OPTIONS.filter(([field])=>String(fields[field]??"").trim()).length,[fields]);
  const create=useMutation({mutationFn:()=>apiPost("/api/v1/control-tower/label-templates",{name,jurisdiction,license_scope:scope,layout:{fields:required},rules,activate:true}),onSuccess:()=>{setName("");void client.invalidateQueries({queryKey:["label-studio-templates"]});}});
  const review=useMutation({mutationFn:()=>apiPost<Review>("/api/v1/control-tower/label-reviews",{template_id:selected||null,product_id:activeSource?.product_id??null,package_id:activeSource?.package_id??fields.package_id??"",label:{...fields,raw_text:rawText},rules:selected?[]:rules,rule_set_reference:selected?"":`${name||"Ad hoc"} configured review`})});
  const toggle=(field:string)=>setRequired(current=>current.includes(field)?current.filter(value=>value!==field):[...current,field]);
  const chooseInventorySource=(lotId:string)=>{
    setInventoryLotId(lotId); review.reset();
    const next=inventory.data?.find(row=>row.lot_id===lotId);
    if(!next){setFields({});setRawText("");return;}
    setFields({...next.label});setRawText(next.raw_text);
    const activeTemplates=templates.data?.filter(row=>row.status==="active")??[];
    if(!selected&&activeTemplates.length===1)setSelected(activeTemplates[0].id);
  };
  const canPrint=Boolean(Object.keys(fields).length&&!missingRequired.length&&review.data&&review.data.status!=="fail");
  return <div className="page"><div className="eyebrow">COMPLIANCE · LABELS</div><h1>Label Studio + LabelGuard</h1><p className="section-note">Select an inventory batch to build the label from the facility, product master, traceability package, and QA/COA records already in DoobieLogic. Missing regulated fields stay visible instead of being guessed. Then review the completed label against the approved rule set before release.</p>
    <div className="view-tabs parity-tabs"><button className="active" type="button">Build & review</button><button type="button" disabled={!canPrint} title={canPrint?"Print reviewed label preview":missingRequired.length?`Complete required fields: ${missingRequired.map(fieldLabel).join(", ")}`:"Run LabelGuard before printing"} onClick={()=>window.print()}>Print reviewed preview</button></div>

    <section className="inventory-panel"><div className="eyebrow">BUILD FROM INVENTORY</div><h2>Select a batch or package</h2><p className="section-note">Only on-hand inventory in the active facility is available here. Choosing a batch replaces the working label with the current authoritative inventory record.</p>
      {inventory.isLoading?<div className="state">Loading active-facility inventory…</div>:null}{inventory.isError?<div className="form-error">{inventory.error.message}</div>:null}
      {inventory.data?<div className="form-grid two"><label className="full">Inventory batch<select value={inventoryLotId} onChange={event=>chooseInventorySource(event.target.value)}><option value="">Choose a batch or package…</option>{inventory.data.map(row=><option value={row.lot_id} key={row.lot_id}>{sourceLabel(row)}</option>)}</select></label></div>:null}
      {inventory.data&&!inventory.data.length?<div className="info-banner">No on-hand inventory batches were found in this facility.</div>:null}
      {activeSource?<><div className="metrics four"><Metric label="Product" value={activeSource.product_name}/><Metric label="Batch" value={activeSource.lot_code}/><Metric label="On hand" value={`${activeSource.on_hand.toLocaleString()} ${activeSource.inventory_unit}`}/><Metric label="Location" value={activeSource.location||"—"}/></div><div className={missingRequired.length?"warning-banner":"success-banner"}><strong>{populatedCount} label fields populated from inventory.</strong> {missingRequired.length?<>Required information still missing: {missingRequired.map(fieldLabel).join(", ")}. Complete or correct the source data before final release.</>:<>All fields required by the current rule set are populated.</>}</div><p className="section-note">Source: {activeSource.source_summary.facility}{activeSource.source_summary.license_number?` · ${activeSource.source_summary.license_number}`:""}{activeSource.source_summary.qa_source?` · QA ${activeSource.source_summary.qa_source}`:""}</p></>:null}
    </section>

    <div className="two-column-grid"><section className="inventory-panel"><div className="eyebrow">VERSIONED RULE SET</div><h2>Create an approved label template</h2><div className="form-grid two"><label>Template name<input value={name} onChange={e=>setName(e.target.value)} placeholder="MA Adult Use Retail Label"/></label><label>Jurisdiction<input value={jurisdiction} onChange={e=>setJurisdiction(e.target.value)} placeholder="Massachusetts"/></label><label>License scope<input value={scope} onChange={e=>setScope(e.target.value)} placeholder="Adult Use / Manufacturing"/></label><label>Source / citation<input value={source} onChange={e=>setSource(e.target.value)} placeholder="Approved regulation or SOP reference"/></label><label className="full">Required warning phrase<input value={contains} onChange={e=>setContains(e.target.value)} placeholder="Optional exact phrase required by the reviewed source"/></label><label className="full">Warning phrase source<input value={containsSource} onChange={e=>setContainsSource(e.target.value)} placeholder="Citation or SOP section"/></label></div><div className="inventory-panel"><strong>Required fields</strong><div className="role-home-task-grid">{FIELD_OPTIONS.map(([field,label])=><label key={field}><input type="checkbox" checked={required.includes(field)} onChange={()=>toggle(field)}/> {label}</label>)}</div></div><button className="primary" type="button" disabled={!name.trim()||create.isPending} onClick={()=>create.mutate()}>{create.isPending?"Saving…":"Save & activate template"}</button>{create.isError?<div className="form-error">{create.error.message}</div>:null}</section>
      <section className="inventory-panel"><div className="eyebrow">LIVE LABEL PREVIEW</div><h2>{fields.product_name||"Product Name"}</h2><div className="inventory-panel label-print-preview"><strong>{fields.product_name||"PRODUCT NAME"}</strong>{PREVIEW_FIELDS.map(field=>fields[field]?<p key={field}><small>{fieldLabel(field)}</small><br/>{fields[field]}</p>:null)}</div>{activeSource?.label.coa_url?<p><a href={activeSource.label.coa_url} target="_blank" rel="noreferrer">Open source COA</a></p>:null}</section></div>
    <section className="inventory-panel"><div className="eyebrow">LABELGUARD</div><h2>Pre-release review</h2><div className="form-grid two"><label>Approved template<select value={selected} onChange={e=>{setSelected(e.target.value);review.reset()}}><option value="">Use builder rules above</option>{templates.data?.filter(row=>row.status==="active").map(row=><option value={row.id} key={row.id}>{row.name} v{row.version} · {row.jurisdiction||"Internal"}</option>)}</select></label>{FIELD_OPTIONS.map(([field,label])=><label key={field}>{label}<input value={fields[field]??""} onChange={e=>{setFields(current=>({...current,[field]:e.target.value}));review.reset()}}/></label>)}<label className="full">Extracted / rendered label text<textarea rows={6} value={rawText} onChange={e=>{setRawText(e.target.value);review.reset()}} placeholder="Inventory selection prebuilds this text; edit it if the final rendered label differs."/></label></div>{missingRequired.length?<div className="warning-banner"><strong>Not ready for release.</strong> Missing required fields: {missingRequired.map(fieldLabel).join(", ")}.</div>:null}<button className="primary" type="button" disabled={review.isPending||Boolean(missingRequired.length)||(!selected&&!rules.length)} onClick={()=>review.mutate()}>{review.isPending?"Checking…":"Run LabelGuard"}</button>{review.isError?<div className="form-error">{review.error.message}</div>:null}{review.data?<div className="inventory-panel"><h3>{review.data.status.toUpperCase()}</h3>{review.data.findings.map(item=><div className={item.status==="fail"?"warning-banner":item.status==="warning"?"info-banner":"success-banner"} key={item.key}><strong>{item.status.toUpperCase()}</strong> · {item.message}{item.source?<><br/><small>{item.source}</small></>:null}</div>)}<p className="section-note">{review.data.disclaimer}</p></div>:null}{active?<p className="section-note">Reviewing against {active.name} v{active.version} ({active.jurisdiction||"internal scope"}).</p>:null}</section>
  </div>;
}

function Metric({label,value}:{label:string;value:string}){return <div className="metric"><span>{label}</span><strong>{value}</strong></div>}
