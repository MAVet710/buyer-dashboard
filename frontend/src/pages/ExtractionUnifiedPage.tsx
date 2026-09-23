import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { WorkspaceWindow } from "../components/WorkspaceWindow";
import { apiGet } from "../lib/api";
import { ExtractionAnalyticsWorkspace } from "./ExtractionAnalyticsWorkspace";
import { ExtractionCommandCenterPage } from "./ExtractionCommandCenterPage";
import { ExtractionOperatorWorkspace } from "./ExtractionOperatorWorkspace";
import { ExtractionPage } from "./ExtractionPage";

type View = "today" | "runs" | "inventory" | "analytics";
type AdvancedView = "run" | "management" | "board";
type AccountContext = { organization?: { id?:string } | null; facility_id?:string; user?: { id?:string } };
type Lot = {
  lot_id:string;
  product_name:string;
  lot_code:string;
  compliance_package_id:string;
  available:number;
  unit:string;
  location?:string;
  status?:string;
  material_type?:string;
  extraction_role?:"source_material"|"extraction_wip"|"bulk_output"|string;
};

// Streamlit parity compatibility: the former "Command Center" and
// "Run 360 / Process Tracker" capabilities remain reachable inside the
// contextual Advanced Extraction window instead of occupying primary navigation.

export function ExtractionUnifiedPage({onNavigate}:{onNavigate:(page:string)=>void}) {
  const context=useQuery({queryKey:["account-context"],queryFn:({signal})=>apiGet<AccountContext>("/api/v1/account/context",signal)});
  if(context.isError)return <div className="state error" role="alert">Facility context is unavailable. Extraction records were not opened.</div>;
  if(!context.data?.organization?.id||!context.data.facility_id)return <div className="state">Loading extraction facility context…</div>;
  const scope=`${context.data.organization.id}:${context.data.facility_id}:${context.data.user?.id??""}`;
  return <ExtractionWorkspace key={scope} scope={scope} onNavigate={onNavigate}/>;
}

