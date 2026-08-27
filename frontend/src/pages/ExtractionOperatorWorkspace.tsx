import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../lib/api";

type OperatorMode = "today" | "runs";
type Stage = { key:string; label:string; qa_gate?:boolean; release_gate?:boolean; optional?:boolean; output_fields?:string[] };
type Workflow = { key:string; label:string; method:string; stages:Stage[] };
type Run = {
  id:string; batch_number:string; method:string; workflow_key:string; current_stage_key:string; status:string; release_status:string;
  strain:string; operator:string; final_output_g?:number; intermediate_product_type?:string; final_product_type?:string;
  formulation_used?:boolean; formulation_base_g?:number; terpene_handling_mode?:string; terpene_type?:string; terpene_source?:string;
  terpene_percentage?:number; terpene_weight_g?:number;
};
type RunInput = { id:string; lot_id:string; reserved_quantity:number; consumed_quantity:number; unit:string };
type Lot = { lot_id:string; product_name:string; lot_code:string; compliance_package_id:string; available:number; unit:string; location?:string };
type StageEvent = {
  id:string; stage_key:string; event_type:string; input_weight_g:number|null; output_weight_g:number|null; loss_weight_g:number|null;
  loss_reason:string; stage_output_field?:string; metrc_stage_input_id?:string; metrc_stage_output_id?:string; operator:string; notes:string; occurred_at:string;
};
type Detail = { run:Run; workflow:Workflow; events:StageEvent[]; mass_balance:Record<string,number>; cogs:Record<string,number> };
type StageForm = {
  input_weight_g:number; output_weight_g:number; loss_reason:string; notes:string; stage_output_field:string;
  metrc_stage_input_id:string; metrc_stage_output_id:string; intermediate_product_type:string; final_product_type:string;
  formulation_base_g:number; terpene_handling_mode:string; terpene_type:string; terpene_source:string; terpene_percentage:number; terpene_weight_g:number;
};
type StageAction = "started" | "measurement" | "completed" | "hold" | "released";

const CLOSED = new Set(["complete", "cancelled", "failed"]);
const TERPENE_MODES = ["Native / No Add-Back", "Reintroduced Cannabis Terpenes", "Botanically Derived Terpenes", "Terp Fraction Recombined", "Custom Blend"];
const emptyForm = ():StageForm => ({
  input_weight_g:0, output_weight_g:0, loss_reason:"", notes:"", stage_output_field:"", metrc_stage_input_id:"", metrc_stage_output_id:"",
  intermediate_product_type:"", final_product_type:"", formulation_base_g:0, terpene_handling_mode:"Native / No Add-Back",
  terpene_type:"", terpene_source:"", terpene_percentage:0, terpene_weight_g:0,
});

