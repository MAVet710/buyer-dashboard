import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type InventorySummary = { lot_id:string;product_id:string;package_id:string;lot_code:string;product_name:string;sku:string;location:string;status:string;on_hand:number;inventory_unit:string };
type CoaResult = { analysis:string;key?:string;name:string;value:number|null;value_text:string;units:string };
type CoaSource = { available:boolean;needs_confirmation:boolean;document_id:string;filename:string;lab_name:string;lab_license_number:string;date_tested:string;overall_status:string;total_thc:number|null;total_cbd:number|null;total_cannabinoids:number|null;total_terpenes:number|null;results:CoaResult[] };
type InventorySource = InventorySummary & { label:Record<string,string>;coa:CoaSource;source_summary:Record<string,string> };
type Product = { id:string;sku:string;name:string;item_type:string;base_unit:string;active:boolean;brand?:string;category?:string;product_format?:string };
type Packaging = { net_content:number;net_content_unit:string;units_per_package:number;sellable_unit:string;case_pack:number;warning_text:string;label_layout:"compact_single"|"compact_split"|"bulk_barcode";label_width_in:number;label_height_in:number;label_source_count:number };
type ProductDetail = { product:Product;profile:{brand:string;category:string;subcategory:string;strain:string;manufacturer:string;product_format:string;production_enabled:boolean}|null;packaging:Packaging|null };
type Graphic = { value:string;svg:string;format?:string };
type LabelEvent = { id:string;event_type:string;from_status:string;to_status:string;actor:string;details:Record<string,unknown>;occurred_at:string };
type SourceSnapshot = { lot_id:string;package_id:string;lot_code:string;product_id:string;product_name:string;inventory_unit:string;label:Record<string,string>;coa:CoaSource;source_summary:Record<string,string> };
type PrintLayout = { layout:"compact_single"|"compact_split"|"bulk_barcode";width_in:number;height_in:number;source_count:number };
type LabelRun = {
  id:string;product_id:string;quantity:number;expected_material_quantity:number;expected_material_unit:string;status:string;metrc_package_tag:string;created_by:string;printed_by:string;
  created_at:string;printed_at:string|null;snapshot:{source:SourceSnapshot;sources?:SourceSnapshot[];product:Record<string,unknown>;label:Record<string,string>;quantity:number;print_layout?:PrintLayout;expected_material_quantity:number;expected_material_unit:string;sandbox?:{sandbox_test_pass?:boolean;bypassed_checks?:string[]}};
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
function displayDate(value:string|undefined){
  const raw=String(value??"").trim();
  const match=raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match?`${match[2]}/${match[3]}/${match[1]}`:raw;
}
function resultValue(row:CoaResult){
  const raw=String(row.value_text??"").trim()||(row.value==null?"":fmt(Number(row.value)));
  if(!raw)return "";
  const units=String(row.units??"").trim();
  if(!units)return raw;
  if(units==="%"||units.toLowerCase()==="percent")return raw.includes("%")?raw:`${raw}%`;
  return raw.toLowerCase().includes(units.toLowerCase())?raw:`${raw} ${units}`;
}
function analytes(source:SourceSnapshot|undefined,kind:"cannabinoids"|"terpenes",limit:number){
  const rows=source?.coa?.results??[];
  return rows.filter(row=>String(row.analysis??"").toLowerCase().includes(kind.slice(0,-1))).filter(row=>Boolean(resultValue(row))).slice(0,limit);
}
function sourceReady(source:InventorySource|undefined){
  return Boolean(source?.coa.available&&["pass","passed"].includes(String(source.coa.overall_status??"").toLowerCase())&&source.coa.date_tested&&!source.coa.needs_confirmation);
}
function layoutName(layout:string){
  if(layout==="compact_split")return "Compact split";
  if(layout==="bulk_barcode")return "Wide barcode / bulk";
  return "Compact single-product";
}

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
    <input role="combobox" aria-label={ariaLabel} aria-expanded={open} autoComplete="off" placeholder={placeholder} disabled={disabled} value={query}
      onFocus={()=>setOpen(true)} onBlur={()=>window.setTimeout(()=>setOpen(false),120)} onChange={event=>{setQuery(event.target.value);setOpen(true);if(value)onChange("")}}/>
    {open&&!disabled?<div className="label-search-menu" role="listbox">
      {filtered.length?filtered.map(option=><button key={option.value} type="button" role="option" aria-selected={option.value===value} onMouseDown={event=>event.preventDefault()} onClick={()=>{onChange(option.value);setQuery(option.label);setOpen(false)}}>{option.label}</button>):<div className="label-search-empty">No matches</div>}
    </div>:null}
  </div>;
}

