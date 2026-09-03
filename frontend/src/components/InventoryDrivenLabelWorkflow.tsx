import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type InventorySummary = { lot_id:string;product_id:string;package_id:string;lot_code:string;product_name:string;sku:string;location:string;status:string;on_hand:number;inventory_unit:string };
type CoaSource = { available:boolean;needs_confirmation:boolean;document_id:string;filename:string;lab_name:string;lab_license_number:string;date_tested:string;overall_status:string;total_thc:number|null;total_cbd:number|null;total_cannabinoids:number|null;total_terpenes:number|null;results:Array<{analysis:string;name:string;value:number|null;value_text:string;units:string}> };
type InventorySource = InventorySummary & { label:Record<string,string>;coa:CoaSource;source_summary:Record<string,string> };
type Product = { id:string;sku:string;name:string;item_type:string;base_unit:string;active:boolean;brand?:string;category?:string;product_format?:string };
type ProductDetail = { product:Product;profile:{brand:string;category:string;subcategory:string;strain:string;manufacturer:string;product_format:string;production_enabled:boolean}|null;packaging:{net_content:number;net_content_unit:string;units_per_package:number;sellable_unit:string;case_pack:number;warning_text:string}|null };
type Graphic = { value:string;svg:string;format?:string };
type LabelEvent = { id:string;event_type:string;from_status:string;to_status:string;actor:string;details:Record<string,unknown>;occurred_at:string };
type LabelRun = {
  id:string;product_id:string;quantity:number;expected_material_quantity:number;expected_material_unit:string;status:string;metrc_package_tag:string;created_by:string;printed_by:string;
  created_at:string;printed_at:string|null;snapshot:{source:Record<string,unknown>;product:Record<string,unknown>;label:Record<string,string>;quantity:number;expected_material_quantity:number;expected_material_unit:string};
  traceability:{value:string;qr:Graphic;barcode:Graphic};events:LabelEvent[];
};
type SearchOption = { value:string;label:string;searchText:string };

const FLOW = ["Source", "Product", "Quantity", "Preview", "METRC tag", "Print"];
const DISPLAY_FIELDS = [
  "brand","strain","product_type","package_size","net_contents","package_composition",
  "harvest_date","cultivated_by","cultivator_license","cultivator_contact",
  "potency","total_thc","total_cbd","total_cannabinoids","total_terpenes","lab_testing_state","laboratory","lab_license_number","test_date","coa_reference",
  "facility_name","license_number","manufacturer","batch_number","warning_text",
];

function graphicDataUri(graphic:Graphic|undefined){return graphic?.svg?`data:image/svg+xml;charset=utf-8,${encodeURIComponent(graphic.svg)}`:"";}
function sourceName(row:InventorySummary){return `${row.product_name} · ${row.lot_code}${row.package_id?` · ${row.package_id}`:""}`;}
function productName(row:Product){return `${row.name}${row.sku?` · ${row.sku}`:""}`;}
function fieldLabel(value:string){return value.replaceAll("_"," ").replace(/\b\w/g,match=>match.toUpperCase());}
function eventLabel(value:string){return value.replaceAll("_"," ").replace(/\b\w/g,match=>match.toUpperCase());}
function fmt(value:number){if(!Number.isFinite(value))return "0";return Number(value.toFixed(5)).toString();}

