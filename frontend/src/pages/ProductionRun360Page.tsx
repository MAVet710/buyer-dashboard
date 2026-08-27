import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type QueueRow = { order_id:string; Order:string; Product:string; Status:string; Planned:number; Actual:number; "Attainment %":number; COGS:number; "Cost / Unit":number; Reservations:number; QA:string; Attention:string };
type Reservation = { id:string; lot_id:string; quantity:number; unit:string; status:string };
type Output = { id:string; product_id:string; position:number; label:string; planned_quantity:number; actual_quantity:number; unit:string; status:string; lot_id:string|null };
type Event = { id:string; stage_key:string; event_type:string; quantity:number|null; unit:string; waste_quantity:number|null; labor_hours:number|null; machine_hours:number|null; notes:string; actor:string; occurred_at:string };
type QA = { id:string; event_type:string; result:string; notes:string; actor:string; occurred_at:string };
type Bom = { id:string; version:number; output_quantity:number; expected_loss_pct:number; active:boolean };
type Standard = { id:string; bom_id:string; standard_labor_hours:number; standard_machine_hours:number; standard_cycle_hours:number; resource_category:string; qa_required:boolean; compliance_checkpoint:string; created_by:string; updated_by:string };
type Variance = {
  expected_output:number;
  actual_output:number;
  output_variance:number;
  output_variance_pct:number|null;
  expected_loss_pct:number;
  expected_labor_hours:number;
  actual_labor_hours:number;
  labor_variance_hours:number;
  labor_variance_pct:number|null;
  expected_machine_hours:number;
  actual_machine_hours:number;
  machine_variance_hours:number;
  machine_variance_pct:number|null;
  expected_cycle_hours:number;
  actual_cycle_hours:number|null;
  cycle_variance_hours:number|null;
  cycle_variance_pct:number|null;
  qa_required:boolean;
  qa_ready:boolean;
  compliance_checkpoint:string;
  resource_category:string;
  standard_configured:boolean;
};
type Detail = {
  order:{ id:string; order_number:string; product_name:string; sku:string; product_format:string; requested_units:number; priority:string; status:string; notes:string; due_at:string|null };
  bom:Bom|null;
  standard:Standard|null;
  variance:Variance;
  requirements:Array<Record<string,unknown>>;
  reservations:Reservation[];
  outputs:Output[];
  events:Event[];
  qa_events:QA[];
  cogs:Record<string,number>;
  planned_output:number;
  actual_output:number;
  attainment_pct:number;
};
type Product = { id:string; sku:string; name:string; item_type:string; base_unit:string };
type ProductionWorkspace = { products:Product[] };
type StandardForm = { standard_labor_hours:number; standard_machine_hours:number; standard_cycle_hours:number; resource_category:string; qa_required:boolean; compliance_checkpoint:string };

const standardValues = (standard:Standard|null):StandardForm => ({
  standard_labor_hours: standard?.standard_labor_hours ?? 0,
  standard_machine_hours: standard?.standard_machine_hours ?? 0,
  standard_cycle_hours: standard?.standard_cycle_hours ?? 0,
  resource_category: standard?.resource_category ?? "",
  qa_required: standard?.qa_required ?? false,
  compliance_checkpoint: standard?.compliance_checkpoint ?? "",
});