export function ExtractionOperatorWorkspace({ mode, onOpenAdvanced }: { mode:OperatorMode; onOpenAdvanced:(runId?:string)=>void }) {
  const client = useQueryClient();
  const [selected, setSelected] = useState("");
  const [search, setSearch] = useState("");
  const [showClosed, setShowClosed] = useState(false);
  const [creating, setCreating] = useState(false);

  const runs = useQuery({ queryKey:["extraction-runs"], queryFn:({signal})=>apiGet<Run[]>("/api/v1/extraction/runs", signal) });
  const detail = useQuery({ queryKey:["extraction-run", selected], enabled:Boolean(selected), queryFn:({signal})=>apiGet<Detail>(`/api/v1/extraction/runs/${selected}`, signal) });

  const openRuns = useMemo(() => (runs.data ?? []).filter(row => !CLOSED.has(row.status)), [runs.data]);
  const attentionRuns = useMemo(() => openRuns.filter(row => ["hold", "qa"].includes(row.status)), [openRuns]);
  const runningRuns = useMemo(() => openRuns.filter(row => row.status === "active"), [openRuns]);
  const nextRuns = useMemo(() => openRuns.filter(row => ["planned", "queued"].includes(row.status)), [openRuns]);
  const filtered = useMemo(() => (runs.data ?? []).filter(row => {
    if (!showClosed && CLOSED.has(row.status)) return false;
    if (!search.trim()) return true;
    return [row.batch_number, row.strain, row.method, row.current_stage_key, row.status].join(" ").toLowerCase().includes(search.trim().toLowerCase());
  }), [runs.data, search, showClosed]);

  useEffect(() => {
    if (selected) return;
    const preferred = attentionRuns[0] ?? runningRuns[0] ?? nextRuns[0] ?? filtered[0];
    if (preferred) setSelected(preferred.id);
  }, [attentionRuns, filtered, nextRuns, runningRuns, selected]);

  const refreshAll = (runId = selected) => {
    void client.invalidateQueries({ queryKey:["extraction-runs"] });
    void client.invalidateQueries({ queryKey:["extraction-parity-overview"] });
    if (runId) void client.invalidateQueries({ queryKey:["extraction-run", runId] });
  };

  return <div className="extraction-operator-workspace">
    <section className="inventory-panel">
      <div className="section-heading">
        <div>
          <div className="eyebrow">Extractor workspace</div>
          <h2>{mode === "today" ? "Today" : "Runs"}</h2>
          <p>{mode === "today" ? "See what needs attention, what is running now and what is next. Select a run to update its current process step inline." : "Search every active or historical extraction run without leaving the operator workspace."}</p>
        </div>
        <div className="heading-actions">
          <button className="primary" type="button" onClick={()=>setCreating(value=>!value)}>{creating ? "Close new run" : "New run"}</button>
          <button className="secondary" type="button" onClick={()=>onOpenAdvanced(selected || undefined)}>Advanced Run 360</button>
        </div>
      </div>

      <div className="metrics extraction-metrics">
        <Metric label="Running now" value={runningRuns.length}/><Metric label="Needs attention" value={attentionRuns.length}/><Metric label="Next / queued" value={nextRuns.length}/>
      </div>

      {creating ? <QuickStartRun onCreated={runId=>{ setSelected(runId); setCreating(false); refreshAll(runId); }} /> : null}
      {runs.isError ? <div className="state error">{runs.error.message}</div> : null}

      {mode === "today" ? <div className="two-column-grid">
        <RunGroup title="Needs attention" empty="No held or QA-gated runs." rows={attentionRuns} selected={selected} onSelect={setSelected}/>
        <RunGroup title="Running now" empty="No runs are currently active." rows={runningRuns} selected={selected} onSelect={setSelected}/>
        <RunGroup title="Next up" empty="No queued runs." rows={nextRuns} selected={selected} onSelect={setSelected}/>
      </div> : <>
        <div className="inventory-toolbar extraction-board-filters">
          <label className="inventory-search"><span>Find run</span><input aria-label="Find extraction run" value={search} placeholder="Batch, strain, method…" onChange={event=>setSearch(event.target.value)}/></label>
          <label className="checkbox-field"><input type="checkbox" checked={showClosed} onChange={event=>setShowClosed(event.target.checked)}/> Closed runs</label>
        </div>
        <div className="table-wrap"><table><thead><tr><th>Run</th><th>Stage</th><th>Method</th><th>Strain</th><th>Latest output</th><th>Status</th></tr></thead><tbody>{filtered.map(row=><tr key={row.id} className={`selectable-row ${selected===row.id?"selected":""}`} onClick={()=>setSelected(row.id)}><td><strong>{row.batch_number}</strong></td><td>{title(row.current_stage_key)}</td><td>{row.method}</td><td>{row.strain||"—"}</td><td>{row.final_output_g?`${formatNumber(row.final_output_g)} g`:"—"}</td><td>{title(row.status)}</td></tr>)}</tbody></table>{!runs.isLoading&&!filtered.length?<div className="empty">No matching extraction runs.</div>:null}</div>
      </>}
    </section>

    {detail.isLoading && selected ? <div className="state">Loading run…</div> : null}
    {detail.isError ? <div className="state error">{detail.error.message}</div> : null}
    {detail.data ? <CurrentRun detail={detail.data} onSaved={()=>refreshAll(detail.data!.run.id)} onOpenAdvanced={()=>onOpenAdvanced(detail.data!.run.id)}/> : null}
  </div>;
}

