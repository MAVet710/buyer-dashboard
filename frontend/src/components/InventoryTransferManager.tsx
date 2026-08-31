import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import type { InventoryPackage } from "../types/inventory";
import { StreamlitDialog } from "./StreamlitDialog";

type Operation = "retail" | "production";
type Facility = { id:string;name:string;code:string;license_type?:string;capabilities?:Record<string,boolean> };
type AccessOrganization = { id:string;name:string;slug:string;facilities:Facility[] };
type AccessOptions = { organizations:AccessOrganization[];organization_id:string;facility_id:string };
type AccountContext = { organization:{id:string;name:string}|null;facility_id:string;user:{role:string} };
type TransferLine = { id:string;source_lot_id:string;destination_lot_id:string|null;product_name:string;quantity:number;received_quantity:number;unit:string;source_lot_code:string;source_package_id:string;destination_lot_code:string;destination_package_id:string;status:"shipped"|"received"|"cancelled" };
type Transfer = { id:string;source_facility_id:string;destination_facility_id:string;source_facility_name:string;destination_facility_name:string;source_license_number:string;destination_license_number:string;manifest_reference:string;external_transfer_id:string;status:"shipped"|"partially_received"|"received"|"cancelled";direction:string;shipped_at:string;received_at:string|null;lines:TransferLine[] };

type ReceiveDraft = { transferId:string;lineId:string;lot_code:string;package_id:string;location:string;confirmed:boolean };