export function ProductionRun360Page({ onNavigate, initialOrderId="" }:{ onNavigate:(page:string)=>void; initialOrderId?:string }) {
  const client = useQueryClient();
  const queue = useQuery({ queryKey:["production-run-queue"], queryFn:({signal})=>apiGet<QueueRow[]>("/api/v1/production/orders",signal) });
  const workspace = useQuery({ queryKey:["coman-parity"], queryFn:({signal})=>apiGet<ProductionWorkspace>("/api/v1/coman-parity/workspace",signal) });
  const [selected,setSelected] = useState(initialOrderId);
  useEffect(()=>{ if(initialOrderId) setSelected(initialOrderId); },[initialOrderId]);
  const selectedExists = !selected || !queue.data?.length || queue.data.some(row=>row.order_id===selected);
  const orderId = (selected && selectedExists ? selected : "") || queue.data?.[0]?.order_id || "";
  const detail = useQuery({ queryKey:["production-run-360",orderId], enabled:Boolean(orderId), queryFn:({signal})=>apiGet<Detail>(`/api/v1/production/orders/${orderId}`,signal) });
  useEffect(()=>{ if(queue.data?.length && selected && !queue.data.some(row=>row.order_id===selected)) setSelected(""); },[queue.data,selected]);
  const refresh = async()=>Promise.all([
    client.invalidateQueries({queryKey:["production-run-queue"]}),
    client.invalidateQueries({queryKey:["production-run-360",orderId]}),
    client.invalidateQueries({queryKey:["coman-parity"]}),
  ]);
  return <div className="page production-run-360">
    <div className="page-heading"><div><div className="eyebrow">PRODUCTION · RUN 360</div><h1>Plan, execute, cost, QA, and release the run.</h1><p>One execution surface from BOM requirements through finished output. Inventory and cost events stay on the canonical ledgers.</p></div><div className="heading-actions"><button className="secondary" onClick={()=>onNavigate("Production")}>Production planning</button><button className="secondary" onClick={()=>onNavigate("Package 360")}>Package 360</button></div></div>
    {queue.isLoading?<div className="state">Loading production queue…</div>:null}
    {queue.isError?<div className="warning-banner">{queue.error.message}</div>:null}
    {queue.data?.length?<section className="inventory-panel"><label>Production run<select value={orderId} onChange={event=>setSelected(event.target.value)}>{queue.data.map(row=><option value={row.order_id} key={row.order_id}>{row.Order} · {row.Product} · {row.Status} · {row.Attention}</option>)}</select></label></section>:!queue.isLoading?<div className="info-banner">No production orders exist yet. Create a production job first.</div>:null}
    {detail.isLoading?<div className="state">Building Run 360…</div>:null}
    {detail.isError?<div className="warning-banner">{detail.error.message}</div>:null}
    {detail.data?<RunDetail detail={detail.data} products={workspace.data?.products??[]} onChanged={refresh}/>:null}
  </div>;
}

