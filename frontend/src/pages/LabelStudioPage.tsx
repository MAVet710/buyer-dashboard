import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type Rule = { key:string;kind:string;field?:string;value?:string|number;severity:"warning"|"fail";message:string;source?:string };
type Template = { id:string;name:string;version:number;jurisdiction:string;license_scope:string;status:string;layout:Record<string,unknown>;rules:Rule[] };
type Review = { id:string;status:"pass"|"warning"|"fail";reviewed_at:string;findings:Array<{key:string;status:string;message:string;field:string;source:string}>;disclaimer:string };

const BASE_FIELDS = [
  ["product_name","Product identity"],
  ["net_contents","Net contents"],
  ["license_number","License / registration"],
  ["package_id","Package / traceability ID"],
  ["ingredients","Ingredients"],
  ["allergens","Allergen statement"],
  ["potency","Potency statement"],
  ["warning_text","Warning statement"],
] as const;

export function LabelStudioPage(){
  const client=useQueryClient();
  const templates=useQuery({queryKey:["label-studio-templates"],queryFn:({signal})=>apiGet<Template[]>("/api/v1/control-tower/label-templates",signal)});
  const [name,setName]=useState(""); const [jurisdiction,setJurisdiction]=useState(""); const [scope,setScope]=useState(""); const [source,setSource]=useState("");
  const [required,setRequired]=useState<string[]>(["product_name","net_contents","license_number","warning_text"]); const [contains,setContains]=useState(""); const [containsSource,setContainsSource]=useState("");
  const [selected,setSelected]=useState(""); const [fields,setFields]=useState<Record<string,string>>({}); const [rawText,setRawText]=useState("");
  const active=useMemo(()=>templates.data?.find(row=>row.id===selected)??null,[templates.data,selected]);
  const rules=useMemo<Rule[]>(()=>[
    ...required.map(field=>({key:`required-${field}`,kind:"required_field",field,severity:"fail" as const,message:`${BASE_FIELDS.find(item=>item[0]===field)?.[1]??field} is present.`,source})),
    ...(contains.trim()?[{key:"required-warning-language",kind:"contains",field:"warning_text",value:contains.trim(),severity:"fail" as const,message:"Configured required warning language is present.",source:containsSource||source}]:[]),
  ],[required,contains,containsSource,source]);
  const create=useMutation({mutationFn:()=>apiPost("/api/v1/control-tower/label-templates",{name,jurisdiction,license_scope:scope,layout:{fields:required},rules,activate:true}),onSuccess:()=>{setName("");void client.invalidateQueries({queryKey:["label-studio-templates"]});}});
  const review=useMutation({mutationFn:()=>apiPost<Review>("/api/v1/control-tower/label-reviews",{template_id:selected||null,label:{...fields,raw_text:rawText},rules:selected?[]:rules,rule_set_reference:selected?"":`${name||"Ad hoc"} configured review`})});
  const toggle=(field:string)=>setRequired(current=>current.includes(field)?current.filter(value=>value!==field):[...current,field]);
  return <div className="page"><div className="eyebrow">COMPLIANCE · LABELS</div><h1>Label Studio + LabelGuard</h1><p className="section-note">Build versioned label rule sets, preview label content, and run deterministic pre-release checks against reviewed requirements. DoobieLogic stores the rule source beside every finding so a compliance result can be traced back to the approved standard.</p>
    <div className="view-tabs parity-tabs"><button className="active" type="button">Template & Rule Builder</button><button type="button" onClick={()=>window.print()}>Print current preview</button></div>
    <div className="two-column-grid"><section className="inventory-panel"><div className="eyebrow">VERSIONED RULE SET</div><h2>Create an approved label template</h2><div className="form-grid two"><label>Template name<input value={name} onChange={e=>setName(e.target.value)} placeholder="MA Adult Use Retail Label"/></label><label>Jurisdiction<input value={jurisdiction} onChange={e=>setJurisdiction(e.target.value)} placeholder="Massachusetts"/></label><label>License scope<input value={scope} onChange={e=>setScope(e.target.value)} placeholder="Adult Use / Manufacturing"/></label><label>Source / citation<input value={source} onChange={e=>setSource(e.target.value)} placeholder="Approved regulation or SOP reference"/></label><label className="full">Required warning phrase<input value={contains} onChange={e=>setContains(e.target.value)} placeholder="Optional exact phrase required by the reviewed source"/></label><label className="full">Warning phrase source<input value={containsSource} onChange={e=>setContainsSource(e.target.value)} placeholder="Citation or SOP section"/></label></div><div className="inventory-panel"><strong>Required fields</strong><div className="role-home-task-grid">{BASE_FIELDS.map(([field,label])=><label key={field}><input type="checkbox" checked={required.includes(field)} onChange={()=>toggle(field)}/> {label}</label>)}</div></div><button className="primary" type="button" disabled={!name.trim()||create.isPending} onClick={()=>create.mutate()}>{create.isPending?"Saving…":"Save & activate template"}</button>{create.isError?<div className="form-error">{create.error.message}</div>:null}</section>
      <section className="inventory-panel"><div className="eyebrow">LIVE LABEL PREVIEW</div><h2>{fields.product_name||"Product Name"}</h2><div className="inventory-panel label-print-preview"><strong>{fields.product_name||"PRODUCT NAME"}</strong><p>{fields.net_contents||"Net contents"}</p><p>{fields.potency||"Potency"}</p><small>{fields.license_number||"License"}</small><small>{fields.package_id||"Package ID"}</small><p>{fields.ingredients||"Ingredients"}</p><p>{fields.allergens||"Allergens"}</p><strong>{fields.warning_text||"Required warning"}</strong></div></section></div>
    <section className="inventory-panel"><div className="eyebrow">LABELGUARD</div><h2>Pre-release review</h2><div className="form-grid two"><label>Approved template<select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Use builder rules above</option>{templates.data?.filter(row=>row.status==="active").map(row=><option value={row.id} key={row.id}>{row.name} v{row.version} · {row.jurisdiction||"Internal"}</option>)}</select></label>{BASE_FIELDS.map(([field,label])=><label key={field}>{label}<input value={fields[field]??""} onChange={e=>setFields(current=>({...current,[field]:e.target.value}))}/></label>)}<label className="full">Extracted label text<textarea rows={5} value={rawText} onChange={e=>setRawText(e.target.value)} placeholder="Paste OCR or final label text for phrase checks."/></label></div><button className="primary" type="button" disabled={review.isPending||(!selected&&!rules.length)} onClick={()=>review.mutate()}>{review.isPending?"Checking…":"Run LabelGuard"}</button>{review.isError?<div className="form-error">{review.error.message}</div>:null}{review.data?<div className="inventory-panel"><h3>{review.data.status.toUpperCase()}</h3>{review.data.findings.map(item=><div className={item.status==="fail"?"warning-banner":item.status==="warning"?"info-banner":"success-banner"} key={item.key}><strong>{item.status.toUpperCase()}</strong> · {item.message}{item.source?<><br/><small>{item.source}</small></>:null}</div>)}<p className="section-note">{review.data.disclaimer}</p></div>:null}{active?<p className="section-note">Reviewing against {active.name} v{active.version} ({active.jurisdiction||"internal scope"}).</p>:null}</section>
  </div>;
}