export function InventoryTransferManager({operation,packages,onClose,onSaved}:{operation:Operation;packages:InventoryPackage[];onClose:()=>void;onSaved:(message:string)=>void}) {
  const client=useQueryClient();
  const context=useQuery({queryKey:["account-context"],queryFn:({signal})=>apiGet<AccountContext>("/api/v1/account/context",signal)});
  const access=useQuery({queryKey:["access-options"],queryFn:({signal})=>apiGet<AccessOptions>("/api/v1/account/access-options",signal)});
  const transfers=useQuery({queryKey:["inventory-transfers"],queryFn:({signal})=>apiGet<Transfer[]>("/api/v1/inventory/transfers?direction=both",signal)});
  const organization=access.data?.organizations.find(row=>row.id===context.data?.organization?.id);
  const destinations=(organization?.facilities??[]).filter(row=>row.id!==context.data?.facility_id);
  const [destination,setDestination]=useState("");
  const [manifest,setManifest]=useState("");
  const [externalId,setExternalId]=useState("");
  const [confirmed,setConfirmed]=useState(false);
  const [quantities,setQuantities]=useState<Record<string,string>>(()=>Object.fromEntries(packages.map(row=>[row.id,String(Math.max(0,row.available))])));
  const [receiveDraft,setReceiveDraft]=useState<ReceiveDraft|null>(null);
  const [cancelReason,setCancelReason]=useState("");
  const selectedDestination=destinations.find(row=>row.id===destination);
  const inbound=(transfers.data??[]).filter(row=>row.direction==="inbound");
  const outbound=(transfers.data??[]).filter(row=>row.direction==="outbound");
  const dispatchLines=useMemo(()=>packages.map(row=>({source_lot_id:row.id,quantity:Number(quantities[row.id]||0)})),[packages,quantities]);
  const dispatchValid=Boolean(destination&&manifest.trim()&&confirmed&&dispatchLines.length&&dispatchLines.every((row,index)=>row.quantity>0&&row.quantity<=packages[index].available+1e-9));
  const refresh=()=>{void client.invalidateQueries({queryKey:["inventory-transfers"]});void client.invalidateQueries({queryKey:["inventory"]});void transfers.refetch();};

  const dispatch=useMutation({mutationFn:()=>apiPost<Transfer>("/api/v1/inventory/transfers/dispatch",{destination_facility_id:destination,manifest_reference:manifest.trim(),external_transfer_id:externalId.trim(),state_transfer_confirmed:confirmed,lines:dispatchLines,notes:"Posted from DoobieLogic Inventory transfer workspace."}),onSuccess:row=>{refresh();onSaved(`Transfer ${row.manifest_reference} dispatched to ${row.destination_facility_name}.`);onClose();}});
  const receive=useMutation({mutationFn:(draft:ReceiveDraft)=>apiPost<Transfer>(`/api/v1/inventory/transfers/${draft.transferId}/lines/${draft.lineId}/receive`,{operation,lot_code:draft.lot_code,package_id:draft.package_id,location:draft.location||"RECEIVING",state_receipt_confirmed:draft.confirmed,notes:"Received through DoobieLogic transfer workspace."}),onSuccess:row=>{setReceiveDraft(null);refresh();onSaved(`Transfer ${row.manifest_reference} receipt posted to this facility.`);}});
  const cancel=useMutation({mutationFn:(transferId:string)=>apiPost<Transfer>(`/api/v1/inventory/transfers/${transferId}/cancel`,{reason:cancelReason.trim()||"Cancelled before destination receipt"}),onSuccess:row=>{setCancelReason("");refresh();onSaved(`Transfer ${row.manifest_reference} cancelled and source inventory restored.`);}});

  return <StreamlitDialog open onClose={onClose} eyebrow="INVENTORY · LICENSE TRANSFERS" title={packages.length?"Transfer selected inventory":"Cross-license transfers"} subtitle="Physical ledger movements stay separate by license while genealogy follows the material across facilities.">
    <div className="warning-banner"><strong>State-system confirmation required.</strong> DoobieLogic does not create or accept the regulatory Metrc transfer in this workflow. Complete the required state-system step first, then confirm it here before physical ledger posting.</div>
    {packages.length?<section className="inventory-panel">
      <div className="eyebrow">OUTBOUND</div><h3>Dispatch selected packages</h3>
      <div className="form-grid"><label>Destination facility<select value={destination} onChange={event=>setDestination(event.target.value)}><option value="">Select destination…</option>{destinations.map(row=><option key={row.id} value={row.id}>{row.name} · {row.code}{row.license_type?` · ${row.license_type}`:""}</option>)}</select></label><label>Manifest / transfer #<input value={manifest} onChange={event=>setManifest(event.target.value)} /></label><label>External transfer ID<input value={externalId} onChange={event=>setExternalId(event.target.value)} placeholder="Optional Metrc/internal reference" /></label><label>Destination<input value={selectedDestination?`${selectedDestination.name} · ${selectedDestination.code}`:"—"} readOnly /></label></div>
      <div className="table-wrap"><table><thead><tr><th>Package</th><th>Product</th><th>Available</th><th>Transfer quantity</th></tr></thead><tbody>{packages.map(row=><tr key={row.id}><td>{row.package_id||row.lot_code}</td><td>{row.product_name}</td><td>{number(row.available)} {row.unit}</td><td><input type="number" min="0" max={row.available} step="any" value={quantities[row.id]??""} onChange={event=>setQuantities(current=>({...current,[row.id]:event.target.value}))} /></td></tr>)}</tbody></table></div>
      <label className="toggle"><input type="checkbox" checked={confirmed} onChange={event=>setConfirmed(event.target.checked)} />I confirm the required state-system/Metrc transfer and manifest have already been created for this shipment.</label>
      <button className="primary submit" disabled={!dispatchValid||dispatch.isPending} onClick={()=>dispatch.mutate()}>Post transfer out</button>{dispatch.isError?<div className="form-error">{dispatch.error.message}</div>:null}
    </section>:null}

    <section className="inventory-panel"><div className="eyebrow">INBOUND</div><h3>Transfers arriving at this license</h3>{transfers.isLoading?<div className="state">Loading transfers…</div>:null}{transfers.isError?<div className="state error">{transfers.error.message}</div>:null}{inbound.length===0&&!transfers.isLoading?<div className="empty">No inbound DoobieLogic transfers are recorded for this facility.</div>:null}{inbound.map(row=><article className="plant-event" key={row.id}><strong>{row.manifest_reference} · {title(row.status)}</strong><span>{row.source_facility_name} ({row.source_license_number||"license not recorded"}) → {row.destination_facility_name}</span><small>{new Date(row.shipped_at).toLocaleString()} · {row.lines.length} package line(s)</small>{row.lines.map(line=><div key={line.id} className="info-banner"><strong>{line.product_name} · {line.source_package_id||line.source_lot_code}</strong><span>{number(line.quantity)} {line.unit} · {title(line.status)}</span>{line.status==="shipped"?<button className="secondary" onClick={()=>setReceiveDraft({transferId:row.id,lineId:line.id,lot_code:line.source_lot_code,package_id:line.source_package_id,location:"RECEIVING",confirmed:false})}>Receive package</button>:line.destination_package_id?<small>Received as {line.destination_package_id}</small>:null}</div>)}</article>)}</section>

    {receiveDraft?<section className="inventory-panel"><div className="eyebrow">DESTINATION RECEIPT</div><h3>Post received package</h3><div className="form-grid"><label>Destination package ID<input value={receiveDraft.package_id} onChange={event=>setReceiveDraft({...receiveDraft,package_id:event.target.value})} /></label><label>Destination lot / batch<input value={receiveDraft.lot_code} onChange={event=>setReceiveDraft({...receiveDraft,lot_code:event.target.value})} /></label><label>Room / location<input value={receiveDraft.location} onChange={event=>setReceiveDraft({...receiveDraft,location:event.target.value})} /></label></div><label className="toggle"><input type="checkbox" checked={receiveDraft.confirmed} onChange={event=>setReceiveDraft({...receiveDraft,confirmed:event.target.checked})} />I confirm this package was accepted/received in the required state system.</label><div className="audit-actions"><button className="primary" disabled={!receiveDraft.confirmed||receive.isPending} onClick={()=>receive.mutate(receiveDraft)}>Post transfer in</button><button className="secondary" onClick={()=>setReceiveDraft(null)}>Cancel</button></div>{receive.isError?<div className="form-error">{receive.error.message}</div>:null}</section>:null}

    <section className="inventory-panel"><div className="eyebrow">OUTBOUND HISTORY</div><h3>Transfers sent from this license</h3>{outbound.length===0&&!transfers.isLoading?<div className="empty">No outbound DoobieLogic transfers are recorded for this facility.</div>:null}{outbound.map(row=><article className="plant-event" key={row.id}><strong>{row.manifest_reference} · {title(row.status)}</strong><span>{row.source_facility_name} → {row.destination_facility_name} ({row.destination_license_number||"license not recorded"})</span><small>{new Date(row.shipped_at).toLocaleString()} · {row.lines.reduce((sum,line)=>sum+line.quantity,0).toLocaleString(undefined,{maximumFractionDigits:4})} total units across {row.lines.length} line(s)</small>{row.status==="shipped"?<div className="audit-actions"><input placeholder="Cancellation reason" value={cancelReason} onChange={event=>setCancelReason(event.target.value)} /><button className="secondary" disabled={cancel.isPending} onClick={()=>cancel.mutate(row.id)}>Cancel before receipt</button></div>:null}</article>)}</section>
    {cancel.isError?<div className="form-error">{cancel.error.message}</div>:null}
  </StreamlitDialog>;
}

function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function number(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:4})}
