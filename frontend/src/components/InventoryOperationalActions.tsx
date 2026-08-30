import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { InventoryPackage } from "../types/inventory";
import { apiPost } from "../lib/api";
import { StreamlitDialog } from "./StreamlitDialog";

export type InventoryOperationalAction = "move" | "hold" | "release";

type ActionResult = { lot_id:string; status?:string; location?:string; changed:boolean; metrc_status?:string };

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

  if(!action)return null;
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
