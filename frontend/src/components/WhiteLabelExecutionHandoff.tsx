import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import { Link } from "react-router-dom";
import type { DurablePlan } from "../pages/WhiteLabelRepackPage";

export function WhiteLabelExecutionHandoff({plan}:{plan:DurablePlan}) {
  return <section className="inventory-panel"><h3>White Label execution handoff: {plan.name}</h3>
    <p>{plan.source.lot_code}: {plan.source.quantity} {plan.source.unit}. Status: {plan.status}.</p>
    <p>Review the planned sizes below and select the actual output products, quantities and package identifiers. Inventory moves only through the existing execution confirmation. Label Studio uses the resulting package and verified COA evidence.</p>
    <div className="table-wrap"><table><thead><tr><th>Package size (g)</th><th>Expected units</th><th>Expected packaged grams</th></tr></thead><tbody>{plan.economics.outputs.map((row,index)=><tr key={index}><td>{row.package_size_g}</td><td>{row.units}</td><td>{row.packaged_g}</td></tr>)}</tbody></table></div>
    <p><Link to={`/production/repack?plan=${plan.id}`}>Open saved plan and economics</Link>{plan.production_order_id?<> · <Link to={`/production/runs/${plan.production_order_id}`}>Production Run 360</Link></>:null} · <Link to="/compliance/labels">Label Studio</Link></p>
  </section>;
}

export function WhiteLabelRunHandoff({notes}:{notes:string}) {
  let planId="";
  try { const parsed=JSON.parse(notes); if(typeof parsed.white_label_plan_id==="string")planId=parsed.white_label_plan_id; } catch { /* Ordinary production notes are plain text. */ }
  const plan=useQuery({queryKey:["white-label-handoff",planId],enabled:!!planId,retry:false,queryFn:({signal})=>apiGet<DurablePlan>(`/api/v1/white-label/plans/${encodeURIComponent(planId)}`,signal)});
  if(!planId)return null;
  if(!plan.data)return <div className="info-banner">{plan.error?.message||"Loading saved White Label handoff..."}</div>;
  return <><WhiteLabelExecutionHandoff plan={plan.data}/><p><Link to={`/production/package-studio?white_label_plan=${planId}`}>Open Package Studio with this source and production link</Link></p></>;
}
