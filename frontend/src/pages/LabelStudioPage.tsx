import { useEffect, useMemo, useRef, useState } from "react";
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
type TraceabilityGraphic = { value:string;svg:string;format?:string };
type InventoryLabelSource = {
  lot_id:string;product_id:string;package_id:string;lot_code:string;product_name:string;sku:string;location:string;status:string;
  on_hand:number;inventory_unit:string;label:Record<string,string>;coa:CoaSource;qr:TraceabilityGraphic;barcode?:TraceabilityGraphic;raw_text:string;
  source_summary:{facility:string;license_number:string;license_type:string;qa_source:string;coa_source:string;coa_verification:string};
};
type InventoryLabelSummary = {
  lot_id:string;product_id:string;package_id:string;lot_code:string;product_name:string;sku:string;location:string;status:string;on_hand:number;inventory_unit:string;
  label?:Record<string,string>;coa?:CoaSource;qr?:TraceabilityGraphic;barcode?:TraceabilityGraphic;raw_text?:string;
  source_summary?:InventoryLabelSource["source_summary"];
};
type CoaMutationResult = { coa_document:Record<string,unknown>;source:InventoryLabelSource };

const PACKAGING_ONLY_FIELDS = new Set(["warning_text", "universal_symbol", "warning_symbol", "statutory_warning"]);

const FIELD_OPTIONS = [
  ["product_name","Product identity"],
  ["brand","Brand"],
  ["strain","Strain"],
  ["product_type","Product type / category"],
  ["package_size","Package size"],
  ["net_contents","Net contents"],
  ["package_composition","Package composition / unit count"],
  ["license_number","Active facility license"],
  ["facility_name","Active facility"],
  ["manufacturer","Manufacturer"],
  ["package_id","Package / traceability ID"],
  ["batch_number","Batch / lot number"],
  ["serial_number","Label serial number"],
  ["potency","Potency statement"],
  ["total_thc","Total THC"],
  ["total_cbd","Total CBD"],
  ["total_cannabinoids","Total cannabinoids / TAC"],
  ["total_terpenes","Total terpenes"],
  ["lab_testing_state","Lab testing state"],
  ["laboratory","Testing laboratory"],
  ["lab_license_number","Laboratory license"],
  ["test_date","Test date"],
  ["coa_reference","COA reference"],
  ["ingredients","Ingredients"],
  ["allergens","Allergen statement"],
  ["harvest_date","Harvest date"],
  ["manufacture_date","Manufacture date"],
  ["package_date","Package date"],
  ["expiration_date","Expiration / best-by"],
  ["cultivated_by","Cultivated by"],
  ["cultivator_license","Cultivator license"],
  ["cultivator_contact","Cultivator contact"],
  ["packaged_by","Packaged by"],
  ["packager_license","Packager license"],
  ["packager_contact","Packager contact"],
  ["sold_by","Sold by"],
  ["seller_license","Seller license(s)"],
  ["seller_contact","Seller contact"],
] as const;

const PREVIEW_FIELDS = [
  "brand","strain","product_type","package_size","net_contents","package_composition",
  "harvest_date","manufacture_date","package_date","expiration_date","test_date","batch_number","serial_number",
  "potency","total_thc","total_cbd","total_cannabinoids","lab_testing_state","laboratory","lab_license_number","coa_reference",
  "cultivated_by","cultivator_license","cultivator_contact","packaged_by","packager_license","packager_contact","sold_by","seller_license","seller_contact",
  "license_number","facility_name","manufacturer","ingredients","allergens","package_id",
] as const;