function AnalyteList({title,rows,total}:{title:string;rows:CoaResult[];total?:number|null}){
  return <div className="label-analytes"><strong>{title}</strong>{rows.map((row,index)=><div key={`${row.key||row.name}-${index}`}><span>{row.name}</span><b>{resultValue(row)}</b></div>)}{total!=null?<div className="label-total"><span>Total {title}</span><b>{fmt(Number(total))}%</b></div>:null}</div>;
}

function SourcePanel({source,index}:{source:SourceSnapshot;index?:number}){
  const label=source.label??{};
  const title=String(label.strain||source.product_name||`Source ${Number(index??0)+1}`);
  return <section className="label-source-panel">
    <h4>{index!=null?`${index+1} - `:""}{title}</h4>
    <p>Harvest: {displayDate(label.harvest_date)} · Tested: {displayDate(label.test_date||source.coa.date_tested)}</p>
    <p>Batch: {label.batch_number||source.lot_code}</p>
    <AnalyteList title="Cannabinoids" rows={analytes(source,"cannabinoids",7)} total={source.coa.total_cannabinoids}/>
    <AnalyteList title="Terpenes" rows={analytes(source,"terpenes",4)} total={source.coa.total_terpenes}/>
  </section>;
}

function LabelHeader({label}:{label:Record<string,string>}){
  return <header className="printed-label-header"><h3>{label.product_name||"Finished product"}</h3><strong>{label.net_contents||label.package_size}</strong>{label.package_composition?<span>{label.package_composition}</span>:null}</header>;
}

function CompactSingleLabel({run,index,sources}:{run:LabelRun;index:number;sources:SourceSnapshot[]}){
  const label=run.snapshot.label??{};
  const source=sources[0];
  const sourceLabel=source?.label??{};
  return <>
    <LabelHeader label={label}/>
    <div className="printed-date-strip"><span>Harvest: {displayDate(sourceLabel.harvest_date)}</span><span>Packaged: {displayDate(run.created_at)}</span><span>Expires: {displayDate(sourceLabel.expiration_date)}</span><span>Tested: {displayDate(sourceLabel.test_date||source?.coa.date_tested)}</span></div>
    <div className="printed-batch">Batch#: {sourceLabel.batch_number||source?.lot_code}</div>
    <div className="printed-two-column">
      <AnalyteList title="Cannabinoids" rows={analytes(source,"cannabinoids",8)} total={source?.coa.total_cannabinoids}/>
      <AnalyteList title="Terpenes" rows={analytes(source,"terpenes",6)} total={source?.coa.total_terpenes}/>
    </div>
    <div className="printed-footer"><div><p>Cultivated by {sourceLabel.cultivated_by||"—"}</p><p>{sourceLabel.cultivator_license}</p><p>Manufactured by {label.manufacturer||sourceLabel.manufacturer||label.facility_name}</p><p>{label.license_number}</p></div><img src={graphicDataUri(run.traceability.qr)} alt="METRC QR"/></div>
    <div className="printed-unit-id">#{index+1} / {run.quantity}</div>
  </>;
}