function QuickStartRun({onCreated}:{onCreated:(runId:string)=>void}) {
  const workflows = useQuery({ queryKey:["extraction-workflows"], queryFn:({signal})=>apiGet<Workflow[]>("/api/v1/extraction/workflows", signal) });
  const lots = useQuery({ queryKey:["extraction-lots"], queryFn:({signal})=>apiGet<Lot[]>("/api/v1/extraction/lots", signal) });
  const [workflowKey,setWorkflowKey]=useState("");
  const [lotId,setLotId]=useState("");
  const [quantity,setQuantity]=useState(0);
  const [batchNumber,setBatchNumber]=useState(()=>suggestBatchNumber());

  useEffect(()=>{ if(!workflowKey&&workflows.data?.[0]) setWorkflowKey(workflows.data[0].key); },[workflowKey,workflows.data]);
  useEffect(()=>{ if(!lotId&&lots.data?.[0]) { setLotId(lots.data[0].lot_id); setQuantity(lots.data[0].available); } },[lotId,lots.data]);
  const workflow=workflows.data?.find(row=>row.key===workflowKey);
  const lot=lots.data?.find(row=>row.lot_id===lotId);

  const start=useMutation({
    mutationFn:async()=>{
      if(!workflow||!lot||quantity<=0) throw new Error("Choose a workflow, source lot and positive input amount.");
      const run=await apiPost<Run>("/api/v1/extraction/runs",{
        batch_number:batchNumber.trim()||suggestBatchNumber(), workflow_key:workflow.key, method:workflow.method,
        product_family:workflow.label, strain:"", operator:"", compliance_provider:"metrc", license_number:"", notes:"",
        metrc_input_package_id:lot.compliance_package_id||"",
      });
      const input=await apiPost<RunInput>(`/api/v1/extraction/runs/${run.id}/inputs`,{lot_id:lot.lot_id,quantity,unit:lot.unit,role:"primary_input",source_reference:lot.compliance_package_id||lot.lot_code});
      await apiPost<RunInput>(`/api/v1/extraction/inputs/${input.id}/consume`,{quantity,reason:"Extraction run start"});
      await apiPost<StageEvent>(`/api/v1/extraction/runs/${run.id}/events`,{stage_key:run.current_stage_key,event_type:"started",input_weight_g:quantity,output_weight_g:null,loss_weight_g:null,loss_reason:"",operator:"",notes:"Run started from Extraction Today."});
      return run;
    },
    onSuccess:run=>onCreated(run.id),
  });

  return <section className="inventory-panel">
    <div className="section-heading"><div><div className="eyebrow">New run</div><h3>Start from source material</h3><p>Pick what you are making, choose the inventory lot and enter how much is actually going into the run. DoobieLogic carries the source package, facility context, workflow and inventory movement.</p></div></div>
    <div className="form-grid">
      <label>What are you making?<select value={workflowKey} onChange={event=>setWorkflowKey(event.target.value)}>{workflows.data?.map(row=><option value={row.key} key={row.key}>{row.label}</option>)}</select></label>
      <label>Source material<select value={lotId} onChange={event=>{const next=lots.data?.find(row=>row.lot_id===event.target.value);setLotId(event.target.value);setQuantity(next?.available??0)}}>{lots.data?.map(row=><option value={row.lot_id} key={row.lot_id}>{row.product_name} · {row.lot_code} · {formatNumber(row.available)} {row.unit}</option>)}</select></label>
      <NumberField label="Amount going into run" value={quantity} max={lot?.available} step={0.1} onChange={setQuantity}/>
      <Field label="Run ID" value={batchNumber} onChange={setBatchNumber}/>
    </div>
    {lot?<div className="info-banner">Source package: <strong>{lot.compliance_package_id||"No external package ID"}</strong> · Available: <strong>{formatNumber(lot.available)} {lot.unit}</strong>{lot.location?` · ${lot.location}`:""}. Known source data is carried into the run automatically.</div>:<div className="info-banner">No released extraction inventory is currently available.</div>}
    <button className="primary submit" type="button" disabled={!workflow||!lot||quantity<=0||quantity>Number(lot?.available??0)||start.isPending} onClick={()=>start.mutate()}>{start.isPending?"Starting run…":"Start run"}</button>
    {start.isError?<div className="form-error">{start.error.message}</div>:null}
  </section>;
}