function fieldLabel(field:string){return FIELD_OPTIONS.find(item=>item[0]===field)?.[1]??field.replaceAll("_"," ");}
function isPackagingOnlyRule(rule:Rule){return PACKAGING_ONLY_FIELDS.has(String(rule.field??"").trim().toLowerCase());}
function templateFields(template:Template|null){const value=template?.layout?.fields;return Array.isArray(value)?value.filter((item):item is string=>typeof item==="string"&&!PACKAGING_ONLY_FIELDS.has(item.trim().toLowerCase())):[];}
function sourceLabel(source:InventoryLabelSummary){const packageRef=source.package_id||source.lot_code;return `${source.product_name} · ${source.lot_code}${packageRef&&packageRef!==source.lot_code?` · ${packageRef}`:""}`;}
function resultDisplay(result:CoaResult){if(result.value_text)return `${result.value_text}${result.units&&!result.value_text.includes(result.units)?` ${result.units}`:""}`;if(result.value==null)return "—";return `${result.value}${result.units?` ${result.units}`:""}`;}
function resultNumeric(result:CoaResult){if(result.value!=null&&Number.isFinite(result.value))return result.value;const parsed=Number.parseFloat(String(result.value_text??"").replace(/[^0-9.-]+/g,""));return Number.isFinite(parsed)?parsed:Number.NEGATIVE_INFINITY;}
function graphicDataUri(graphic:TraceabilityGraphic|undefined){return graphic?.svg?`data:image/svg+xml;charset=utf-8,${encodeURIComponent(graphic.svg)}`:"";}
function isPassedCoa(source:InventoryLabelSource|null){return Boolean(source?.coa.available&&["pass","passed"].includes(String(source.coa.overall_status??"").trim().toLowerCase())&&source.coa.date_tested);}
function testingFields(source:InventoryLabelSource){const next={...source.label};for(const field of PACKAGING_ONLY_FIELDS)delete next[field];return next;}
function testingRawText(label:Record<string,string>){return ["product_name",...PREVIEW_FIELDS,"total_terpenes"].map(field=>String(label[field]??"").trim()).filter(Boolean).join("\n");}
function isCompleteSummary(source:InventoryLabelSummary|undefined):source is InventoryLabelSource{return Boolean(source?.label&&source.coa&&source.qr&&source.source_summary);}