function RunDetail({ detail, products, onChanged }:{ detail:Detail; products:Product[]; onChanged:()=>void }) {
  const [tab,setTab] = useState<"Execute"|"Standards"|"Materials"|"Outputs"|"QA"|"Costs"|"Timeline">("Execute");
  const reserve = useMutation({ mutationFn:()=>apiPost(`/api/v1/production/orders/${detail.order.id}/reserve`,{}), onSuccess:onChanged });
  const [event,setEvent] = useState({ event_type:"started",stage_key:"execution",quantity:"",unit:"unit",waste_quantity:"",labor_hours:"",machine_hours:"",notes:"" });
  const postEvent = useMutation({ mutationFn:()=>apiPost(`/api/v1/production/orders/${detail.order.id}/events`,numbers(event)), onSuccess:()=>{ setEvent({...event,quantity:"",waste_quantity:"",labor_hours:"",machine_hours:"",notes:""}); onChanged(); } });
  const [output,setOutput] = useState({ product_id:products[0]?.id??"", planned_quantity:detail.order.requested_units, label:"", unit:products[0]?.base_unit??"unit" });
  useEffect(()=>{ if(!output.product_id&&products[0]) setOutput(value=>({...value,product_id:products[0].id,unit:products[0].base_unit})); },[products,output.product_id]);
  const addOutput = useMutation({ mutationFn:()=>apiPost(`/api/v1/production/orders/${detail.order.id}/outputs`,output), onSuccess:onChanged });
  const [actuals,setActuals] = useState<Record<string,string>>({});
  const [lotCodes,setLotCodes] = useState<Record<string,string>>({});
  const postActual = useMutation({ mutationFn:(row:Output)=>apiPost(`/api/v1/production/outputs/${row.id}/actual`,{actual_quantity:Number(actuals[row.id]??row.actual_quantity),lot_code:lotCodes[row.id]??""}), onSuccess:onChanged });
  const [qa,setQa] = useState({event_type:"release",result:"passed",output_id:"",document_reference:"",notes:""});
  const postQa = useMutation({ mutationFn:()=>apiPost(`/api/v1/production/orders/${detail.order.id}/qa`,{...qa,output_id:qa.output_id||null}), onSuccess:onChanged });
  const [cost,setCost] = useState({category:"labor",amount_usd:0,quantity:"",unit:"",source_type:"manual",source_id:"",notes:""});
  const postCost = useMutation({ mutationFn:()=>apiPost(`/api/v1/production/orders/${detail.order.id}/costs`,{...cost,quantity:cost.quantity?Number(cost.quantity):null}), onSuccess:()=>{setCost({...cost,amount_usd:0,quantity:"",notes:""});onChanged();} });
  const [standardForm,setStandardForm] = useState<StandardForm>(()=>standardValues(detail.standard));
  useEffect(()=>{ setStandardForm(standardValues(detail.standard)); },[detail.order.id,detail.standard]);
  const saveStandard = useMutation({ mutationFn:()=>apiPost(`/api/v1/production/orders/${detail.order.id}/standard`,standardForm), onSuccess:onChanged });
  const tabs = ["Execute","Standards","Materials","Outputs","QA","Costs","Timeline"] as const;

  return <>
    <section className="page-heading"><div><div className="eyebrow">{detail.order.order_number}</div><h2>{detail.order.product_name}</h2><p>{detail.order.sku||"No SKU"} · {title(detail.order.product_format)} · Due {date(detail.order.due_at)}</p></div><span className="status-pill">{title(detail.order.status)}</span></section>
    <section className="metrics four"><Metric label="Planned" value={number(detail.planned_output)}/><Metric label="Actual" value={number(detail.actual_output)}/><Metric label="Attainment" value={`${number(detail.attainment_pct)}%`}/><Metric label="Actual COGS" value={money(detail.cogs.total??0)}/></section>
    {detail.variance.standard_configured?<div className={detail.variance.qa_ready?"info-banner":"warning-banner"}>Production standard active · Output {signedPercent(detail.variance.output_variance_pct)} · Labor {signedPercent(detail.variance.labor_variance_pct)} · QA {detail.variance.qa_ready?"ready":"required"}</div>:detail.bom?<div className="info-banner">This run has an active BOM but no execution standard yet. Add the standard once and every run using this BOM version will inherit it.</div>:null}
    <div className="view-tabs parity-tabs">{tabs.map(value=><button className={tab===value?"active":""} onClick={()=>setTab(value)} key={value}>{value}</button>)}</div>

    {tab==="Execute"?<section className="inventory-panel"><div className="eyebrow">RUN EVENT</div><h2>Record what actually happened</h2><div className="form-grid three"><label>Event<select value={event.event_type} onChange={e=>setEvent({...event,event_type:e.target.value})}>{["started","progress","hold","resumed","completed","waste","rework"].map(v=><option key={v} value={v}>{title(v)}</option>)}</select></label><label>Stage<input value={event.stage_key} onChange={e=>setEvent({...event,stage_key:e.target.value})}/></label><label>Quantity<input type="number" value={event.quantity} onChange={e=>setEvent({...event,quantity:e.target.value})}/></label><label>Unit<input value={event.unit} onChange={e=>setEvent({...event,unit:e.target.value})}/></label><label>Waste quantity<input type="number" value={event.waste_quantity} onChange={e=>setEvent({...event,waste_quantity:e.target.value})}/></label><label>Labor hours<input type="number" value={event.labor_hours} onChange={e=>setEvent({...event,labor_hours:e.target.value})}/></label><label>Machine hours<input type="number" value={event.machine_hours} onChange={e=>setEvent({...event,machine_hours:e.target.value})}/></label><label className="full">Notes<textarea value={event.notes} onChange={e=>setEvent({...event,notes:e.target.value})}/></label></div><button className="primary" disabled={postEvent.isPending} onClick={()=>postEvent.mutate()}>Post run event</button><MutationState rows={[postEvent]}/></section>:null}

    {tab==="Standards"?<StandardsPanel detail={detail} value={standardForm} setValue={setStandardForm} save={saveStandard}/>:null}

    {tab==="Materials"?<section className="inventory-panel"><div className="eyebrow">BOM + RESERVATIONS</div><h2>Required vs reserved materials</h2>{detail.requirements.length?<DataTable rows={detail.requirements}/>:<div className="info-banner">No active BOM requirements are linked to this production order.</div>}<button className="primary submit" disabled={!detail.requirements.length||reserve.isPending} onClick={()=>reserve.mutate()}>Reserve BOM materials</button><h3>Reservations</h3>{detail.reservations.length?<DataTable rows={detail.reservations}/>:<div className="info-banner">No materials reserved yet.</div>}<MutationState rows={[reserve]}/></section>:null}

    {tab==="Outputs"?<section className="inventory-panel"><div className="eyebrow">MULTI-OUTPUT EXECUTION</div><h2>Planned and actual outputs</h2>{detail.outputs.length?<div className="table-wrap"><table><thead><tr><th>Output</th><th>Planned</th><th>Actual</th><th>Status</th><th>Lot code</th><th>Post</th></tr></thead><tbody>{detail.outputs.map(row=><tr key={row.id}><td>{row.position}. {row.label}</td><td>{number(row.planned_quantity)} {row.unit}</td><td><input type="number" value={actuals[row.id]??String(row.actual_quantity)} onChange={e=>setActuals({...actuals,[row.id]:e.target.value})}/></td><td>{title(row.status)}</td><td><input value={lotCodes[row.id]??""} placeholder={row.lot_id?"Lot already created":"Finished lot code"} onChange={e=>setLotCodes({...lotCodes,[row.id]:e.target.value})}/></td><td><button className="secondary" disabled={postActual.isPending} onClick={()=>postActual.mutate(row)}>Post actual</button></td></tr>)}</tbody></table></div>:<div className="info-banner">No output rows exist yet.</div>}<h3>Add output</h3><div className="form-grid three"><label>Product<select value={output.product_id} onChange={e=>{const p=products.find(row=>row.id===e.target.value);setOutput({...output,product_id:e.target.value,unit:p?.base_unit??output.unit});}}>{products.map(row=><option value={row.id} key={row.id}>{row.sku} · {row.name}</option>)}</select></label><label>Planned quantity<input type="number" value={output.planned_quantity} onChange={e=>setOutput({...output,planned_quantity:Number(e.target.value)})}/></label><label>Unit<input value={output.unit} onChange={e=>setOutput({...output,unit:e.target.value})}/></label><label>Label<input value={output.label} onChange={e=>setOutput({...output,label:e.target.value})}/></label></div><button className="primary" disabled={!output.product_id||addOutput.isPending} onClick={()=>addOutput.mutate()}>Add planned output</button><MutationState rows={[addOutput,postActual]}/></section>:null}

    {tab==="QA"?<section className="inventory-panel"><div className="eyebrow">QA HOLD / RELEASE</div><h2>Release only with an auditable decision</h2><div className="form-grid three"><label>Decision<select value={qa.event_type} onChange={e=>setQa({...qa,event_type:e.target.value})}>{["hold","release","inspection","coa_review"].map(v=><option key={v} value={v}>{title(v)}</option>)}</select></label><label>Result<select value={qa.result} onChange={e=>setQa({...qa,result:e.target.value})}>{["pending","passed","failed"].map(v=><option key={v} value={v}>{title(v)}</option>)}</select></label><label>Output<select value={qa.output_id} onChange={e=>setQa({...qa,output_id:e.target.value})}><option value="">Whole run</option>{detail.outputs.map(row=><option value={row.id} key={row.id}>{row.label}</option>)}</select></label><label>Document / COA<input value={qa.document_reference} onChange={e=>setQa({...qa,document_reference:e.target.value})}/></label><label className="full">Notes<textarea value={qa.notes} onChange={e=>setQa({...qa,notes:e.target.value})}/></label></div><button className="primary" disabled={postQa.isPending} onClick={()=>postQa.mutate()}>Post QA decision</button><h3>QA history</h3>{detail.qa_events.length?<DataTable rows={detail.qa_events}/>:<div className="info-banner">No QA decisions recorded.</div>}<MutationState rows={[postQa]}/></section>:null}

    {tab==="Costs"?<section className="inventory-panel"><div className="eyebrow">TRUE RUN COGS</div><h2>Cost the actual run</h2><section className="metrics four">{Object.entries(detail.cogs).map(([key,value])=><Metric key={key} label={title(key)} value={money(value)}/>)}</section><div className="form-grid three"><label>Category<select value={cost.category} onChange={e=>setCost({...cost,category:e.target.value})}>{["material","packaging","labor","machine","testing","freight","overhead","waste","other"].map(v=><option value={v} key={v}>{title(v)}</option>)}</select></label><label>Amount<input type="number" min="0" step="0.01" value={cost.amount_usd} onChange={e=>setCost({...cost,amount_usd:Number(e.target.value)})}/></label><label>Quantity<input type="number" value={cost.quantity} onChange={e=>setCost({...cost,quantity:e.target.value})}/></label><label>Unit<input value={cost.unit} onChange={e=>setCost({...cost,unit:e.target.value})}/></label><label>Source reference<input value={cost.source_id} onChange={e=>setCost({...cost,source_id:e.target.value})}/></label><label>Notes<input value={cost.notes} onChange={e=>setCost({...cost,notes:e.target.value})}/></label></div><button className="primary" disabled={cost.amount_usd<0||postCost.isPending} onClick={()=>postCost.mutate()}>Add cost event</button><MutationState rows={[postCost]}/></section>:null}

    {tab==="Timeline"?<section className="inventory-panel"><div className="eyebrow">EXECUTION EVIDENCE</div><h2>Run timeline</h2>{detail.events.length?detail.events.slice().reverse().map(row=><article className="commercial-order-card" key={row.id}><div><strong>{title(row.event_type)}</strong><span className="status-pill">{row.stage_key}</span></div><p>{row.notes||"Production event"}</p><small>{new Date(row.occurred_at).toLocaleString()} · {row.actor}{row.quantity!=null?` · ${number(row.quantity)} ${row.unit}`:""}{row.waste_quantity!=null?` · waste ${number(row.waste_quantity)} ${row.unit}`:""}</small></article>):<div className="info-banner">No run events recorded.</div>}</section>:null}
  </>;
}

