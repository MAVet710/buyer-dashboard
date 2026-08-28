import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDownload, apiGet, apiPost, downloadBlob } from "../lib/api";

type Candidate = {
  order_id:string; order_number:string; status:string; customer:string; customer_license:string;
  package_count:number; package_labels:string[]; ready:boolean;
};
type Proposal = {
  id:string; action_type:string; title:string; rationale:string; status:string; risk_level:string;
  financial_impact_usd:number; preview:Record<string,unknown>; payload:Record<string,unknown>;
  created_by:string; approved_by:string; created_at:string;
};
type Actions = { items:Proposal[] };
type SubmitResult = { status?:string; dispatch?:{status?:string;external_reference?:string}; message?:string; external_reference?:string };
type Lifecycle = {
  state:string; proposal_id:string; proposal_status:string; transaction_id?:string; traceability_status?:string;
  external_reference?:string; template_verified:boolean; template_id?:string; template_name?:string;
  manifest_available:boolean; manifest_download_available:boolean; manifest_transfer_id?:string;
  manifest_number?:string; delivery_id?:string; recipient_license?:string; package_labels?:string[]; message:string;
  manifest_readback_error?:string;
};

export function ManifestDraftControl() {
  const client=useQueryClient();
  const [orderId,setOrderId]=useState("");
  const [departure,setDeparture]=useState("");
  const [arrival,setArrival]=useState("");
  const [route,setRoute]=useState("");
  const [transferType,setTransferType]=useState("Transfer");
  const [transporterLicense,setTransporterLicense]=useState("");
  const [driverName,setDriverName]=useState("");
  const [driverLicense,setDriverLicense]=useState("");
  const [vehiclePlate,setVehiclePlate]=useState("");
  const [vehicleMake,setVehicleMake]=useState("");
  const [vehicleModel,setVehicleModel]=useState("");
  const [phone,setPhone]=useState("");
  const [selectedId,setSelectedId]=useState("");
  const [message,setMessage]=useState("");

  const candidates=useQuery({queryKey:["manifest-candidates"],queryFn:({signal})=>apiGet<{items:Candidate[]}>("/api/v1/doobie/manifest-drafts/candidates",signal)});
  const actions=useQuery({queryKey:["doobie-actions"],queryFn:({signal})=>apiGet<Actions>("/api/v1/doobie/actions",signal)});
  const drafts=useMemo(()=>(actions.data?.items??[]).filter(row=>row.action_type==="prepare_transfer_manifest"),[actions.data]);
  const selected=drafts.find(row=>row.id===selectedId)??drafts[0];
  const candidate=(candidates.data?.items??[]).find(row=>row.order_id===orderId);
  const lifecycle=useQuery({
    queryKey:["manifest-lifecycle",selected?.id??""],
    queryFn:({signal})=>apiGet<Lifecycle>(`/api/v1/doobie/manifest-drafts/${selected!.id}/lifecycle`,signal),
    enabled:false,
    retry:false,
  });

  const refresh=async()=>{await Promise.all([client.invalidateQueries({queryKey:["doobie-actions"]}),client.invalidateQueries({queryKey:["manifest-candidates"]})])};
  const build=useMutation({
    mutationFn:()=>apiPost<Proposal>("/api/v1/doobie/manifest-drafts",{
      order_id:orderId,
      estimated_departure:new Date(departure).toISOString(),
      estimated_arrival:new Date(arrival).toISOString(),
      planned_route:route.trim(),
      transfer_type_name:transferType.trim(),
      transporter_facility_license_number:transporterLicense.trim(),
      driver_name:driverName.trim(),
      driver_license_number:driverLicense.trim(),
      phone_number_for_questions:phone.trim(),
      vehicle_license_plate_number:vehiclePlate.trim(),
      vehicle_make:vehicleMake.trim(),
      vehicle_model:vehicleModel.trim(),
    }),
    onSuccess:async row=>{setSelectedId(row.id);setMessage("Doobie built the manifest-ready draft. Review the preview before approval.");await refresh()},
  });
  const approve=useMutation({
    mutationFn:(id:string)=>apiPost<Proposal>(`/api/v1/doobie/actions/${id}/approve`,{}),
    onSuccess:async row=>{setSelectedId(row.id);setMessage("Draft approved. Nothing has been sent to Metrc yet.");await refresh()},
  });
  const reject=useMutation({
    mutationFn:(id:string)=>apiPost<Proposal>(`/api/v1/doobie/actions/${id}/reject`,{}),
    onSuccess:async()=>{setSelectedId("");setMessage("Draft rejected. No Metrc request was sent.");await refresh()},
  });
  const submit=useMutation({
    mutationFn:(id:string)=>apiPost<SubmitResult>(`/api/v1/doobie/manifest-drafts/${id}/submit`,{}),
    onSuccess:async result=>{setMessage(result.message||`Metrc sandbox submission status: ${result.dispatch?.status||result.status||"submitted"}. Use Check Metrc status to verify provider readback.`);await refresh()},
  });
  const download=useMutation({
    mutationFn:async(id:string)=>({blob:await apiDownload(`/api/v1/doobie/manifest-drafts/${id}/manifest.pdf`),id}),
    onSuccess:({blob})=>downloadBlob(blob,`${lifecycle.data?.manifest_number||"metrc-manifest"}.pdf`),
  });

  const canBuild=Boolean(orderId&&candidate?.ready&&departure&&arrival&&route.trim()&&transferType.trim()&&!build.isPending);
  const error=build.error||approve.error||reject.error||submit.error||lifecycle.error||download.error;

  return <section className="inventory-panel manifest-draft-control">
    <div className="eyebrow">DOOBIE AGENT · MA METRC SANDBOX</div>
    <div className="manifest-draft-heading"><div><h2>Manifest Drafts</h2><p className="section-note">Doobie builds the outgoing transfer-template draft from the sales order, customer license, and allocated Metrc package tags. An authorized employee reviews and approves it, separately submits it to Metrc, then verifies provider readback before treating the manifest as issued.</p></div><span className="read-only-chip">Human controlled</span></div>
    <div className="info-banner"><strong>Pilot guardrail:</strong> provider submission and lifecycle verification are enabled only for the trusted Massachusetts Metrc sandbox. Production manifest writes remain blocked.</div>

    <div className="form-grid two">
      <label>Sales order<select value={orderId} onChange={event=>setOrderId(event.target.value)}><option value="">Choose an allocated sales order</option>{(candidates.data?.items??[]).map(row=><option value={row.order_id} key={row.order_id} disabled={!row.ready}>{row.order_number} · {row.customer||"No customer"} · {row.package_count} package{row.package_count===1?"":"s"}{row.ready?"":" · not ready"}</option>)}</select></label>
      <label>Transfer type<input value={transferType} onChange={event=>setTransferType(event.target.value)} placeholder="Metrc transfer type"/></label>
      <label>Estimated departure<input type="datetime-local" value={departure} onChange={event=>setDeparture(event.target.value)}/></label>
      <label>Estimated arrival<input type="datetime-local" value={arrival} onChange={event=>setArrival(event.target.value)}/></label>
    </div>
    <label>Planned route<textarea rows={3} value={route} onChange={event=>setRoute(event.target.value)} placeholder="Planned route and required travel notes"/></label>
    {candidate?<div className={candidate.ready?"success-banner":"warning-banner"}><strong>{candidate.customer||"Customer"}</strong> · {candidate.customer_license||"Missing customer license"} · {candidate.package_count} allocated Metrc package{candidate.package_count===1?"":"s"}{candidate.package_labels.length?<><br/><small>{candidate.package_labels.join(" · ")}</small></>:null}</div>:null}

    <details className="manifest-transport-details"><summary>Transport details</summary><div className="form-grid two">
      <label>Transporter license<input value={transporterLicense} onChange={event=>setTransporterLicense(event.target.value)}/></label>
      <label>Phone for questions<input value={phone} onChange={event=>setPhone(event.target.value)}/></label>
      <label>Driver name<input value={driverName} onChange={event=>setDriverName(event.target.value)}/></label>
      <label>Driver license<input value={driverLicense} onChange={event=>setDriverLicense(event.target.value)}/></label>
      <label>Vehicle plate<input value={vehiclePlate} onChange={event=>setVehiclePlate(event.target.value)}/></label>
      <label>Vehicle make<input value={vehicleMake} onChange={event=>setVehicleMake(event.target.value)}/></label>
      <label>Vehicle model<input value={vehicleModel} onChange={event=>setVehicleModel(event.target.value)}/></label>
    </div></details>
    <div className="audit-actions"><button className="primary" type="button" disabled={!canBuild} onClick={()=>build.mutate()}>{build.isPending?"Building…":"Build with Doobie Agent"}</button></div>

    {drafts.length?<div className="manifest-drafts-existing"><label>Draft to review<select value={selected?.id??""} onChange={event=>setSelectedId(event.target.value)}>{drafts.map(row=><option value={row.id} key={row.id}>{row.title} · {row.status}</option>)}</select></label></div>:null}
    {selected?<div className="manifest-preview"><div className="manifest-preview-head"><div><div className="eyebrow">EMPLOYEE REVIEW</div><h3>{selected.title}</h3><p>{selected.rationale}</p></div><span className="status-pill">{selected.status}</span></div><pre>{JSON.stringify(selected.preview,null,2)}</pre><div className="audit-actions">{["proposed","failed"].includes(selected.status)?<><button className="secondary" disabled={reject.isPending} onClick={()=>reject.mutate(selected.id)}>Reject</button><button className="primary" disabled={approve.isPending} onClick={()=>approve.mutate(selected.id)}>Approve draft</button></>:null}{selected.status==="approved"?<button className="primary" disabled={submit.isPending} onClick={()=>submit.mutate(selected.id)}>{submit.isPending?"Submitting…":"Submit to Metrc"}</button>:null}{selected.status==="executed"?<button className="secondary" disabled={lifecycle.isFetching} onClick={()=>lifecycle.refetch()}>{lifecycle.isFetching?"Checking…":"Check Metrc status"}</button>:null}{selected.status==="executed"&&lifecycle.data?.manifest_download_available?<button className="primary" disabled={download.isPending} onClick={()=>download.mutate(selected.id)}>{download.isPending?"Downloading…":"Download Metrc manifest"}</button>:null}</div></div>:null}

    {selected?.status==="executed"&&lifecycle.data?<div className="manifest-lifecycle-panel"><div className="eyebrow">PROVIDER READBACK</div><div className="manifest-lifecycle-steps"><span className="done">Draft</span><span className="done">Approved</span><span className="done">Submitted</span><span className={lifecycle.data.template_verified?"done":"current"}>Template verified</span><span className={lifecycle.data.manifest_available?"done":"pending"}>Manifest available</span></div><p><strong>{lifecycle.data.state.replaceAll("_"," ")}</strong> · {lifecycle.data.message}</p>{lifecycle.data.template_id?<small>Metrc template ID: {lifecycle.data.template_id}</small>:null}{lifecycle.data.manifest_number?<small> · Manifest: {lifecycle.data.manifest_number}</small>:null}{lifecycle.data.manifest_readback_error?<div className="warning-banner">{lifecycle.data.manifest_readback_error}</div>:null}</div>:null}
    {message?<div className="success-banner">{message}</div>:null}
    {error?<div className="form-error">{error.message}</div>:null}
  </section>;
}