function ExtractionWorkspace({scope,onNavigate}:{scope:string;onNavigate:(page:string)=>void}) {
  const [params,setParams]=useSearchParams();
  const requestedView=params.get("extractionView");
  const view:View=requestedView==="runs"||requestedView==="inventory"||requestedView==="analytics"?requestedView:"today";
  const selectedRunId=params.get("extractionRun")??"";
  const requestedPanel=params.get("extractionPanel");
  const advancedOpen=requestedPanel==="run"||requestedPanel==="management"||requestedPanel==="board";
  const advancedView:AdvancedView=requestedPanel==="management"?"management":requestedPanel==="board"?"board":"run";
  const setView=(next:View)=>setParams(previous=>{const updated=new URLSearchParams(previous);updated.set("extractionView",next);return updated;});
  const selectRun=useCallback((id:string,replace=false)=>{
    setParams(previous=>{const updated=new URLSearchParams(previous);if(id)updated.set("extractionRun",id);else updated.delete("extractionRun");return updated;},{replace});
  },[setParams]);
  const setAdvancedView=(next:AdvancedView)=>setParams(previous=>{const updated=new URLSearchParams(previous);updated.set("extractionPanel",next);return updated;});
  const openAdvanced=(runId?:string)=>setParams(previous=>{
    const updated=new URLSearchParams(previous);
    if(runId)updated.set("extractionRun",runId);
    updated.set("extractionPanel",updated.get("extractionRun")?"run":"board");
    return updated;
  });
  const closeAdvanced=()=>setParams(previous=>{const updated=new URLSearchParams(previous);updated.delete("extractionPanel");return updated;});
  const selectAdvancedRun=(id:string)=>setParams(previous=>{const updated=new URLSearchParams(previous);updated.set("extractionRun",id);updated.set("extractionPanel","run");return updated;});
  const lots=useQuery({
    queryKey:["extraction-eligible-lots",scope],
    queryFn:({signal})=>apiGet<Lot[]>("/api/v1/extraction-inventory/lots",signal),
    enabled:view==="inventory",
  });

  const inventoryRows=lots.data??[];
  const sourceCount=inventoryRows.filter(row=>row.extraction_role==="source_material").length;
  const wipCount=inventoryRows.filter(row=>row.extraction_role==="extraction_wip").length;
  const bulkOutputCount=inventoryRows.filter(row=>row.extraction_role==="bulk_output").length;

  return <div className="page extraction-unified">
    <div className="page-heading">
      <div><div className="eyebrow">Production Ops · Extraction</div><h1>Extraction</h1><p>Run today’s work, update the current process inline and let DoobieLogic calculate what it can. Deep QA, COGS, traceability, toll processing and full run history stay available as context instead of crowding the floor.</p></div>
      <button className="secondary" type="button" onClick={()=>openAdvanced()}>Advanced Run 360</button>
    </div>
    <div className="view-tabs parity-tabs">
      <button className={view==="today"?"active":""} onClick={()=>setView("today")}>Today</button>
      <button className={view==="runs"?"active":""} onClick={()=>setView("runs")}>Runs</button>
      <button className={view==="inventory"?"active":""} onClick={()=>setView("inventory")}>Inventory</button>
      <button className={view==="analytics"?"active":""} onClick={()=>setView("analytics")}>Analytics</button>
    </div>

    {view==="today"||view==="runs"?<ExtractionOperatorWorkspace mode={view} scope={scope} selectedRunId={selectedRunId} onSelectRun={selectRun} onOpenAdvanced={openAdvanced}/>:null}
    {view==="analytics"?<ExtractionAnalyticsWorkspace/>:null}
    {view==="inventory"?<section className="inventory-panel">
      <div className="section-heading"><div><div className="eyebrow">Extraction Inventory</div><h2>Extraction-ready material</h2><p>Only cannabis source material, extraction WIP/intermediates and explicit bulk extraction outputs are shown here. Finished packaged products and unrelated production materials stay in Production Inventory.</p></div><button className="secondary" type="button" onClick={()=>onNavigate("Production Inventory")}>View all Production Inventory</button></div>
      {lots.isLoading?<div className="state">Loading extraction inventory…</div>:null}
      {lots.isError?<div className="state error">Extraction inventory could not be loaded. {lots.error.message}</div>:null}
      <div className="metrics extraction-metrics">
        <div className="metric"><span>Eligible lots</span><strong>{inventoryRows.length}</strong></div>
        <div className="metric"><span>Source material</span><strong>{sourceCount}</strong></div>
        <div className="metric"><span>Extraction WIP</span><strong>{wipCount}</strong></div>
        <div className="metric"><span>Bulk outputs</span><strong>{bulkOutputCount}</strong></div>
      </div>
      <div className="table-wrap"><table><thead><tr><th>Material</th><th>Role</th><th>Lot</th><th>METRC / external package</th><th>Location</th><th>Available</th></tr></thead><tbody>{inventoryRows.map(row=><tr key={row.lot_id}><td><strong>{row.product_name}</strong><div className="source-caption">{row.material_type||"Extraction material"}</div></td><td>{roleLabel(row.extraction_role)}</td><td>{row.lot_code}</td><td>{row.compliance_package_id||"—"}</td><td>{row.location||"—"}</td><td>{Number(row.available||0).toLocaleString(undefined,{maximumFractionDigits:2})} {row.unit}</td></tr>)}</tbody></table>{!lots.isLoading&&!inventoryRows.length?<div className="empty">No extraction-eligible material is currently available in this facility. Finished packaged inventory remains available under Production Inventory.</div>:null}</div>
    </section>:null}

    <WorkspaceWindow open={advancedOpen} onClose={closeAdvanced} eyebrow="EXTRACTION · CONTEXT" title="Extraction Run 360" subtitle="Deep run controls stay open over the floor instead of replacing it." ariaLabel="Advanced Extraction Run 360" windowKey="extraction-run-360">
      <div className="view-tabs parity-tabs"><button className={advancedView!=="management"?"active":""} onClick={()=>setAdvancedView("run")}>Run 360</button><button className={advancedView==="management"?"active":""} onClick={()=>setAdvancedView("management")}>Management & Compliance</button></div>
      {advancedView!=="management"?<ExtractionPage scope={scope} selectedRunId={advancedView==="run"?selectedRunId:""} onSelectRun={selectAdvancedRun} onCloseRun={()=>setAdvancedView("board")} onNavigate={onNavigate}/>:<ExtractionCommandCenterPage onNavigate={onNavigate}/>}
    </WorkspaceWindow>
  </div>;
}

function roleLabel(role?:string){
  if(role==="source_material")return "Source material";
  if(role==="extraction_wip")return "Extraction WIP";
  if(role==="bulk_output")return "Bulk output";
  return "Extraction material";
}