function SearchablePicker({ariaLabel,value,options,placeholder,disabled,onChange}:{ariaLabel:string;value:string;options:SearchOption[];placeholder:string;disabled:boolean;onChange:(value:string)=>void}){
  const selectedLabel=options.find(option=>option.value===value)?.label??"";
  const [query,setQuery]=useState(selectedLabel);
  const [open,setOpen]=useState(false);
  useEffect(()=>{
    if(value)setQuery(selectedLabel);
    else if(!open)setQuery("");
  },[value,selectedLabel,open]);
  const normalized=query.trim().toLowerCase();
  const filtered=useMemo(()=>{
    if(!normalized)return options.slice(0,40);
    return options.filter(option=>option.searchText.includes(normalized)).slice(0,40);
  },[normalized,options]);
  return <div className="label-search-picker">
    <input
      role="combobox"
      aria-label={ariaLabel}
      aria-expanded={open}
      autoComplete="off"
      placeholder={placeholder}
      disabled={disabled}
      value={query}
      onFocus={()=>setOpen(true)}
      onBlur={()=>window.setTimeout(()=>setOpen(false),120)}
      onChange={event=>{setQuery(event.target.value);setOpen(true);if(value)onChange("")}}
    />
    {open&&!disabled?<div className="label-search-menu" role="listbox">
      {filtered.length?filtered.map(option=><button
        key={option.value}
        type="button"
        role="option"
        aria-selected={option.value===value}
        onMouseDown={event=>event.preventDefault()}
        onClick={()=>{onChange(option.value);setQuery(option.label);setOpen(false)}}
      >{option.label}</button>):<div className="label-search-empty">No matches</div>}
    </div>:null}
  </div>;
}

