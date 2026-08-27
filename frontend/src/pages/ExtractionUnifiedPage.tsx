import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { WorkspaceWindow } from "../components/WorkspaceWindow";
import { apiGet } from "../lib/api";
import type { InventoryResponse } from "../types/inventory";
import { ExtractionAnalyticsWorkspace } from "./ExtractionAnalyticsWorkspace";
import { ExtractionCommandCenterPage } from "./ExtractionCommandCenterPage";
import { ExtractionOperatorWorkspace } from "./ExtractionOperatorWorkspace";
import { ExtractionPage } from "./ExtractionPage";

type View = "today" | "runs" | "inventory" | "analytics";
type AdvancedView = "run" | "management";
type Lot = { lot_id:string; product_name:string; lot_code:string; compliance_package_id:string; available:number; unit:string; location?:string; status?:string };

export function ExtractionUnifiedPage({onNavigate}:{onNavigate:(page:string)=>void}) {
  const [view,setView]=useState<View>("today");
  const [advancedOpen,setAdvancedOpen]=useState(false);
  const [advancedView,setAdvancedView]=useState<AdvancedView>("run");
  const openAdvanced=()=>{setAdvancedView("run");setAdvancedOpen(true)};
  const lots=useQuery({queryKey:["extraction-unified-lots"],queryFn:({signal})=>apiGet<Lot[]>("/api/v1/extraction/lots",signal),enabled:view==="inventory"});
  const productionInventory=useQuery({queryKey:["extraction-production-inventory-fallback"],queryFn:({signal})=>apiGet<InventoryResponse>("/api/v1/inventory/production/packages?view=all",signal),enabled:view==="inventory"});

  const fallbackLots:Lot[]=(productionInventory.data?.items??[]).filter(row=>Number(row.available||0)>0&&["available","reserved"].includes(String(row.status||"").toLowerCase())).map(row=>({lot_id:row.id,product_name:row.product_name,lot_code:row.lot_code,compliance_package_id:row.package_id,available:Number(row.available||0),unit:row.unit,location:row.location,status:row.status}));
  const inventoryRows=lots.data?.length?lots.data:fallbackLots;
  const inventoryLoading=lots.isLoading&&productionInventory.isLoading;
  const fallbackActive=!lots.isLoading&&(!lots.data?.length||lots.isError)&&fallbackLots.length>0;
  const inventoryFailed=lots.isError&&productionInventory.isError;
  const inventoryError=[lots.error?.message,productionInventory.error?.message].filter(Boolean).join(" · ");

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
      <div className="section-heading"><div><div className="eyebrow">Extraction Inventory</div><h2>Available input lots</h2><p>Reservation-aware facility material ready for extraction. DoobieLogic falls back to Production Inventory if the dedicated extraction feed is unavailable.</p></div></div>
      {inventoryLoading?<div className="state">Loading extraction inventory…</div>:null}
      {fallbackActive?<div className="info-banner">Showing eligible Production Inventory because the extraction reservation feed did not return usable rows. Availability is validated again when a run starts.</div>:null}
      {inventoryFailed?<div className="state error">Extraction inventory could not be loaded. {inventoryError||"No inventory source responded."}</div>:null}
      <div className="metrics"><div className="metric"><span>Available lots</span><strong>{inventoryRows.length}</strong></div><div className="metric"><span>Total available</span><strong>{inventoryRows.reduce((sum,row)=>sum+Number(row.available||0),0).toLocaleString(undefined,{maximumFractionDigits:1})}</strong></div></div>
      <div className="table-wrap"><table><thead><tr><th>Material</th><th>Lot</th><th>METRC / external package</th><th>Location</th><th>Available</th></tr></thead><tbody>{inventoryRows.map(row=><tr key={row.lot_id}><td><strong>{row.product_name}</strong></td><td>{row.lot_code}</td><td>{row.compliance_package_id||"—"}</td><td>{row.location||"—"}</td><td>{Number(row.available||0).toLocaleString(undefined,{maximumFractionDigits:2})} {row.unit}</td></tr>)}</tbody></table>{!inventoryLoading&&!inventoryRows.length?<div className="empty">No available extraction input lots in this facility.</div>:null}</div>
    </section>:null}

    <WorkspaceWindow open={advancedOpen} onClose={()=>setAdvancedOpen(false)} eyebrow="EXTRACTION · CONTEXT" title="Extraction Run 360" subtitle="Deep run controls stay open over the floor instead of replacing it." ariaLabel="Advanced Extraction Run 360" windowKey="extraction-run-360">
      <div className="view-tabs parity-tabs"><button className={advancedView==="run"?"active":""} onClick={()=>setAdvancedView("run")}>Run 360</button><button className={advancedView==="management"?"active":""} onClick={()=>setAdvancedView("management")}>Management & Compliance</button></div>
      {advancedView==="run"?<ExtractionPage onNavigate={onNavigate}/>:<ExtractionCommandCenterPage onNavigate={onNavigate}/>} 
    </WorkspaceWindow>
  </div>;
}