function StandardsPanel({ detail, value, setValue, save }:{ detail:Detail; value:StandardForm; setValue:(value:StandardForm)=>void; save:{isPending:boolean;isError:boolean;isSuccess:boolean;error:Error|null;mutate:()=>void} }) {
  if(!detail.bom) return <section className="inventory-panel"><div className="eyebrow">PRODUCTION STANDARDS</div><h2>No active BOM is linked</h2><div className="info-banner">Create an active Product BOM first. Production standards are intentionally version-bound to the canonical BOM rather than stored in a separate recipe system.</div></section>;
  const variance = detail.variance;
  return <section className="inventory-panel">
    <div className="eyebrow">PRODUCTION STANDARDS · BOM V{detail.bom.version}</div>
    <h2>Expected vs actual execution</h2>
    <p>Standards are stored once per BOM version and automatically scaled to this run's requested quantity. Actuals come from the existing Run 360 event history.</p>
    <section className="metrics four">
      <Metric label="Output variance" value={signedPercent(variance.output_variance_pct)}/>
      <Metric label="Labor variance" value={signedPercent(variance.labor_variance_pct)}/>
      <Metric label="Machine variance" value={signedPercent(variance.machine_variance_pct)}/>
      <Metric label="Cycle variance" value={signedPercent(variance.cycle_variance_pct)}/>
    </section>
    <div className="table-wrap"><table><thead><tr><th>Standard</th><th>Expected for this run</th><th>Actual</th><th>Variance</th></tr></thead><tbody>
      <tr><td>Finished output</td><td>{number(variance.expected_output)}</td><td>{number(variance.actual_output)}</td><td>{signedPercent(variance.output_variance_pct)}</td></tr>
      <tr><td>Labor hours</td><td>{hours(variance.expected_labor_hours)}</td><td>{hours(variance.actual_labor_hours)}</td><td>{signedHours(variance.labor_variance_hours)}</td></tr>
      <tr><td>Machine hours</td><td>{hours(variance.expected_machine_hours)}</td><td>{hours(variance.actual_machine_hours)}</td><td>{signedHours(variance.machine_variance_hours)}</td></tr>
      <tr><td>Cycle time</td><td>{hours(variance.expected_cycle_hours)}</td><td>{variance.actual_cycle_hours==null?"Not started":hours(variance.actual_cycle_hours)}</td><td>{variance.cycle_variance_hours==null?"—":signedHours(variance.cycle_variance_hours)}</td></tr>
    </tbody></table></div>
    <div className="form-grid three">
      <label>BOM recipe output<input value={detail.bom.output_quantity} disabled/></label>
      <label>Expected process loss %<input value={detail.bom.expected_loss_pct} disabled/></label>
      <label>Resource category<input value={value.resource_category} placeholder="Extraction, Filling, Packaging…" onChange={e=>setValue({...value,resource_category:e.target.value})}/></label>
      <label>Standard labor hours / BOM batch<input type="number" min="0" step="0.25" value={value.standard_labor_hours} onChange={e=>setValue({...value,standard_labor_hours:Number(e.target.value)})}/></label>
      <label>Standard machine hours / BOM batch<input type="number" min="0" step="0.25" value={value.standard_machine_hours} onChange={e=>setValue({...value,standard_machine_hours:Number(e.target.value)})}/></label>
      <label>Standard cycle hours / BOM batch<input type="number" min="0" step="0.25" value={value.standard_cycle_hours} onChange={e=>setValue({...value,standard_cycle_hours:Number(e.target.value)})}/></label>
      <label><input type="checkbox" checked={value.qa_required} onChange={e=>setValue({...value,qa_required:e.target.checked})}/> QA release required</label>
      <label className="full">Compliance checkpoint<textarea value={value.compliance_checkpoint} placeholder="Required compliance evidence or checkpoint before release" onChange={e=>setValue({...value,compliance_checkpoint:e.target.value})}/></label>
    </div>
    <div className={variance.qa_ready?"info-banner":"warning-banner"}>QA readiness: {variance.qa_ready?"Ready":"Required before release"}{variance.resource_category?` · Resource: ${variance.resource_category}`:""}{variance.compliance_checkpoint?` · Compliance: ${variance.compliance_checkpoint}`:""}</div>
    <button className="primary" disabled={save.isPending} onClick={()=>save.mutate()}>{detail.standard?"Update production standard":"Save production standard"}</button>
    <MutationState rows={[save]}/>
  </section>;
}

