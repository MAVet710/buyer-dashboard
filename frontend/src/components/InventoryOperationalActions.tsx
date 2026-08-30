import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { InventoryPackage } from "../types/inventory";
import { apiPost } from "../lib/api";
import { StreamlitDialog } from "./StreamlitDialog";

export type InventoryOperationalAction = "move" | "hold" | "release";

type ActionResult = { lot_id:string; status?:string; location?:string; changed:boolean; metrc_status?:string };
type TraceabilityPrefill = { operation_type:string; entity_id:string; reason?:string; fields?:Record<string,string> };

const TRACEABILITY_PREFILL_KEY = "buyer-dash-traceability-prefill";
const PACKAGE_STUDIO_PREFILL_KEY = "buyer-dash-package-studio-prefill";
const PRODUCTION_ALLOCATION_KEY = "buyer-dash-production-inventory-selection";

export function InventoryOperationalActions({
  action,
  packages,
  locations,
  onClose,
  onSaved,
}:{
  action:InventoryOperationalAction|null;
  packages:InventoryPackage[];
  locations:string[];
  onClose:()=>void;
  onSaved:(message:string)=>void;
}){
  const [destination,setDestination]=useState("");
  const [reason,setReason]=useState("");
  useEffect(()=>{
    if(!action)return;
    setDestination("");
    setReason(action==="move"?"Operational inventory move":action==="hold"?"Operational hold":"Operational hold released");
  },[action]);

  const mutation=useMutation({
    mutationFn:async()=>{
      if(!action||!packages.length)throw new Error("Select at least one package.");
      if(action==="move"&&!destination.trim())throw new Error("Choose or enter a destination room / location.");
      const results:ActionResult[]=[];
      for(const pkg of packages){
        if(action==="move"){
          results.push(await apiPost<ActionResult>("/api/v1/traceability-actions/inventory/move",{
            lot_id:pkg.id,destination_location:destination.trim(),reason:reason.trim()||"Operational inventory move",sync_to_metrc:false,
          }));
        }else if(action==="hold"){
          results.push(await apiPost<ActionResult>("/api/v1/traceability-actions/inventory/hold",{
            lot_id:pkg.id,reason:reason.trim()||"Operational hold",
          }));
        }else{
          results.push(await apiPost<ActionResult>("/api/v1/traceability-actions/inventory/release-hold",{
            lot_id:pkg.id,reason:reason.trim()||"Operational hold released",
          }));
        }
      }
      return results;
    },
    onSuccess:results=>{
      const changed=results.filter(row=>row.changed).length;
      const label=action==="move"?`Moved ${changed} package(s) to ${destination.trim()}.`:action==="hold"?`Placed ${changed} package(s) on operational hold.`:`Released ${changed} package(s) from operational hold.`;
      onSaved(label);
      onClose();
    },
  });

  if(!action){
    if(!packages.length)return null;
    const single=packages.length===1?packages[0]:null;
    const packageIds=packages.map(row=>row.package_id||row.id).filter(Boolean);
    return <section className="inventory-panel audit-actions" aria-label="More inventory actions">
      <strong>More inventory actions</strong>
      <button className="secondary" type="button" disabled={!single} title={single?"Open Package Studio with this source package":"Split requires one source package"} onClick={()=>{
        if(!single)return;
        sessionStorage.setItem(PACKAGE_STUDIO_PREFILL_KEY,JSON.stringify({lot_id:single.id,action_type:"breakdown"}));
        window.location.assign("/production/package-studio");
      }}>Split / Package Studio</button>
      <button className="secondary" type="button" disabled={!single} title={single?"Prepare a controlled package finish action":"Finish requires one package"} onClick={()=>single&&openTraceability({operation_type:"package_finish",entity_id:single.package_id||single.id,reason:"Finish selected inventory package"})}>Finish</button>
      <button className="secondary" type="button" disabled={!single} title={single?"Prepare a controlled package unfinish action":"Unfinish requires one package"} onClick={()=>single&&openTraceability({operation_type:"package_unfinish",entity_id:single.package_id||single.id,reason:"Unfinish selected inventory package"})}>Unfinish</button>
      <button className="secondary" type="button" disabled={!single} title={single?"Prepare a controlled package item change":"Change Item requires one package"} onClick={()=>single&&openTraceability({operation_type:"package_item_update",entity_id:single.package_id||single.id,reason:"Change item assigned to selected package"})}>Change Item</button>
      <button className="secondary" type="button" disabled={!single} title={single?"Prepare a controlled package note change":"Change Note requires one package"} onClick={()=>single&&openTraceability({operation_type:"package_note_update",entity_id:single.package_id||single.id,reason:"Update note on selected package"})}>Change Note</button>
      <button className="secondary" type="button" onClick={()=>{
        sessionStorage.setItem(PRODUCTION_ALLOCATION_KEY,JSON.stringify(packages.map(row=>({lot_id:row.id,package_id:row.package_id,product_id:row.product_id,product_name:row.product_name,available:row.available,unit:row.unit,location:row.location}))));
        window.location.assign("/production");
      }}>Allocate to Production</button>
      <button className="secondary" type="button" title="Start an inter-facility transfer/manifest workflow. This is not a Move." onClick={()=>openTraceability({operation_type:"transfer_create",entity_id:single?.package_id||`inventory-selection:${packages.length}`,reason:"Start transfer / manifest for selected inventory",fields:{package_ids:packageIds.join(",")}})}>Transfer / Manifest</button>
      <button className="secondary" type="button" disabled={!single} title={single?"Open the controlled waste/destruction workflow":"Waste/Destroy is handled one package at a time until provider semantics are verified"} onClick={()=>single&&openTraceability({operation_type:"waste_record",entity_id:single.package_id||single.id,reason:"Record controlled waste / destruction for selected package",fields:{quantity:String(single.available||single.on_hand||0),unit:single.unit||"g"}})}>Waste / Destroy</button>
      <span className="source-caption">Compliance-changing actions open the typed traceability workflow for preflight and confirmation. They are not treated as completed Metrc writes until provider verification succeeds.</span>
    </section>;
  }

  const title=action==="move"?"Move inventory":action==="hold"?"Place inventory on hold":"Release inventory hold";
  const subtitle=action==="move"
    ?"Move packages to another room or operational location inside this licensed facility. This is not an inter-facility transfer."
    :action==="hold"
      ?"Operational holds immediately remove the selected packages from normal available workflows while preserving physical quantity."
      :"Release only DoobieLogic operational holds. Regulatory/QA quarantine states keep their controlled release workflow.";
  const existingLocations=[...new Set(locations.filter(Boolean))].sort();
  return <StreamlitDialog open onClose={onClose} eyebrow="Inventory action" title={title} subtitle={subtitle} footer={<div className="heading-actions"><button className="secondary" type="button" disabled={mutation.isPending} onClick={onClose}>Cancel</button><button className="primary" type="button" disabled={mutation.isPending||(action==="move"&&!destination.trim())} onClick={()=>mutation.mutate()}>{mutation.isPending?"Applying…":action==="move"?"Confirm move":action==="hold"?"Place on hold":"Release hold"}</button></div>}>
    <div className="detail-facts"><p><strong>Selected packages:</strong> {packages.length}</p><p><strong>Current locations:</strong> {[...new Set(packages.map(row=>row.location||"UNASSIGNED"))].join(" · ")}</p></div>
    {action==="move"?<div className="form-grid"><label>Destination room / location<input list="inventory-location-options" value={destination} onChange={event=>setDestination(event.target.value)} placeholder="Vault A, Extraction Room, Rack 3…"/><datalist id="inventory-location-options">{existingLocations.map(value=><option value={value} key={value}/>)}</datalist></label></div>:null}
    <label>Reason / note<textarea value={reason} onChange={event=>setReason(event.target.value)} placeholder="Why is this action being performed?"/></label>
    {action==="move"?<div className="info-banner"><strong>Move ≠ Transfer.</strong> This changes the operational room/location inside the same facility. Metrc package-location writes remain fail-closed until the verified provider write/readback contract is promoted.</div>:null}
    <div className="table-wrap"><table><thead><tr><th>Package</th><th>Product</th><th>Location</th><th>Status</th></tr></thead><tbody>{packages.map(row=><tr key={row.id}><td>{row.package_id||row.id}</td><td>{row.product_name}</td><td>{row.location||"UNASSIGNED"}</td><td>{row.status}</td></tr>)}</tbody></table></div>
    {mutation.isError?<div className="form-error">{mutation.error.message}</div>:null}
  </StreamlitDialog>;
}

function openTraceability(prefill:TraceabilityPrefill){
  sessionStorage.setItem(TRACEABILITY_PREFILL_KEY,JSON.stringify(prefill));
  window.location.assign("/compliance/actions");
}