function RunGroup({title:heading,empty,rows,selected,onSelect}:{title:string;empty:string;rows:Run[];selected:string;onSelect:(id:string)=>void}) {
  return <section className="inventory-panel"><h3>{heading}</h3>{rows.length?<div className="table-wrap"><table><thead><tr><th>Run</th><th>Stage</th><th>Status</th></tr></thead><tbody>{rows.map(row=><tr key={row.id} className={`selectable-row ${selected===row.id?"selected":""}`} onClick={()=>onSelect(row.id)}><td><strong>{row.batch_number}</strong><div className="source-caption">{row.method}{row.strain?` · ${row.strain}`:""}</div></td><td>{title(row.current_stage_key)}</td><td>{title(row.status)}</td></tr>)}</tbody></table></div>:<div className="empty">{empty}</div>}</section>;
}

function CurrentRun({detail,onSaved,onOpenAdvanced}:{detail:Detail;onSaved:()=>void;onOpenAdvanced:()=>void}) {
  const currentStage=detail.workflow.stages.find(stage=>stage.key===detail.run.current_stage_key)??detail.workflow.stages[0];
  const stageIndex=Math.max(0,detail.workflow.stages.findIndex(stage=>stage.key===currentStage.key));
  const latestByStage=useMemo(()=>{const rows=new Map<string,StageEvent>();[...detail.events].sort((a,b)=>Date.parse(a.occurred_at)-Date.parse(b.occurred_at)).forEach(event=>{if(["measurement","completed"].includes(event.event_type))rows.set(event.stage_key,event)});return rows},[detail.events]);
  const currentEvent=latestByStage.get(currentStage.key);
  const previousStage=detail.workflow.stages[stageIndex-1];
  const previousEvent=previousStage?latestByStage.get(previousStage.key):undefined;
  const consumed=Number(detail.mass_balance.consumed_input??0);
  const suggestedInput=Number(currentEvent?.input_weight_g??previousEvent?.output_weight_g??consumed??0);
  const [form,setForm]=useState<StageForm>(emptyForm);
  const [advanced,setAdvanced]=useState(false);

  useEffect(()=>{const stageEvent=latestByStage.get(currentStage.key);setForm({
    input_weight_g:Number(stageEvent?.input_weight_g??previousEvent?.output_weight_g??consumed??0), output_weight_g:Number(stageEvent?.output_weight_g??0),
    loss_reason:stageEvent?.loss_reason??"", notes:"", stage_output_field:stageEvent?.stage_output_field??currentStage.output_fields?.[0]??"",
    metrc_stage_input_id:stageEvent?.metrc_stage_input_id??"", metrc_stage_output_id:stageEvent?.metrc_stage_output_id??"",
    intermediate_product_type:detail.run.intermediate_product_type??"", final_product_type:detail.run.final_product_type??"",
    formulation_base_g:Number(detail.run.formulation_base_g??previousEvent?.output_weight_g??consumed??0), terpene_handling_mode:detail.run.terpene_handling_mode??"Native / No Add-Back",
    terpene_type:detail.run.terpene_type??"", terpene_source:detail.run.terpene_source??"", terpene_percentage:Number(detail.run.terpene_percentage??0), terpene_weight_g:Number(detail.run.terpene_weight_g??0),
  });setAdvanced(false)},[consumed,currentStage.key,currentStage.output_fields,detail.run,latestByStage,previousEvent]);

  const hasOutput=form.output_weight_g>0;
  const stageLoss=hasOutput?Math.max(0,form.input_weight_g-form.output_weight_g):0;
  const stageGain=hasOutput?Math.max(0,form.output_weight_g-form.input_weight_g):0;
  const stageYield=form.input_weight_g>0&&hasOutput?form.output_weight_g/form.input_weight_g*100:0;
  const lossPct=form.input_weight_g>0&&hasOutput?stageLoss/form.input_weight_g*100:0;
  const calculatedTerpene=form.terpene_handling_mode==="Native / No Add-Back"?0:(form.terpene_weight_g>0?form.terpene_weight_g:form.formulation_base_g*form.terpene_percentage/100);
  const expectedFormulatedMass=Math.max(0,form.formulation_base_g)+Math.max(0,calculatedTerpene);
  const latestMeasuredOutput=[...detail.events].sort((a,b)=>Date.parse(b.occurred_at)-Date.parse(a.occurred_at)).find(event=>Number(event.output_weight_g??0)>0)?.output_weight_g??detail.run.final_output_g??detail.mass_balance.recorded_output??0;
  const recordedStageLoss=Array.from(latestByStage.values()).reduce((sum,event)=>sum+Number(event.loss_weight_g??0),0);
  const massReduction=Math.max(0,consumed-Number(latestMeasuredOutput||0));
  const unexplainedVariance=Math.max(0,massReduction-recordedStageLoss);
  const overallYield=consumed>0&&Number(latestMeasuredOutput||0)>0?Number(latestMeasuredOutput)/consumed*100:Number(detail.mass_balance.yield_pct??0);
  const isQaGate=Boolean(currentStage.qa_gate);const isReleaseGate=Boolean(currentStage.release_gate);const isFormulation=currentStage.key==="formulation";const outputFields=currentStage.output_fields??[];const requiresOutput=outputFields.length>0||currentStage.key==="final_output";

  const mutation=useMutation({mutationFn:(eventType:StageAction)=>apiPost(`/api/v1/extraction/runs/${detail.run.id}/events`,{
    stage_key:currentStage.key,event_type:eventType,input_weight_g:form.input_weight_g>0?form.input_weight_g:null,output_weight_g:form.output_weight_g>0?form.output_weight_g:null,
    loss_weight_g:null,loss_reason:form.loss_reason,notes:form.notes,operator:"",stage_output_field:form.stage_output_field,metrc_stage_input_id:form.metrc_stage_input_id,metrc_stage_output_id:form.metrc_stage_output_id,
    intermediate_product_type:form.intermediate_product_type,final_product_type:form.final_product_type,formulation_used:isFormulation?true:undefined,formulation_base_g:isFormulation?form.formulation_base_g:undefined,
    terpene_handling_mode:isFormulation?form.terpene_handling_mode:undefined,terpene_type:isFormulation?form.terpene_type:undefined,terpene_source:isFormulation?form.terpene_source:undefined,
    terpene_percentage:isFormulation?form.terpene_percentage:undefined,terpene_weight_g:isFormulation?calculatedTerpene:undefined,
  }),onSuccess:onSaved});
  const canComplete=!requiresOutput||hasOutput;const recentEvents=[...detail.events].sort((a,b)=>Date.parse(b.occurred_at)-Date.parse(a.occurred_at)).slice(0,8);

  return <section className="inventory-panel">
    <div className="section-heading"><div><div className="eyebrow">{detail.run.method} · {detail.workflow.label}</div><h2>{detail.run.batch_number}</h2><p>{detail.run.strain||"Source-linked run"} · {title(detail.run.status)} · current stage: <strong>{currentStage.label}</strong></p></div><button className="secondary" type="button" onClick={onOpenAdvanced}>Open Run 360</button></div>
    <div className="metrics"><Metric label="Consumed input" value={`${formatNumber(consumed)} g`}/><Metric label="Latest measured output" value={`${formatNumber(Number(latestMeasuredOutput||0))} g`}/><Metric label="Overall yield" value={`${formatNumber(overallYield,1)}%`}/><Metric label="Recorded process loss" value={`${formatNumber(recordedStageLoss)} g`}/><Metric label="Unexplained variance" value={`${formatNumber(unexplainedVariance)} g`}/></div>
    <div className="detail-facts"><p><strong>Progress:</strong> Step {stageIndex+1} of {detail.workflow.stages.length}</p><p><strong>Operator:</strong> {detail.run.operator||"Authenticated operator"}</p><p><strong>Release:</strong> {title(detail.run.release_status)}</p><p><strong>Input carried forward:</strong> {formatNumber(suggestedInput)} g</p></div>
    <progress max={Math.max(detail.workflow.stages.length,1)} value={stageIndex+1}/><div className="view-tabs parity-tabs">{detail.workflow.stages.map((stage,index)=><button key={stage.key} type="button" disabled className={stage.key===currentStage.key?"active":""}>{index<stageIndex?"✓ ":""}{stage.label}{stage.optional?" · optional":""}</button>)}</div>
    {isQaGate||isReleaseGate?<div className="info-banner">{isQaGate?"This run is at the QA / COA gate.":"This run is at the release gate."} Complete the controlled action in Run 360 without leaving this Extraction workspace.</div>:<>
      <div className="section-heading"><div><div className="eyebrow">Current step</div><h3>{currentStage.label}</h3><p>Enter the real measurement. DoobieLogic carries the previous weight forward and calculates everything deterministic.</p></div></div>
      <div className="form-grid"><NumberField label="Stage input (g)" value={form.input_weight_g} onChange={value=>setForm({...form,input_weight_g:value})}/><NumberField label="Scale output (g)" value={form.output_weight_g} onChange={value=>setForm({...form,output_weight_g:value})}/>{outputFields.length>1?<label>What was measured?<select value={form.stage_output_field} onChange={event=>setForm({...form,stage_output_field:event.target.value})}>{outputFields.map(field=><option value={field} key={field}>{title(field)}</option>)}</select></label>:null}<label className="span-2">Quick note<textarea value={form.notes} placeholder="Optional operator note…" onChange={event=>setForm({...form,notes:event.target.value})}/></label></div>
      {hasOutput?<div className="metrics"><Metric label="Calculated stage loss" value={`${formatNumber(stageLoss)} g`}/><Metric label="Loss %" value={`${formatNumber(lossPct,1)}%`}/><Metric label="Stage yield" value={`${formatNumber(stageYield,1)}%`}/>{stageGain>0?<Metric label="Net addition / gain" value={`${formatNumber(stageGain)} g`}/>:null}</div>:<div className="info-banner">Enter the scale output and DoobieLogic calculates loss and yield automatically. Manual loss entry is not part of the normal workflow.</div>}
      {isFormulation?<section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Formulation</div><h3>Blend calculation</h3></div></div><div className="form-grid"><NumberField label="Base material (g)" value={form.formulation_base_g} onChange={value=>setForm({...form,formulation_base_g:value})}/><label>Terpene handling<select value={form.terpene_handling_mode} onChange={event=>setForm({...form,terpene_handling_mode:event.target.value,terpene_weight_g:event.target.value==="Native / No Add-Back"?0:form.terpene_weight_g})}>{TERPENE_MODES.map(mode=><option key={mode}>{mode}</option>)}</select></label>{form.terpene_handling_mode!=="Native / No Add-Back"?<><Field label="Terpene type" value={form.terpene_type} onChange={value=>setForm({...form,terpene_type:value})}/><Field label="Terpene source" value={form.terpene_source} onChange={value=>setForm({...form,terpene_source:value})}/><NumberField label="Terpene %" value={form.terpene_percentage} max={20} step={.1} onChange={value=>setForm({...form,terpene_percentage:value,terpene_weight_g:0})}/><NumberField label="Weight override (g)" value={form.terpene_weight_g} step={.1} onChange={value=>setForm({...form,terpene_weight_g:value})}/></>:null}</div><div className="info-banner">Calculated terpene addition: <strong>{formatNumber(calculatedTerpene,3)} g</strong> · Expected formulated mass: <strong>{formatNumber(expectedFormulatedMass,3)} g</strong>. Confirm actual scale output after blending.</div></section>:null}
      <details open={advanced} onToggle={event=>setAdvanced((event.currentTarget as HTMLDetailsElement).open)}><summary>More details / traceability</summary><div className="form-grid"><Field label="Loss / variance reason" value={form.loss_reason} onChange={value=>setForm({...form,loss_reason:value})}/><Field label="METRC stage input ID" value={form.metrc_stage_input_id} onChange={value=>setForm({...form,metrc_stage_input_id:value})}/><Field label="METRC stage output ID" value={form.metrc_stage_output_id} onChange={value=>setForm({...form,metrc_stage_output_id:value})}/><Field label="Intermediate product type" value={form.intermediate_product_type} onChange={value=>setForm({...form,intermediate_product_type:value})}/><Field label="Final product type" value={form.final_product_type} onChange={value=>setForm({...form,final_product_type:value})}/></div></details>
      <div className="heading-actions">{detail.run.status==="hold"?<button className="secondary" type="button" disabled={mutation.isPending} onClick={()=>mutation.mutate("released")}>Resume run</button>:<button className="secondary" type="button" disabled={mutation.isPending} onClick={()=>mutation.mutate("hold")}>Put on hold</button>}<button className="secondary" type="button" disabled={mutation.isPending} onClick={()=>mutation.mutate("started")}>Start / mark active</button><button className="secondary" type="button" disabled={mutation.isPending||(requiresOutput&&!hasOutput)} onClick={()=>mutation.mutate("measurement")}>Save update</button><button className="primary" type="button" disabled={mutation.isPending||!canComplete} onClick={()=>mutation.mutate("completed")}>{mutation.isPending?"Saving…":"Complete & move to next"}</button></div>
      {mutation.isError?<div className="form-error">{mutation.error.message}</div>:null}{mutation.isSuccess?<div className="success-banner">Run updated. Calculations and stage status refreshed.</div>:null}
    </>}
    <details><summary>Recent process history</summary><div className="table-wrap"><table><thead><tr><th>Time</th><th>Stage</th><th>Update</th><th>Input</th><th>Output</th><th>Loss</th><th>Operator</th></tr></thead><tbody>{recentEvents.map(event=><tr key={event.id}><td>{dateTime(event.occurred_at)}</td><td>{detail.workflow.stages.find(stage=>stage.key===event.stage_key)?.label??title(event.stage_key)}</td><td>{title(event.event_type)}</td><td>{event.input_weight_g==null?"—":`${formatNumber(event.input_weight_g)} g`}</td><td>{event.output_weight_g==null?"—":`${formatNumber(event.output_weight_g)} g`}</td><td>{event.loss_weight_g==null?"—":`${formatNumber(event.loss_weight_g)} g`}</td><td>{event.operator||"—"}</td></tr>)}</tbody></table>{!recentEvents.length?<div className="empty">No process updates recorded yet.</div>:null}</div></details>
  </section>;
}

function Metric({label,value}:{label:string;value:string|number}){return <div className="metric"><span>{label}</span><strong>{value}</strong></div>}
function Field({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}){return <label>{label}<input value={value} onChange={event=>onChange(event.target.value)}/></label>}
function NumberField({label,value,onChange,max,step=.1}:{label:string;value:number;onChange:(value:number)=>void;max?:number;step?:number}){return <label>{label}<input type="number" min="0" max={max} step={step} value={Number.isFinite(value)?value:0} onChange={event=>onChange(Number(event.target.value||0))}/></label>}
function title(value:string|undefined){return String(value||"").replace(/_/g," ").replace(/\b\w/g,char=>char.toUpperCase())}
function formatNumber(value:number,digits=2){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:digits})}
function dateTime(value:string){const parsed=new Date(value);return Number.isNaN(parsed.getTime())?value:parsed.toLocaleString()}
function suggestBatchNumber(){const now=new Date();const date=now.toISOString().slice(2,10).replace(/-/g,"");const time=now.toTimeString().slice(0,5).replace(":","");return `EX-${date}-${time}`}