function CompactSplitLabel({run,index,sources}:{run:LabelRun;index:number;sources:SourceSnapshot[]}){
  const label=run.snapshot.label??{};
  const primary=sources[0];
  const primaryLabel=primary?.label??{};
  return <>
    <LabelHeader label={label}/>
    {sources.length>=2?<div className="printed-split-sources">{sources.slice(0,2).map((source,sourceIndex)=><SourcePanel key={source.lot_id} source={source} index={sourceIndex}/>)}</div>:<>
      <div className="printed-date-strip"><span>Harvest: {displayDate(primaryLabel.harvest_date)}</span><span>Packaged: {displayDate(run.created_at)}</span><span>Expires: {displayDate(primaryLabel.expiration_date)}</span><span>Tested: {displayDate(primaryLabel.test_date||primary?.coa.date_tested)}</span></div>
      <div className="printed-batch">Batch#: {primaryLabel.batch_number||primary?.lot_code}</div>
      <div className="printed-split-sources"><section className="label-source-panel"><AnalyteList title="Cannabinoids" rows={analytes(primary,"cannabinoids",9)} total={primary?.coa.total_cannabinoids}/></section><section className="label-source-panel"><AnalyteList title="Terpenes" rows={analytes(primary,"terpenes",8)} total={primary?.coa.total_terpenes}/><p className="source-party">Cultivated by {primaryLabel.cultivated_by}<br/>{primaryLabel.cultivator_license}<br/>Manufactured by {label.manufacturer||label.facility_name}<br/>{label.license_number}</p></section></div>
    </>}
    <div className="printed-footer compact-split-footer"><div><p>{label.warning_text}</p></div><img src={graphicDataUri(run.traceability.qr)} alt="METRC QR"/></div>
    <div className="printed-unit-id">#{index+1} / {run.quantity}</div>
  </>;
}

function BulkBarcodeLabel({run,index,sources}:{run:LabelRun;index:number;sources:SourceSnapshot[]}){
  const label=run.snapshot.label??{};
  const source=sources[0];
  const sourceLabel=source?.label??{};
  return <div className="bulk-label-grid">
    <div className="bulk-barcode"><img src={graphicDataUri(run.traceability.barcode)} alt="METRC barcode"/><strong>{run.metrc_package_tag}</strong></div>
    <div className="bulk-main"><h3>{label.product_name}</h3><div className="bulk-meta"><span>Tested: {displayDate(sourceLabel.test_date||source?.coa.date_tested)}</span><span>Packed: {displayDate(run.created_at)}</span><span>Net Wgt: {label.net_contents||label.package_size}</span><span>Batch: {sourceLabel.batch_number||source?.lot_code}</span></div><div className="bulk-potency"><span>TAC: {label.total_cannabinoids||"—"}</span><span>THC: {label.total_thc||"—"}</span><span>CBD: {label.total_cbd||"—"}</span><span>Total Terpenes: {label.total_terpenes||"—"}</span></div><small>Cultivated by {sourceLabel.cultivated_by} {sourceLabel.cultivator_license} · Packaged by {label.manufacturer||label.facility_name} {label.license_number}</small></div>
    <div className="printed-unit-id">{index+1}/{run.quantity}</div>
  </div>;
}

