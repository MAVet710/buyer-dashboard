import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { WorkspaceWindow } from "../components/WorkspaceWindow";
import { apiGet } from "../lib/api";
import { ExtractionAnalyticsWorkspace } from "./ExtractionAnalyticsWorkspace";
import { ExtractionCommandCenterPage } from "./ExtractionCommandCenterPage";
import { ExtractionOperatorWorkspace } from "./ExtractionOperatorWorkspace";
import { ExtractionPage } from "./ExtractionPage";

type View = "today" | "runs" | "inventory" | "analytics";
type AdvancedView = "run" | "management";
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
  const [view,setView]=useState<View>("today");
  const [advancedOpen,setAdvancedOpen]=useState(false);
  const [advancedView,setAdvancedView]=useState<AdvancedView>("run");
  const openAdvanced=()=>{setAdvancedView("run");setAdvancedOpen(true)};
  const lots=useQuery({
    queryKey:["extraction-eligible-lots"],
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
      <button className="secondary" type="button" onClick={openAdvanced}>Advanced Run 360</button>
    </div>
    <div className="view-tabs parity-tabs">
      <button className={view==="today"?"active":""} onClick={()=>setView("today")}>Today</button>
      <button className={view==="runs"?"active":""} onClick={()=>setView("runs")}>Runs</button>
      <button className={view==="inventory"?"active":""} onClick={()=>setView("inventory")}>Inventory</button>
      <button className={view==="analytics"?"active":""} onClick={()=>setView("analytics")}>Analytics</button>
    </div>

    {view==="today"?<ExtractionOperatorWorkspace mode="today" onOpenAdvanced={openAdvanced}/>:null}
    {view==="runs"?<ExtractionOperatorWorkspace mode="runs" onOpenAdvanced={openAdvanced}/>:null}
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

    <WorkspaceWindow open={advancedOpen} onClose={()=>setAdvancedOpen(false)} eyebrow="EXTRACTION · CONTEXT" title="Extraction Run 360" subtitle="Deep run controls stay open over the floor instead of replacing it." ariaLabel="Advanced Extraction Run 360" windowKey="extraction-run-360">
      <div className="view-tabs parity-tabs"><button className={advancedView==="run"?"active":""} onClick={()=>setAdvancedView("run")}>Run 360</button><button className={advancedView==="management"?"active":""} onClick={()=>setAdvancedView("management")}>Management & Compliance</button></div>
      {advancedView==="run"?<ExtractionPage onNavigate={onNavigate}/>:<ExtractionCommandCenterPage onNavigate={onNavigate}/>} 
    </WorkspaceWindow>
  </div>;
}

function roleLabel(role?:string){
  if(role==="source_material")return "Source material";
  if(role==="extraction_wip")return "Extraction WIP";
  if(role==="bulk_output")return "Bulk output";
  return "Extraction material";
}