export function LabelStudioPage(){
  const client=useQueryClient();
  const templates=useQuery({queryKey:["label-studio-templates"],queryFn:({signal})=>apiGet<Template[]>("/api/v1/control-tower/label-templates",signal)});
  const inventory=useQuery({queryKey:["label-studio-inventory-summaries"],queryFn:({signal})=>apiGet<InventoryLabelSummary[]>("/api/v1/label-printing/inventory-sources?summary=true",signal)});
  const [name,setName]=useState(""); const [jurisdiction,setJurisdiction]=useState(""); const [scope,setScope]=useState(""); const [source,setSource]=useState("");
  const [required,setRequired]=useState<string[]>(["product_name","net_contents","license_number","package_id","batch_number","lab_testing_state","test_date"]);
  const [selected,setSelected]=useState(""); const [inventoryLotId,setInventoryLotId]=useState(""); const [fields,setFields]=useState<Record<string,string>>({}); const [rawText,setRawText]=useState("");
  const [coaMessage,setCoaMessage]=useState("");
  const hydratedLot=useRef("");
  const active=useMemo(()=>templates.data?.find(row=>row.id===selected)??null,[templates.data,selected]);
  const selectedSummary=useMemo(()=>inventory.data?.find(row=>row.lot_id===inventoryLotId),[inventory.data,inventoryLotId]);
  const sourceDetail=useQuery({
    queryKey:["label-studio-inventory-source",inventoryLotId],
    queryFn:({signal})=>apiGet<InventoryLabelSource>(`/api/v1/label-printing/inventory-sources/${encodeURIComponent(inventoryLotId)}`,signal),
    enabled:Boolean(inventoryLotId&&!isCompleteSummary(selectedSummary)),
  });
  const activeSource=useMemo<InventoryLabelSource|null>(()=>isCompleteSummary(selectedSummary)?selectedSummary:(sourceDetail.data??null),[selectedSummary,sourceDetail.data]);
  const inheritedCoa=useMemo(()=>Boolean(activeSource?.coa.available&&activeSource.coa.metrc_source_id&&activeSource.package_id&&activeSource.coa.metrc_source_id!==activeSource.package_id),[activeSource]);
  const rules=useMemo<Rule[]>(()=>required.map(field=>({key:`required-${field}`,kind:"required_field",field,severity:"fail" as const,message:`${fieldLabel(field)} is present.`,source})),[required,source]);
  const activeTestingRules=useMemo(()=>active?.rules.filter(rule=>!isPackagingOnlyRule(rule))??[],[active]);
  const activeHasPackagingOnlyRules=useMemo(()=>Boolean(active?.rules.some(isPackagingOnlyRule)),[active]);
  const requiredForReview=useMemo(()=>{const configured=templateFields(active);return configured.length?configured:required},[active,required]);
  const missingRequired=useMemo(()=>requiredForReview.filter(field=>!String(fields[field]??"").trim()),[fields,requiredForReview]);
  const populatedCount=useMemo(()=>FIELD_OPTIONS.filter(([field])=>String(fields[field]??"").trim()).length,[fields]);
  const cannabinoids=useMemo(()=>activeSource?.coa.results.filter(row=>row.analysis==="cannabinoids")??[],[activeSource]);
  const terpenes=useMemo(()=>activeSource?.coa.results.filter(row=>row.analysis==="terpenes")??[],[activeSource]);
  const topTerpenes=useMemo(()=>[...terpenes].filter(row=>!String(row.key).toLowerCase().includes("total")).sort((a,b)=>resultNumeric(b)-resultNumeric(a)).slice(0,3),[terpenes]);
  const create=useMutation({mutationFn:()=>apiPost("/api/v1/control-tower/label-templates",{name,jurisdiction,license_scope:scope,layout:{fields:required,label_scope:"testing"},rules,activate:true}),onSuccess:()=>{setName("");void client.invalidateQueries({queryKey:["label-studio-templates"]});}});
  const review=useMutation({mutationFn:()=>{
    const useTemplateId=Boolean(active&&!activeHasPackagingOnlyRules);
    return apiPost<Review>("/api/v1/control-tower/label-reviews",{
      template_id:useTemplateId?active?.id:null,
      product_id:activeSource?.product_id??null,
      package_id:activeSource?.package_id??fields.package_id??"",
      label:{...fields,warning_text:"",universal_symbol:"",label_scope:"testing",package_id:activeSource?.package_id??fields.package_id??"",raw_text:rawText},
      rules:useTemplateId?[]:(active?activeTestingRules:rules),
      rule_set_reference:active?`${active.name} v${active.version} · testing-label scope`:`${name||"Ad hoc"} testing-label review`,
    });
  }});
  const syncSource=(next:InventoryLabelSource)=>{
    client.setQueryData<InventoryLabelSource>(["label-studio-inventory-source",next.lot_id],next);
    hydratedLot.current=next.lot_id;
    const nextFields=testingFields(next);setFields(nextFields);setRawText(testingRawText(nextFields));review.reset();
  };
  useEffect(()=>{
    if(!activeSource||activeSource.lot_id!==inventoryLotId||hydratedLot.current===inventoryLotId)return;
    hydratedLot.current=inventoryLotId;
    const nextFields=testingFields(activeSource);setFields(nextFields);setRawText(testingRawText(nextFields));
  },[activeSource,inventoryLotId]);
  useEffect(()=>{
    if(!inventoryLotId||selected)return;
    const activeTemplates=templates.data?.filter(row=>row.status==="active")??[];
    if(activeTemplates.length===1)setSelected(activeTemplates[0].id);
  },[inventoryLotId,selected,templates.data]);
  const uploadCoa=useMutation({
    mutationFn:async(file:File)=>{if(!inventoryLotId)throw new Error("Choose an inventory batch first.");const body=new FormData();body.set("file",file);return apiPostForm<CoaMutationResult>(`/api/v1/label-printing/inventory-sources/${encodeURIComponent(inventoryLotId)}/coa`,body)},
    onSuccess:value=>{syncSource(value.source);setCoaMessage(value.source.coa.needs_confirmation?"COA parsed. The METRC tag was not readable in the PDF, so explicit confirmation is required before it becomes the label source.":"COA matched and is now the verified test source for this material.")},
  });
  const confirmCoa=useMutation({
    mutationFn:()=>{if(!inventoryLotId||!activeSource?.coa.document_id)throw new Error("No pending COA is available to confirm.");return apiPost<CoaMutationResult>(`/api/v1/label-printing/inventory-sources/${encodeURIComponent(inventoryLotId)}/coa/${encodeURIComponent(activeSource.coa.document_id)}/confirm`,{})},
    onSuccess:value=>{syncSource(value.source);setCoaMessage("COA association confirmed for this METRC package tag.")},
  });
  const toggle=(field:string)=>setRequired(current=>current.includes(field)?current.filter(value=>value!==field):[...current,field]);
  const chooseInventorySource=(lotId:string)=>{
    hydratedLot.current="";setInventoryLotId(lotId);review.reset();setCoaMessage("");uploadCoa.reset();confirmCoa.reset();setFields({});setRawText("");
    const activeTemplates=templates.data?.filter(row=>row.status==="active")??[];
    if(lotId&&!selected&&activeTemplates.length===1)setSelected(activeTemplates[0].id);
  };
  const openCoa=async()=>{
    if(!activeSource?.coa.file_url)return;
    const blob=await apiDownload(activeSource.coa.file_url);
    const url=URL.createObjectURL(blob);window.open(url,"_blank","noopener,noreferrer");window.setTimeout(()=>URL.revokeObjectURL(url),60_000);
  };
  const coaReady=isPassedCoa(activeSource);
  const canPrint=Boolean(Object.keys(fields).length&&!missingRequired.length&&review.data?.status==="pass"&&!activeSource?.coa.needs_confirmation&&activeSource?.package_id&&coaReady);
  return <div className="page"><style>{`@media print{body *{visibility:hidden!important}.label-print-preview,.label-print-preview *{visibility:visible!important}.label-print-preview{position:absolute!important;left:0!important;top:0!important;width:100%!important;max-width:none!important;margin:0!important;border:0!important;box-shadow:none!important;background:#fff!important;color:#000!important}.label-print-preview .label-qr-image{width:1in!important;height:1in!important}.label-print-preview .label-barcode-image{width:100%!important;max-width:3in!important;height:auto!important}}.label-qr-image{width:120px;height:120px;display:block}.label-barcode-image{width:100%;max-width:360px;height:auto;display:block}.label-traceability{font-family:monospace;word-break:break-all}.locked-field{background:rgba(127,127,127,.08)}`}</style><div className="eyebrow">COMPLIANCE · TESTING LABELS</div><h1>Label Studio + LabelGuard</h1><p className="section-note">Select an inventory batch to build its testing label from Product Master, the active facility, its current METRC package tag, and the COA attached to that tested material. Packaging-only statutory warning text and warning symbols are intentionally outside this testing-label scope. A split or repack may have a new current tag while retaining the verified ancestor COA through package lineage. The QR and printed package identity always use the current tag.</p>
    <div className="view-tabs parity-tabs"><button className="active" type="button">Build & review</button><button type="button" disabled={!canPrint} title={canPrint?"Print the reviewed testing label with current METRC package QR/barcode":activeSource?.coa.needs_confirmation?"Confirm the pending COA association before printing":!coaReady?"A verified passing COA with a test date is required before printing":missingRequired.length?`Complete required fields: ${missingRequired.map(fieldLabel).join(", ")}`:review.data?.status==="warning"?"Resolve the warning or obtain an approved print override workflow":"Run LabelGuard and receive a PASS before printing"} onClick={()=>window.print()}>Print reviewed label</button></div>

    <section className="inventory-panel"><div className="eyebrow">BUILD FROM INVENTORY</div><h2>Select a batch or package</h2><p className="section-note">Only on-hand inventory in the active facility is available here. The selected lot's current METRC tag is immutable inside Label Studio and becomes both the printed traceability ID and the payload for its QR and Code 128 barcode.</p>
      {inventory.isLoading?<div className="state">Loading active-facility inventory…</div>:null}{inventory.isError?<div className="form-error">{inventory.error.message}</div>:null}
      {inventory.data?<div className="form-grid two"><label className="full">Inventory batch<select value={inventoryLotId} onChange={event=>chooseInventorySource(event.target.value)}><option value="">Choose a batch or package…</option>{inventory.data.map(row=><option value={row.lot_id} key={row.lot_id}>{sourceLabel(row)}</option>)}</select></label></div>:null}
      {inventory.data&&!inventory.data.length?<div className="info-banner">No on-hand inventory batches were found in this facility.</div>:null}
      {inventoryLotId&&sourceDetail.isLoading&&!activeSource?<div className="state">Loading selected batch details…</div>:null}{sourceDetail.isError?<div className="form-error">{sourceDetail.error.message}</div>:null}
      {activeSource?<><div className="metrics four"><Metric label="Product" value={activeSource.product_name}/><Metric label="Batch" value={activeSource.lot_code}/><Metric label="On hand" value={`${activeSource.on_hand.toLocaleString()} ${activeSource.inventory_unit}`}/><Metric label="Location" value={activeSource.location||"—"}/></div><div className={missingRequired.length?"warning-banner":"success-banner"}><strong>{populatedCount} testing-label fields populated from inventory.</strong> {missingRequired.length?<>Required testing-label information still missing: {missingRequired.map(fieldLabel).join(", ")}. Complete or correct the source data before final release.</>:<>All fields required by the current testing-label rule set are populated.</>}</div><p className="section-note">Source: {activeSource.source_summary.facility}{activeSource.source_summary.license_number?` · ${activeSource.source_summary.license_number}`:""}{activeSource.source_summary.qa_source?` · QA ${activeSource.source_summary.qa_source}`:""}</p></>:null}
    </section>

    {activeSource?<section className="inventory-panel"><div className="eyebrow">COA SOURCE</div><h2>Test results for this material</h2>
      {activeSource.coa.available&&!inheritedCoa?<><div className="success-banner"><strong>COA matched to the current METRC package tag.</strong> {activeSource.coa.filename||"Stored COA"} is the verified test source. {activeSource.coa.lab_name?`Laboratory: ${activeSource.coa.lab_name}.`:""}</div><div className="audit-actions"><button className="secondary" type="button" onClick={()=>void openCoa()}>Open source COA</button></div></>:null}
      {activeSource.coa.available&&inheritedCoa?<><div className="success-banner"><strong>COA inherited through package lineage.</strong> Current package <span className="label-traceability">{activeSource.package_id}</span> retains the verified COA from tested package <span className="label-traceability">{activeSource.coa.metrc_source_id}</span>. The printed label, QR, and barcode stay tied to the current package tag.</div><div className="audit-actions"><button className="secondary" type="button" onClick={()=>void openCoa()}>Open source COA</button></div></>:null}
      {activeSource.coa.needs_confirmation?<div className="warning-banner"><strong>COA parsed, identity confirmation required.</strong> The PDF did not expose a readable METRC tag. Confirm only if this certificate belongs to <strong>{activeSource.package_id}</strong>. A certificate that contains a different METRC tag is rejected before this stage.<div className="audit-actions"><button className="primary" disabled={confirmCoa.isPending} type="button" onClick={()=>confirmCoa.mutate()}>{confirmCoa.isPending?"Confirming…":"Confirm COA for this tag"}</button><button className="secondary" type="button" onClick={()=>void openCoa()}>Review PDF first</button></div></div>:null}
      {!activeSource.coa.available&&!activeSource.coa.needs_confirmation&&activeSource.package_id?<div className="info-banner"><strong>No verified COA was found for this package or its recorded material lineage.</strong> Use the PDF fallback only when the certificate truly belongs to the selected package. An ancestor COA should arrive through lineage, not by manually relabeling it as the child package's test.</div>:null}
      {activeSource.coa.available&&!coaReady?<div className="warning-banner"><strong>Testing label cannot be printed yet.</strong> The selected material needs a verified passing COA with a test date.</div>:null}
      {!activeSource.package_id?<div className="warning-banner"><strong>No METRC package/tag is stored on this inventory lot.</strong> Automatic COA resolution, traceability-code generation, and printing stay disabled until traceability identity is present.</div>:null}
      {!activeSource.coa.available&&!activeSource.coa.needs_confirmation&&activeSource.package_id?<label className="file-drop">Fallback: upload the COA for {activeSource.package_id}<input type="file" accept="application/pdf,.pdf" disabled={uploadCoa.isPending} onChange={event=>{const file=event.target.files?.[0];if(file)uploadCoa.mutate(file);event.currentTarget.value=""}}/></label>:null}
      {uploadCoa.isPending?<div className="state">Reading COA and verifying the METRC package tag…</div>:null}{uploadCoa.isError?<div className="form-error">{uploadCoa.error.message}</div>:null}{confirmCoa.isError?<div className="form-error">{confirmCoa.error.message}</div>:null}{coaMessage?<div className="success-banner">{coaMessage}</div>:null}
      {activeSource.coa.document_id?<><div className="metrics four"><Metric label="COA status" value={activeSource.coa.overall_status||activeSource.coa.status}/><Metric label="Test date" value={activeSource.coa.date_tested||"—"}/><Metric label="Total THC" value={activeSource.coa.total_thc==null?"—":`${activeSource.coa.total_thc}%`}/><Metric label="Total terpenes" value={activeSource.coa.total_terpenes==null?"—":`${activeSource.coa.total_terpenes}%`}/></div>{cannabinoids.length?<AnalyteTable title="Cannabinoids" rows={cannabinoids}/>:null}{terpenes.length?<AnalyteTable title="Terpenes" rows={terpenes}/>:null}</>:null}
    </section>:null}

    <div className="two-column-grid"><section className="inventory-panel"><div className="eyebrow">VERSIONED TESTING-LABEL RULE SET</div><h2>Create an approved testing-label template</h2><p className="section-note">This rule builder intentionally excludes packaging-only warning statements and warning symbols. Responsible-party, package-composition, laboratory, and serial fields can be required by a facility template when applicable.</p><div className="form-grid two"><label>Template name<input value={name} onChange={e=>setName(e.target.value)} placeholder="MA Flower Testing Label"/></label><label>Jurisdiction<input value={jurisdiction} onChange={e=>setJurisdiction(e.target.value)} placeholder="Massachusetts"/></label><label>License scope<input value={scope} onChange={e=>setScope(e.target.value)} placeholder="Cultivation / Manufacturing / Retail"/></label><label>Source / citation<input value={source} onChange={e=>setSource(e.target.value)} placeholder="Approved testing-label SOP or rule reference"/></label></div><div className="inventory-panel"><strong>Required testing-label fields</strong><div className="role-home-task-grid">{FIELD_OPTIONS.map(([field,label])=><label key={field}><input type="checkbox" checked={required.includes(field)} onChange={()=>toggle(field)}/> {label}</label>)}</div></div><button className="primary" type="button" disabled={!name.trim()||create.isPending} onClick={()=>create.mutate()}>{create.isPending?"Saving…":"Save & activate template"}</button>{create.isError?<div className="form-error">{create.error.message}</div>:null}</section>
      <section className="inventory-panel"><div className="eyebrow">LIVE TESTING-LABEL PREVIEW</div><h2>{fields.product_name||"Product Name"}</h2><div className="inventory-panel label-print-preview"><strong>{fields.product_name||"PRODUCT NAME"}</strong>{PREVIEW_FIELDS.map(field=>fields[field]?<p key={field}><small>{fieldLabel(field)}</small><br/>{fields[field]}</p>:null)}{activeSource?.barcode?.svg?<div><strong>METRC package barcode</strong><img className="label-barcode-image" src={graphicDataUri(activeSource.barcode)} alt={`Code 128 barcode for METRC package ${activeSource.barcode.value}`}/></div>:null}{activeSource?.qr.svg?<div><strong>METRC package QR</strong><img className="label-qr-image" src={graphicDataUri(activeSource.qr)} alt={`QR code for METRC package ${activeSource.qr.value}`}/><div className="label-traceability">{activeSource.qr.value}</div></div>:null}{cannabinoids.length?<><hr/><strong>Cannabinoids</strong>{cannabinoids.slice(0,8).map(row=><p key={row.key}><small>{row.name}</small><br/>{resultDisplay(row)}</p>)}</>:null}{topTerpenes.length?<><hr/><strong>Top Terpenes</strong>{topTerpenes.map(row=><p key={row.key}><small>{row.name}</small><br/>{resultDisplay(row)}</p>)}{fields.total_terpenes?<p><small>Total Terpenes</small><br/>{fields.total_terpenes}</p>:null}</>:null}</div><p className="section-note">The COA detail above retains every parsed terpene. The printed testing label intentionally uses only the top three terpene concentrations plus Total Terpenes so the physical label remains readable.</p></section></div>
    <section className="inventory-panel"><div className="eyebrow">LABELGUARD</div><h2>Testing-label pre-release review</h2>{active&&activeHasPackagingOnlyRules?<div className="info-banner"><strong>Legacy packaging rule ignored for this testing label.</strong> Packaging-only warning/symbol rules in {active.name} v{active.version} do not participate in this testing-label review.</div>:null}<div className="form-grid two"><label>Approved template<select value={selected} onChange={e=>{setSelected(e.target.value);review.reset()}}><option value="">Use testing-label builder rules above</option>{templates.data?.filter(row=>row.status==="active").map(row=><option value={row.id} key={row.id}>{row.name} v{row.version} · {row.jurisdiction||"Internal"}</option>)}</select></label>{FIELD_OPTIONS.map(([field,label])=><label key={field}>{label}<input className={field==="package_id"&&activeSource?"locked-field":""} readOnly={field==="package_id"&&Boolean(activeSource)} title={field==="package_id"&&activeSource?"The current METRC package tag comes from inventory and cannot be changed in Label Studio.":undefined} value={fields[field]??""} onChange={e=>{setFields(current=>({...current,[field]:e.target.value}));review.reset()}}/></label>)}<label className="full">Extracted / rendered testing-label text<textarea rows={6} value={rawText} onChange={e=>{setRawText(e.target.value);review.reset()}} placeholder="Inventory selection prebuilds this text; edit it if the final rendered testing label differs."/></label></div>{missingRequired.length?<div className="warning-banner"><strong>Not ready for release.</strong> Missing required testing-label fields: {missingRequired.map(fieldLabel).join(", ")}.</div>:null}{activeSource?.coa.needs_confirmation?<div className="warning-banner"><strong>Not ready for release.</strong> Confirm the pending COA association before running the final label review.</div>:null}{activeSource&&!coaReady?<div className="warning-banner"><strong>Not ready for printing.</strong> A verified passing COA with a test date is required for a testing label.</div>:null}<button className="primary" type="button" disabled={review.isPending||Boolean(missingRequired.length)||Boolean(activeSource?.coa.needs_confirmation)||(!selected&&!rules.length)} onClick={()=>review.mutate()}>{review.isPending?"Checking…":"Run LabelGuard"}</button>{review.isError?<div className="form-error">{review.error.message}</div>:null}{review.data?<div className="inventory-panel"><h3>{review.data.status.toUpperCase()}</h3>{review.data.findings.map(item=><div className={item.status==="fail"?"warning-banner":item.status==="warning"?"info-banner":"success-banner"} key={item.key}><strong>{item.status.toUpperCase()}</strong> · {item.message}{item.source?<><br/><small>{item.source}</small></>:null}</div>)}{review.data.status==="warning"?<div className="warning-banner"><strong>Printing remains blocked.</strong> Route warning overrides through the approved QA/Admin print workflow rather than bypassing LabelGuard.</div>:null}<p className="section-note">{review.data.disclaimer}</p></div>:null}{active?<p className="section-note">Reviewing testing-label fields against {active.name} v{active.version} ({active.jurisdiction||"internal scope"}). Packaging-only warning and symbol requirements are excluded from this testing-label review.</p>:null}</section>
  </div>;
}

function AnalyteTable({title,rows}:{title:string;rows:CoaResult[]}){return <details className="streamlit-expander" open><summary>{title} · {rows.length} result{rows.length===1?"":"s"}</summary><div className="streamlit-expander-body"><div className="table-wrap"><table><thead><tr><th>Analyte</th><th>Result</th><th>Status</th></tr></thead><tbody>{rows.map(row=><tr key={row.key}><td>{row.name}</td><td>{resultDisplay(row)}</td><td>{row.status||"—"}</td></tr>)}</tbody></table></div></div></details>}
function Metric({label,value}:{label:string;value:string}){return <div className="metric"><span>{label}</span><strong>{value}</strong></div>}