export function InventoryDrivenLabelWorkflow({sandboxTestPass=false}:{sandboxTestPass?:boolean}){
  const inventory=useQuery({queryKey:["label-studio-inventory-summaries"],queryFn:({signal})=>apiGet<unknown>("/api/v1/label-printing/inventory-sources?summary=true",signal)});
  const products=useQuery({queryKey:["label-studio-finished-products"],queryFn:({signal})=>apiGet<unknown>("/api/v1/product-master?operation=production&search=&status=active&item_type=finished_good",signal)});
  const inventoryRows=useMemo<InventorySummary[]>(()=>Array.isArray(inventory.data)?inventory.data.filter((row):row is InventorySummary=>Boolean(row&&typeof row==="object"&&"lot_id" in row&&"product_name" in row)):[],[inventory.data]);
  const productRows=useMemo<Product[]>(()=>Array.isArray(products.data)?products.data.filter((row):row is Product=>Boolean(row&&typeof row==="object"&&"id" in row&&"name" in row)):[],[products.data]);
  const sourceOptions=useMemo<SearchOption[]>(()=>inventoryRows.map(row=>({value:row.lot_id,label:sourceName(row),searchText:[row.product_name,row.lot_code,row.package_id,row.sku,row.location].join(" ").toLowerCase()})),[inventoryRows]);
  const productOptions=useMemo<SearchOption[]>(()=>productRows.map(row=>({value:row.id,label:productName(row),searchText:[row.name,row.sku,row.brand,row.category,row.product_format].join(" ").toLowerCase()})),[productRows]);
  const [sourceLotId,setSourceLotId]=useState("");
  const [secondarySourceLotId,setSecondarySourceLotId]=useState("");
  const [productId,setProductId]=useState("");
  const [quantity,setQuantity]=useState(1);
  const [tag,setTag]=useState("");
  const [run,setRun]=useState<LabelRun|null>(null);
  const [reprintReason,setReprintReason]=useState("");
  const source=useQuery({queryKey:["label-studio-production-source",sourceLotId],queryFn:({signal})=>apiGet<InventorySource>(`/api/v1/label-printing/inventory-sources/${encodeURIComponent(sourceLotId)}`,signal),enabled:Boolean(sourceLotId)});
  const secondarySource=useQuery({queryKey:["label-studio-production-source",secondarySourceLotId],queryFn:({signal})=>apiGet<InventorySource>(`/api/v1/label-printing/inventory-sources/${encodeURIComponent(secondarySourceLotId)}`,signal),enabled:Boolean(secondarySourceLotId)});
  const product=useQuery({queryKey:["label-studio-production-product",productId],queryFn:({signal})=>apiGet<ProductDetail>(`/api/v1/product-master/${encodeURIComponent(productId)}`,signal),enabled:Boolean(productId)});
  const packaging=product.data?.packaging;
  const needsSecondSource=Number(packaging?.label_source_count??1)===2;
  useEffect(()=>{if(packaging&&!needsSecondSource)setSecondarySourceLotId("");},[packaging,needsSecondSource]);
  const create=useMutation({mutationFn:()=>apiPost<LabelRun>("/api/v1/label-printing/production-runs",{source_lot_id:sourceLotId,...(needsSecondSource?{secondary_source_lot_id:secondarySourceLotId}:{}),product_id:productId,quantity}),onSuccess:value=>setRun(value)});
  const assign=useMutation({mutationFn:()=>apiPost<LabelRun>(`/api/v1/label-printing/production-runs/${run?.id}/tag`,{metrc_package_tag:tag.trim()}),onSuccess:value=>setRun(value)});
  const print=useMutation({mutationFn:()=>apiPost<LabelRun>(`/api/v1/label-printing/production-runs/${run?.id}/print`,{copies:run?.quantity,reason:run?.status==="tagged"?"":reprintReason.trim()}),onSuccess:value=>{setRun(value);setReprintReason("");window.setTimeout(()=>window.print(),50)}});
  const transition=useMutation({mutationFn:(status:string)=>apiPost<LabelRun>(`/api/v1/label-printing/production-runs/${run?.id}/transition`,{status,note:""}),onSuccess:value=>setRun(value)});
  const reset=()=>{setSourceLotId("");setSecondarySourceLotId("");setProductId("");setQuantity(1);setTag("");setRun(null);setReprintReason("");create.reset();assign.reset();print.reset();transition.reset()};
  const error=create.error||assign.error||print.error||transition.error||source.error||secondarySource.error||product.error;
  const primaryVerified=sourceReady(source.data);
  const secondaryVerified=sourceReady(secondarySource.data);
  const primaryReady=sandboxTestPass||primaryVerified;
  const secondReady=!needsSecondSource||sandboxTestPass||secondaryVerified;
  const sources=run?.snapshot.sources?.length?run.snapshot.sources:[run?.snapshot.source].filter(Boolean) as SourceSnapshot[];
  const label=run?.snapshot?.label??{};
  const copies=run?Array.from({length:Math.max(1,Math.min(run.quantity,500))},(_,index)=>index):[];
  const printLayout:PrintLayout=run?.snapshot.print_layout??{layout:packaging?.label_layout??"compact_single",width_in:Number(packaging?.label_width_in??3.5),height_in:Number(packaging?.label_height_in??2.1),source_count:Number(packaging?.label_source_count??1)};
  const nextStatus=run?.status==="printed"?"applied":run?.status==="applied"?"released":run?.status==="released"?"fulfilled":run?.status==="fulfilled"?"archived":"";
  const nextAction=nextStatus==="applied"?"Mark labels applied":nextStatus==="released"?"Release finished package":nextStatus==="fulfilled"?"Mark fulfilled":nextStatus==="archived"?"Archive run":"";
  const sourceConflict=needsSecondSource&&Boolean(sourceLotId)&&sourceLotId===secondarySourceLotId;

  return <section className="inventory-panel production-label-workflow">
    <style>{`
      .production-label-workflow{margin-bottom:28px}.sandbox-test-pass{margin:0 0 16px;padding:12px 14px;border:2px solid currentColor;border-radius:12px}.sandbox-test-pass strong{display:block;font-size:13px}.sandbox-test-pass small{display:block;margin-top:4px;line-height:1.35}.label-flow{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:16px 0}.label-flow span{padding:9px 8px;border:1px solid var(--border);border-radius:10px;text-align:center;font-size:12px}.label-flow span.done{font-weight:700;border-color:currentColor}.production-label-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.production-label-grid label{display:flex;flex-direction:column;gap:6px}.label-search-picker{position:relative}.label-search-picker>input{width:100%}.label-search-menu{position:absolute;z-index:40;left:0;right:0;top:calc(100% + 4px);max-height:260px;overflow:auto;border:1px solid var(--border);border-radius:10px;background:Canvas;color:CanvasText;box-shadow:0 12px 28px rgba(0,0,0,.18);padding:6px}.label-search-menu button{display:block;width:100%;text-align:left;border:0;background:transparent;color:inherit;padding:9px 10px;border-radius:8px;font:inherit}.label-search-menu button:hover,.label-search-menu button:focus{background:rgba(127,127,127,.14)}.label-search-empty{padding:10px;opacity:.7}.production-label-preview{margin-top:18px;border:1px solid var(--border);border-radius:14px;padding:18px}.production-label-preview-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 18px}.production-label-preview-grid div{display:flex;justify-content:space-between;gap:16px;border-bottom:1px solid rgba(127,127,127,.15);padding:5px 0}.production-label-preview-grid span{opacity:.7}.production-traceability{display:grid;grid-template-columns:140px 1fr;gap:18px;align-items:center;margin-top:14px}.production-traceability img{max-width:100%}.label-audit-row{display:grid;grid-template-columns:150px 1fr 180px;gap:10px;padding:7px 0;border-bottom:1px solid rgba(127,127,127,.15);font-size:12px}
      .production-label-copy{position:relative;box-sizing:border-box;border:1px solid #222;padding:.10in;background:#fff;color:#000;width:${printLayout.width_in}in;height:${printLayout.height_in}in;margin:12px 0;overflow:hidden;font-family:Arial,sans-serif}.production-label-copy:not(:first-child){display:none}.printed-label-header{text-align:center;border-bottom:1px solid #111;padding-bottom:4px}.printed-label-header h3{margin:0;font-size:15px;line-height:1.05}.printed-label-header strong,.printed-label-header span{display:block;font-size:9px;line-height:1.15}.printed-date-strip{display:grid;grid-template-columns:1fr 1fr;gap:1px 8px;padding:4px 0;font-size:7.5px;line-height:1.15}.printed-batch{font-size:8px;font-weight:700;border-bottom:1px solid #111;padding-bottom:3px}.printed-two-column,.printed-split-sources{display:grid;grid-template-columns:1fr 1fr;gap:8px}.printed-split-sources{gap:0}.label-source-panel{padding:4px 6px 2px 0;min-width:0}.label-source-panel+ .label-source-panel{border-left:1px solid #111;padding-left:6px;padding-right:0}.label-source-panel h4{font-size:9px;margin:0 0 2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.label-source-panel p{font-size:6.5px;margin:1px 0;line-height:1.15}.label-analytes>strong{display:block;font-size:7.5px;text-decoration:underline;margin:2px 0}.label-analytes>div{display:flex;justify-content:space-between;gap:5px;font-size:6.5px;line-height:1.12}.label-analytes b{font-weight:600;white-space:nowrap}.label-total{border-top:1px solid #555;margin-top:2px;padding-top:1px;font-weight:700}.printed-footer{position:absolute;left:.10in;right:.10in;bottom:.08in;display:grid;grid-template-columns:1fr .42in;align-items:end;gap:5px;border-top:1px solid #111;padding-top:3px}.printed-footer p{font-size:6px;margin:0;line-height:1.1}.printed-footer img{width:.38in;height:.38in;justify-self:end}.compact-split-footer{bottom:.06in}.source-party{margin-top:4px!important;border-top:1px solid #777;padding-top:2px}.printed-unit-id{position:absolute;right:.03in;bottom:.01in;font-size:5.5px}.bulk-label-grid{height:100%;display:grid;grid-template-columns:1.05in 1fr;gap:.08in;align-items:center}.bulk-barcode{display:flex;flex-direction:column;justify-content:center;align-items:center;min-width:0}.bulk-barcode img{width:100%;max-height:${Math.max(.45,printLayout.height_in-.35)}in}.bulk-barcode strong{font-size:6px;overflow-wrap:anywhere;text-align:center}.bulk-main h3{font-size:12px;margin:0 0 4px}.bulk-meta,.bulk-potency{display:grid;grid-template-columns:1fr 1fr;gap:1px 8px;font-size:7px}.bulk-potency{margin:4px 0;font-weight:700}.bulk-main small{font-size:6px;line-height:1.1;display:block}
      @media(max-width:850px){.label-flow,.production-label-grid{grid-template-columns:1fr 1fr}.production-label-preview-grid{grid-template-columns:1fr}.production-traceability{grid-template-columns:1fr}.label-audit-row{grid-template-columns:1fr}}@media print{@page{size:${printLayout.width_in}in ${printLayout.height_in}in;margin:0}body *{visibility:hidden!important}.production-label-print-batch,.production-label-print-batch *{visibility:visible!important}.production-label-print-batch{position:absolute!important;left:0!important;top:0!important;width:${printLayout.width_in}in!important}.production-label-copy{display:block!important;break-after:page;page-break-after:always;margin:0!important;border:0!important;width:${printLayout.width_in}in!important;height:${printLayout.height_in}in!important}.production-label-copy:last-child{break-after:auto;page-break-after:auto}}
    `}</style>
    {sandboxTestPass?<div className="sandbox-test-pass" role="status"><strong>DEV SANDBOX · ALL OPERATIONAL DATA IS TEST DATA · PRINT TEST PASS ACTIVE</strong><small>This pass is restricted to the DEV role inside dev-sandbox / SANDBOX. Missing or non-passing COA readiness and sandbox METRC tag availability can be bypassed for print testing. Product/facility scope, tag format, local tag uniqueness, and production safeguards remain enforced.</small></div>:null}
    <div className="eyebrow">LABEL STUDIO · CREATE FROM INVENTORY</div>
    <div className="page-heading"><div><h2>Create the finished label</h2><p>Search the tested source package, choose the finished product, verify its saved label layout and stock size, scan the finished METRC package tag, and print.</p></div>{run?<button className="secondary" onClick={reset}>Start new label run</button>:null}</div>
    <div className="label-flow">{FLOW.map((step,index)=>{const progress=run?run.status==="validated"?4:run.status==="tagged"?5:["printed","applied","released","fulfilled","archived"].includes(run.status)?6:3:sourceLotId&&productId&&quantity>0?3:sourceLotId&&productId?2:sourceLotId?1:0;return <span key={step} className={progress>index?"done":""}>{index+1}. {step}</span>})}</div>

    <div className="production-label-grid">
      <label>1. Source batch<SearchablePicker ariaLabel="Search source batches" value={sourceLotId} options={sourceOptions} placeholder="Search strain, batch, SKU, or METRC package…" disabled={Boolean(run)} onChange={setSourceLotId}/></label>
      <label>2. End product<SearchablePicker ariaLabel="Search finished products" value={productId} options={productOptions} placeholder="Search product name, SKU, brand, or format…" disabled={Boolean(run)} onChange={setProductId}/></label>
      <label>3. Finished quantity<input aria-label="Finished quantity" type="number" min="1" max="500" step="1" value={quantity} disabled={Boolean(run)} onChange={event=>setQuantity(Math.max(1,Math.min(500,Number(event.target.value)||1)))}/></label>
      {needsSecondSource?<label>Second tested source<SearchablePicker ariaLabel="Search second source batch" value={secondarySourceLotId} options={sourceOptions.filter(option=>option.value!==sourceLotId)} placeholder="Search second strain or METRC package…" disabled={Boolean(run)} onChange={setSecondarySourceLotId}/></label>:null}
    </div>

    {sourceLotId?<div className="catalog-row"><strong>{source.isLoading?"Loading source evidence…":primaryVerified?"✓ Verified source":sandboxTestPass?"✓ DEV Sandbox test pass":"Source needs attention"}</strong><small>{primaryVerified&&source.data?.coa.available?`${source.data.coa.lab_name||"Lab"} · tested ${source.data.coa.date_tested||"date missing"} · ${source.data.coa.overall_status||"status missing"}`:sandboxTestPass?"Sandbox test data · COA readiness will be recorded as bypassed for this print test":"No verified passing COA resolved"}</small></div>:null}
    {needsSecondSource&&secondarySourceLotId?<div className="catalog-row"><strong>{secondarySource.isLoading?"Loading second source…":secondaryVerified?"✓ Second source verified":sandboxTestPass?"✓ DEV Sandbox test pass":"Second source needs attention"}</strong><small>{secondaryVerified&&secondarySource.data?.coa.available?`${secondarySource.data.coa.lab_name||"Lab"} · tested ${secondarySource.data.coa.date_tested||"date missing"} · ${secondarySource.data.coa.overall_status||"status missing"}`:sandboxTestPass?"Sandbox test data · second-source COA readiness will be recorded as bypassed":"No verified passing COA resolved"}</small></div>:null}
    {productId?<div className="catalog-row"><strong>{product.isLoading?"Loading package specifications…":packaging?"✓ Product label configured":"Package setup required"}</strong><span>{packaging?`${layoutName(packaging.label_layout)} · ${packaging.label_width_in} × ${packaging.label_height_in} in`:""}</span><small>{packaging?`${fmt(packaging.units_per_package)} units/package · ${fmt(packaging.net_content)} ${packaging.net_content_unit} · ${packaging.label_source_count} tested source${packaging.label_source_count===1?"":"s"}`:"Configure package and label defaults in Product Master"}</small></div>:null}
    {sourceConflict?<div className="form-error">Choose two different source packages for a Duo label.</div>:null}

    {!run?<div style={{marginTop:16}}><button className="primary" disabled={!sourceLotId||!productId||!primaryReady||!secondReady||sourceConflict||!packaging||create.isPending} onClick={()=>create.mutate()}>{create.isPending?"Building preview…":"4. Build & validate label preview"}</button><p className="section-note">Label Studio snapshots the selected source testing and Product Master print preset. It does not reserve, consume, or validate a production quantity of source material.{sandboxTestPass?" DEV Sandbox test-pass use is written into the run audit trail.":""}</p></div>:null}

    {run?<div className="production-label-preview"><div className="eyebrow">4. GENERATED LABEL PREVIEW · {run.status.toUpperCase()}</div><h3>{label.product_name||"Finished product"}</h3>{run.snapshot.sandbox?.sandbox_test_pass?<div className="sandbox-test-pass"><strong>Sandbox test-pass recorded on this run</strong><small>{run.snapshot.sandbox.bypassed_checks?.length?`Bypassed: ${run.snapshot.sandbox.bypassed_checks.join(", ")}`:"No source-readiness checks needed bypassing."}</small></div>:null}<div className="production-label-preview-grid"><div><span>Print layout</span><strong>{layoutName(printLayout.layout)}</strong></div><div><span>Label stock</span><strong>{printLayout.width_in} × {printLayout.height_in} in</strong></div><div><span>Tested sources</span><strong>{sources.length}</strong></div>{DISPLAY_FIELDS.filter(field=>String(label[field]??"").trim()).map(field=><div key={field}><span>{fieldLabel(field)}</span><strong>{label[field]}</strong></div>)}{sources.map((item,index)=><div key={item.lot_id}><span>{sources.length>1?`Source ${index+1}`:"Source package"}</span><strong>{item.package_id||item.lot_code}</strong></div>)}<div><span>Finished quantity</span><strong>{run.quantity} labels</strong></div></div>
      {run.status==="validated"?<div className="production-traceability"><div><strong>5. Scan METRC package tag</strong><p className="section-note">{sandboxTestPass?"DEV Sandbox accepts a test package tag without requiring it to be available in synchronized sandbox METRC inventory. Tag format and local uniqueness are still enforced, and a production METRC mapping will refuse the pass.":"One physical finished-package tag for this label run. Every printed retail label inherits the same traceability identity."}</p></div><div className="inline-form"><input autoFocus aria-label="METRC finished package tag" placeholder={sandboxTestPass?"Scan or enter sandbox test package tag":"Scan physical METRC package tag"} value={tag} onChange={event=>setTag(event.target.value)}/><button className="primary" disabled={tag.trim().length<4||assign.isPending} onClick={()=>assign.mutate()}>{assign.isPending?"Validating…":"Assign tag"}</button></div></div>:null}
      {run.metrc_package_tag?<div className="production-traceability"><img src={graphicDataUri(run.traceability.qr)} alt={`QR code for finished METRC package ${run.metrc_package_tag}`}/><div><strong>{run.metrc_package_tag}</strong><img src={graphicDataUri(run.traceability.barcode)} alt={`Code 128 barcode for finished METRC package ${run.metrc_package_tag}`}/><p className="section-note">The saved Product Master stock size and layout will be used when the browser print dialog opens.</p></div></div>:null}
      {run.status==="tagged"?<div style={{marginTop:16}}><button className="primary" disabled={print.isPending} onClick={()=>print.mutate()}>{print.isPending?"Recording print…":`6. Finalize & print ${run.quantity} labels`}</button></div>:null}
      {["printed","applied","released","fulfilled"].includes(run.status)?<div style={{marginTop:16}}><div className="inline-form"><input aria-label="Reprint reason" placeholder="Reason required for reprint" value={reprintReason} onChange={event=>setReprintReason(event.target.value)}/><button className="secondary" disabled={!reprintReason.trim()||print.isPending} onClick={()=>print.mutate()}>Reprint {run.quantity}</button>{nextStatus?<button className="primary" disabled={transition.isPending} onClick={()=>transition.mutate(nextStatus)}>{nextAction}</button>:null}</div></div>:null}
    </div>:null}

    {run?.metrc_package_tag?<div className="production-label-print-batch" aria-label="Printable retail labels">{copies.map(index=><div className={`production-label-copy layout-${printLayout.layout}`} key={index} data-layout={printLayout.layout} data-label-width={printLayout.width_in} data-label-height={printLayout.height_in}>{printLayout.layout==="compact_split"?<CompactSplitLabel run={run} index={index} sources={sources}/>:printLayout.layout==="bulk_barcode"?<BulkBarcodeLabel run={run} index={index} sources={sources}/>:<CompactSingleLabel run={run} index={index} sources={sources}/>}</div>)}</div>:null}

    {run?<div style={{marginTop:18}}><h3>Audit trail</h3>{run.events.map(event=><div className="label-audit-row" key={event.id}><strong>{eventLabel(event.event_type)}</strong><span>{event.from_status&&event.to_status?`${event.from_status} → ${event.to_status}`:event.to_status||event.from_status}</span><small>{event.actor} · {new Date(event.occurred_at).toLocaleString()}</small></div>)}</div>:null}
    {error?<div className="form-error">{error.message}</div>:null}
  </section>;
}