export function InventoryDrivenLabelWorkflow(){
  const inventory=useQuery({queryKey:["label-studio-inventory-summaries"],queryFn:({signal})=>apiGet<unknown>("/api/v1/label-printing/inventory-sources?summary=true",signal)});
  const products=useQuery({queryKey:["label-studio-finished-products"],queryFn:({signal})=>apiGet<unknown>("/api/v1/product-master?operation=production&search=&status=active&item_type=finished_good",signal)});
  const inventoryRows=useMemo<InventorySummary[]>(()=>Array.isArray(inventory.data)?inventory.data.filter((row):row is InventorySummary=>Boolean(row&&typeof row==="object"&&"lot_id" in row&&"product_name" in row)):[],[inventory.data]);
  const productRows=useMemo<Product[]>(()=>Array.isArray(products.data)?products.data.filter((row):row is Product=>Boolean(row&&typeof row==="object"&&"id" in row&&"name" in row)):[],[products.data]);
  const sourceOptions=useMemo<SearchOption[]>(()=>inventoryRows.map(row=>({value:row.lot_id,label:sourceName(row),searchText:[row.product_name,row.lot_code,row.package_id,row.sku,row.location].join(" ").toLowerCase()})),[inventoryRows]);
  const productOptions=useMemo<SearchOption[]>(()=>productRows.map(row=>({value:row.id,label:productName(row),searchText:[row.name,row.sku,row.brand,row.category,row.product_format].join(" ").toLowerCase()})),[productRows]);
  const [sourceLotId,setSourceLotId]=useState("");
  const [productId,setProductId]=useState("");
  const [quantity,setQuantity]=useState(1);
  const [tag,setTag]=useState("");
  const [run,setRun]=useState<LabelRun|null>(null);
  const [reprintReason,setReprintReason]=useState("");
  const source=useQuery({queryKey:["label-studio-production-source",sourceLotId],queryFn:({signal})=>apiGet<InventorySource>(`/api/v1/label-printing/inventory-sources/${encodeURIComponent(sourceLotId)}`,signal),enabled:Boolean(sourceLotId)});
  const product=useQuery({queryKey:["label-studio-production-product",productId],queryFn:({signal})=>apiGet<ProductDetail>(`/api/v1/product-master/${encodeURIComponent(productId)}`,signal),enabled:Boolean(productId)});
  const create=useMutation({mutationFn:()=>apiPost<LabelRun>("/api/v1/label-printing/production-runs",{source_lot_id:sourceLotId,product_id:productId,quantity}),onSuccess:value=>setRun(value)});
  const assign=useMutation({mutationFn:()=>apiPost<LabelRun>(`/api/v1/label-printing/production-runs/${run?.id}/tag`,{metrc_package_tag:tag.trim()}),onSuccess:value=>setRun(value)});
  const print=useMutation({mutationFn:()=>apiPost<LabelRun>(`/api/v1/label-printing/production-runs/${run?.id}/print`,{copies:run?.quantity,reason:run?.status==="tagged"?"":reprintReason.trim()}),onSuccess:value=>{setRun(value);setReprintReason("");window.setTimeout(()=>window.print(),50)}});
  const transition=useMutation({mutationFn:(status:string)=>apiPost<LabelRun>(`/api/v1/label-printing/production-runs/${run?.id}/transition`,{status,note:""}),onSuccess:value=>setRun(value)});
  const reset=()=>{setSourceLotId("");setProductId("");setQuantity(1);setTag("");setRun(null);setReprintReason("");create.reset();assign.reset();print.reset();transition.reset()};
  const error=create.error||assign.error||print.error||transition.error||source.error||product.error;
  const sourceReady=Boolean(source.data?.coa.available&&["pass","passed"].includes(String(source.data?.coa.overall_status??"").toLowerCase())&&source.data?.coa.date_tested&&!source.data?.coa.needs_confirmation);
  const packaging=product.data?.packaging;
  const label=run?.snapshot?.label??{};
  const sourcePackage=String(run?.snapshot.source?.package_id??"");
  const sourceLot=String(run?.snapshot.source?.lot_code??"");
  const copies=run?Array.from({length:Math.max(1,Math.min(run.quantity,500))},(_,index)=>index):[];
  const nextStatus=run?.status==="printed"?"applied":run?.status==="applied"?"released":run?.status==="released"?"fulfilled":run?.status==="fulfilled"?"archived":"";
  const nextAction=nextStatus==="applied"?"Mark labels applied":nextStatus==="released"?"Release finished package":nextStatus==="fulfilled"?"Mark fulfilled":nextStatus==="archived"?"Archive run":"";

  return <section className="inventory-panel production-label-workflow">
    <style>{`
      .production-label-workflow{margin-bottom:28px}.label-flow{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:16px 0}.label-flow span{padding:9px 8px;border:1px solid var(--border);border-radius:10px;text-align:center;font-size:12px}.label-flow span.done{font-weight:700;border-color:currentColor}.production-label-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.production-label-grid label{display:flex;flex-direction:column;gap:6px}.label-search-picker{position:relative}.label-search-picker>input{width:100%}.label-search-menu{position:absolute;z-index:40;left:0;right:0;top:calc(100% + 4px);max-height:260px;overflow:auto;border:1px solid var(--border);border-radius:10px;background:Canvas;color:CanvasText;box-shadow:0 12px 28px rgba(0,0,0,.18);padding:6px}.label-search-menu button{display:block;width:100%;text-align:left;border:0;background:transparent;color:inherit;padding:9px 10px;border-radius:8px;font:inherit}.label-search-menu button:hover,.label-search-menu button:focus{background:rgba(127,127,127,.14)}.label-search-empty{padding:10px;opacity:.7}.production-label-preview{margin-top:18px;border:1px solid var(--border);border-radius:14px;padding:18px}.production-label-preview-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 18px}.production-label-preview-grid div{display:flex;justify-content:space-between;gap:16px;border-bottom:1px solid rgba(127,127,127,.15);padding:5px 0}.production-label-preview-grid span{opacity:.7}.production-traceability{display:grid;grid-template-columns:140px 1fr;gap:18px;align-items:center;margin-top:14px}.production-traceability img{max-width:100%}.production-label-copy{border:1px solid #222;padding:14px;background:#fff;color:#000;width:3.5in;min-height:2.1in;margin:12px 0}.production-label-copy:not(:first-child){display:none}.production-label-copy h3{margin:0 0 7px}.production-label-copy p{margin:3px 0;font-size:11px}.production-label-copy .codes{display:grid;grid-template-columns:90px 1fr;gap:8px;align-items:center}.production-label-copy .codes img{max-width:100%}.label-audit-row{display:grid;grid-template-columns:150px 1fr 180px;gap:10px;padding:7px 0;border-bottom:1px solid rgba(127,127,127,.15);font-size:12px}@media(max-width:850px){.label-flow,.production-label-grid{grid-template-columns:1fr 1fr}.production-label-preview-grid{grid-template-columns:1fr}.production-traceability{grid-template-columns:1fr}.label-audit-row{grid-template-columns:1fr}}@media print{body *{visibility:hidden!important}.production-label-print-batch,.production-label-print-batch *{visibility:visible!important}.production-label-print-batch{position:absolute!important;left:0!important;top:0!important;width:100%!important}.production-label-copy{display:block!important;break-after:page;page-break-after:always;margin:0!important;border:0!important;width:100%!important;min-height:0!important}.production-label-copy:last-child{break-after:auto;page-break-after:auto}}
    `}</style>
    <div className="eyebrow">LABEL STUDIO · CREATE FROM INVENTORY</div>
    <div className="page-heading"><div><h2>Create the finished label</h2><p>Search for the tested source batch, choose the finished Product Master item, enter how many labels you need, verify the generated label, scan the physical METRC package tag, and print.</p></div>{run?<button className="secondary" onClick={reset}>Start new label run</button>:null}</div>
    <div className="label-flow">{FLOW.map((step,index)=>{const progress=run?run.status==="validated"?4:run.status==="tagged"?5:["printed","applied","released","fulfilled","archived"].includes(run.status)?6:3:sourceLotId&&productId&&quantity>0?3:sourceLotId&&productId?2:sourceLotId?1:0;return <span key={step} className={progress>index?"done":""}>{index+1}. {step}</span>})}</div>

    <div className="production-label-grid">
      <label>1. Source batch<SearchablePicker ariaLabel="Search source batches" value={sourceLotId} options={sourceOptions} placeholder="Search strain, batch, SKU, or METRC package…" disabled={Boolean(run)} onChange={setSourceLotId}/></label>
      <label>2. End product<SearchablePicker ariaLabel="Search finished products" value={productId} options={productOptions} placeholder="Search product name, SKU, brand, or format…" disabled={Boolean(run)} onChange={setProductId}/></label>
      <label>3. Finished quantity<input aria-label="Finished quantity" type="number" min="1" max="500" step="1" value={quantity} disabled={Boolean(run)} onChange={event=>setQuantity(Math.max(1,Math.min(500,Number(event.target.value)||1)))}/></label>
    </div>

    {sourceLotId?<div className="catalog-row"><strong>{source.isLoading?"Loading source evidence…":sourceReady?"✓ Verified source":"Source needs attention"}</strong><small>{source.data?.coa.available?`${source.data.coa.lab_name||"Lab"} · tested ${source.data.coa.date_tested||"date missing"} · ${source.data.coa.overall_status||"status missing"}`:"No verified COA resolved"}</small></div>:null}
    {productId?<div className="catalog-row"><strong>{product.isLoading?"Loading package specifications…":packaging?"✓ Product package configured":"Package setup required"}</strong><span>{packaging?`${fmt(packaging.units_per_package)} units/package · ${fmt(packaging.net_content)} ${packaging.net_content_unit}`:""}</span><small>{packaging?"Product Master package facts will populate the label automatically.":"Configure package facts in Product Master"}</small></div>:null}

    {!run?<div style={{marginTop:16}}><button className="primary" disabled={!sourceLotId||!productId||!sourceReady||!packaging||create.isPending} onClick={()=>create.mutate()}>{create.isPending?"Building preview…":"4. Build & validate label preview"}</button><p className="section-note">This snapshots the current source COA and Product Master package facts. Later catalog edits cannot rewrite what this run used.</p></div>:null}

    {run?<div className="production-label-preview"><div className="eyebrow">4. GENERATED LABEL PREVIEW · {run.status.toUpperCase()}</div><h3>{label.product_name||"Finished product"}</h3><div className="production-label-preview-grid">{DISPLAY_FIELDS.filter(field=>String(label[field]??"").trim()).map(field=><div key={field}><span>{fieldLabel(field)}</span><strong>{label[field]}</strong></div>)}<div><span>Source package</span><strong>{sourcePackage}</strong></div><div><span>Source lot</span><strong>{sourceLot}</strong></div><div><span>Finished quantity</span><strong>{run.quantity} labels</strong></div></div>
      {run.status==="validated"?<div className="production-traceability"><div><strong>5. Scan METRC package tag</strong><p className="section-note">One physical finished-package tag for this label run. Every printed retail label inherits the same traceability identity.</p></div><div className="inline-form"><input autoFocus aria-label="METRC finished package tag" placeholder="Scan physical METRC package tag" value={tag} onChange={event=>setTag(event.target.value)}/><button className="primary" disabled={tag.trim().length<4||assign.isPending} onClick={()=>assign.mutate()}>{assign.isPending?"Validating…":"Assign tag"}</button></div></div>:null}
      {run.metrc_package_tag?<div className="production-traceability"><img src={graphicDataUri(run.traceability.qr)} alt={`QR code for finished METRC package ${run.metrc_package_tag}`}/><div><strong>{run.metrc_package_tag}</strong><img src={graphicDataUri(run.traceability.barcode)} alt={`Code 128 barcode for finished METRC package ${run.metrc_package_tag}`}/><p className="section-note">The database prevents this tag from being reused by another finished package in the organization.</p></div></div>:null}
      {run.status==="tagged"?<div style={{marginTop:16}}><button className="primary" disabled={print.isPending} onClick={()=>print.mutate()}>{print.isPending?"Recording print…":`6. Finalize & print ${run.quantity} labels`}</button></div>:null}
      {["printed","applied","released","fulfilled"].includes(run.status)?<div style={{marginTop:16}}><div className="inline-form"><input aria-label="Reprint reason" placeholder="Reason required for reprint" value={reprintReason} onChange={event=>setReprintReason(event.target.value)}/><button className="secondary" disabled={!reprintReason.trim()||print.isPending} onClick={()=>print.mutate()}>Reprint {run.quantity}</button>{nextStatus?<button className="primary" disabled={transition.isPending} onClick={()=>transition.mutate(nextStatus)}>{nextAction}</button>:null}</div></div>:null}
    </div>:null}

    {run?.metrc_package_tag?<div className="production-label-print-batch" aria-label="Printable retail labels">{copies.map(index=><div className="production-label-copy" key={index}><h3>{label.product_name}</h3>{DISPLAY_FIELDS.filter(field=>field!=="warning_text"&&String(label[field]??"").trim()).map(field=><p key={field}><strong>{fieldLabel(field)}:</strong> {label[field]}</p>)}<p><strong>Source package:</strong> {sourcePackage}</p><p><strong>Source lot:</strong> {sourceLot}</p>{label.warning_text?<p><strong>Warning:</strong> {label.warning_text}</p>:null}<div className="codes"><img src={graphicDataUri(run.traceability.qr)} alt="METRC QR"/><div><img src={graphicDataUri(run.traceability.barcode)} alt="METRC barcode"/><p>{run.metrc_package_tag}</p><p>Retail unit {index+1} of {run.quantity}</p></div></div></div>)}</div>:null}

    {run?<div style={{marginTop:18}}><h3>Audit trail</h3>{run.events.map(event=><div className="label-audit-row" key={event.id}><strong>{eventLabel(event.event_type)}</strong><span>{event.from_status&&event.to_status?`${event.from_status} → ${event.to_status}`:event.to_status||event.from_status}</span><small>{event.actor} · {new Date(event.occurred_at).toLocaleString()}</small></div>)}</div>:null}
    {error?<div className="form-error">{error.message}</div>:null}
  </section>;
}