function numbers(value:{event_type:string;stage_key:string;quantity:string;unit:string;waste_quantity:string;labor_hours:string;machine_hours:string;notes:string}) { return {...value,quantity:value.quantity?Number(value.quantity):null,waste_quantity:value.waste_quantity?Number(value.waste_quantity):null,labor_hours:value.labor_hours?Number(value.labor_hours):null,machine_hours:value.machine_hours?Number(value.machine_hours):null}; }
function MutationState({rows}:{rows:Array<{isError:boolean;isSuccess:boolean;error:Error|null}>}) { const error=rows.find(row=>row.isError)?.error; return <>{error?<div className="form-error">{error.message}</div>:null}{rows.some(row=>row.isSuccess)?<div className="success-banner">Operational record saved.</div>:null}</>; }
function DataTable({rows}:{rows:Array<Record<string,unknown>>|Reservation[]|QA[]}) { if(!rows.length)return null; const normalized=rows as Array<Record<string,unknown>>; const columns=Object.keys(normalized[0]); return <div className="table-wrap"><table><thead><tr>{columns.map(col=><th key={col}>{title(col)}</th>)}</tr></thead><tbody>{normalized.map((row,index)=><tr key={index}>{columns.map(col=><td key={col}>{format(row[col])}</td>)}</tr>)}</tbody></table></div>; }
function Metric({label,value}:{label:string;value:string|number}) { return <article className="metric"><span>{label}</span><strong>{value}</strong></article>; }
function format(value:unknown) { if(value==null)return "—"; if(typeof value==="number")return number(value); return String(value); }
function title(value:string) { return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase()); }
function number(value:number) { return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:2}); }
function money(value:number) { return Number(value||0).toLocaleString(undefined,{style:"currency",currency:"USD",maximumFractionDigits:2}); }
function date(value:string|null) { return value?new Date(value).toLocaleDateString():"No due date"; }
function signedPercent(value:number|null) { if(value==null)return "—"; const normalized=Math.abs(value)<0.005?0:value; return `${normalized>0?"+":""}${number(normalized)}%`; }
function hours(value:number) { return `${number(value)} hr`; }
function signedHours(value:number) { const normalized=Math.abs(value)<0.005?0:value; return `${normalized>0?"+":""}${number(normalized)} hr`; }
