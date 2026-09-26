import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import "./WholesaleLogisticsPanel.css";

type Run = { id:string; service_date:string; driver_name:string|null; driver_license_number?:string|null; vehicle_make?:string|null; vehicle_model?:string|null; vehicle_license_plate_number:string|null; status:string; notes:string; version:number; stop_count:number };
type Stop = { work_item_id?:string|null; id:string; sequence:number; shipment_number:string; order_number:string; partner_name_snapshot:string; manifest_reference:string; status:string; address_snapshot:string; contact_snapshot:string; planned_start:string|null; planned_end:string|null; notes:string; recipient_name:string; delivered_at:string|null; outcome_notes:string; acknowledgment_name:string; allowed_statuses:string[] };
type Detail = Run & {stops:Stop[]};
type Candidate = {id:string; shipment_number:string; order_number:string; partner_name:string; contact_snapshot:string};
const base = "/api/v1/wholesale-logistics";
const label = (value:string) => value.replaceAll("_", " ");
const time = (value:string|null) => value ? new Date(value).toLocaleString() : "Not set";
const formValues = (form:HTMLFormElement) => Object.fromEntries(new FormData(form).entries());
const today = () => { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${String(now.getDate()).padStart(2,"0")}`; };

export function WholesaleLogisticsPanel() {
  const client = useQueryClient();
  const [day, setDay] = useState(today);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(() => new URLSearchParams(window.location.search).get("dispatch") || "");
  const board = useQuery({queryKey:["dispatch", "board", day, offset], queryFn:({signal})=>apiGet<{runs:Run[]; has_more:boolean}>(`${base}/runs?service_date=${day}&offset=${offset}`, signal)});
  const create = useMutation({mutationFn:(body:Record<string,FormDataEntryValue>)=>apiPost<Run>(`${base}/runs`, body), onSuccess:run=>{setSelected(run.id); void client.invalidateQueries({queryKey:["dispatch"]});}});
  function submit(event:FormEvent<HTMLFormElement>) { event.preventDefault(); create.mutate({...formValues(event.currentTarget), service_date:day}); }
  return <section className="dispatch-panel">
    <h2>Dispatch and logistics</h2>
    <p>Track the physical delivery of existing shipments. Delivery outcomes do not post inventory, change fulfilled quantities, or submit provider manifests. Reconcile exceptions through the canonical return workflow.</p>
    <label>Service date<input type="date" required value={day} onChange={e=>{setDay(e.target.value);setOffset(0);setSelected("");}}/></label>
    <details><summary>Create dispatch run</summary><form onSubmit={submit} className="dispatch-form">
      <label>Driver name<input name="driver_name" maxLength={255}/></label>
      <label>Driver license number (optional)<input name="driver_license_number" maxLength={128}/></label>
      <label>Vehicle make (optional)<input name="vehicle_make" maxLength={128}/></label>
      <label>Vehicle model (optional)<input name="vehicle_model" maxLength={128}/></label>
      <label>Vehicle plate<input name="vehicle_license_plate_number" maxLength={64}/></label>
      <label>Run notes<textarea name="notes" maxLength={4000}/></label>
      <button className="primary" disabled={create.isPending || !day}>Create run</button>
    </form></details>
    {create.error?<p role="alert">{create.error.message}</p>:null}
    {board.isLoading?<p>Loading dispatch board...</p>:null}
    {board.error?<p role="alert">{board.error.message}</p>:null}
    <div className="dispatch-board">{board.data?.runs.map(run=><button key={run.id} className={selected===run.id?"primary":"secondary"} onClick={()=>setSelected(run.id)}><strong>{run.driver_name}</strong><span>{run.vehicle_license_plate_number} | {label(run.status)}</span><span>{run.stop_count} stops</span></button>)}</div>
    {board.data?.runs.length===0?<p>No runs for this service date.</p>:null}
    <div className="dispatch-actions"><button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-100))}>Previous runs</button><button disabled={!board.data?.has_more} onClick={()=>setOffset(offset+100)}>More runs</button></div>
    {selected?<RunDetail key={selected} id={selected}/>:null}
  </section>;
}

export function RunDetail({id}:{id:string}) {
  const client=useQueryClient();
  const [message,setMessage]=useState("");
  const detail=useQuery({queryKey:["dispatch","run",id],queryFn:({signal})=>apiGet<Detail>(`${base}/runs/${id}`,signal)});
  const change=useMutation({mutationFn:({path,body}:{path:string;body:Record<string,unknown>})=>apiPost<{message:string}>(`${base}/runs/${id}${path}`,{...body,version:detail.data?.version}),onSuccess:result=>{setMessage(result.message);void client.invalidateQueries({queryKey:["dispatch"]});},onError:()=>{void client.invalidateQueries({queryKey:["dispatch"]});}});
  const focusStop=typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("stop");
  useEffect(()=>{ if(detail.data && focusStop) document.getElementById(`dispatch-stop-${focusStop}`)?.scrollIntoView({block:"center"}); },[detail.data,focusStop]);
  const run=detail.data;
  if (!run) return <p role={detail.error?"alert":undefined}>{detail.error?.message??"Loading stops..."}</p>;
  const mutate=(path:string,body:Record<string,unknown>={})=>change.mutate({path,body});
  const planning=run.stops.every(stop=>stop.status==="planned");
  function move(index:number,delta:number) { if(!run) return; const ids=run.stops.map(s=>s.id); [ids[index],ids[index+delta]]=[ids[index+delta],ids[index]]; mutate("/reorder",{stop_ids:ids}); }
  return <div>
    <h3>{run.driver_name} | {run.vehicle_license_plate_number} | {label(run.status)}</h3>
    <p>Driver license: {run.driver_license_number||"Not recorded"} | Vehicle: {[run.vehicle_make,run.vehicle_model].filter(Boolean).join(" ")||"Not recorded"}</p>
    <p>{run.notes}</p>
    {message?<p role="status">{message}</p>:null}{change.error?<p role="alert">{change.error.message}</p>:null}
    <fieldset disabled={change.isPending}>
      {planning?<><details><summary>Edit run</summary><form className="dispatch-form" onSubmit={event=>{event.preventDefault();mutate("",formValues(event.currentTarget));}}>
        <label>Service date<input name="service_date" type="date" required defaultValue={run.service_date}/></label>
        <label>Driver name<input name="driver_name" maxLength={255} defaultValue={run.driver_name??""}/></label>
        <label>Driver license number (optional)<input name="driver_license_number" maxLength={128} defaultValue={run.driver_license_number??""}/></label>
        <label>Vehicle make (optional)<input name="vehicle_make" maxLength={128} defaultValue={run.vehicle_make??""}/></label>
        <label>Vehicle model (optional)<input name="vehicle_model" maxLength={128} defaultValue={run.vehicle_model??""}/></label>
        <label>Vehicle plate<input name="vehicle_license_plate_number" maxLength={64} defaultValue={run.vehicle_license_plate_number??""}/></label>
        <label>Run notes<textarea name="notes" maxLength={4000} defaultValue={run.notes}/></label><button>Save run</button>
      </form></details><AddStopForm onAdd={body=>mutate("/stops",body)}/>
      <button className="secondary" disabled={run.stops.length<2} onClick={()=>mutate("/plan")}>Plan from first stop</button>
      <p>Uses straight-line nearest neighbors when every stop has coordinates. Keeps the first stop fixed. Does not account for traffic, roads, or service windows.</p></>:null}
      <div className="dispatch-stops">{run.stops.map((stop,index)=><article id={`dispatch-stop-${stop.id}`} aria-label={`Dispatch stop ${stop.sequence}`} className={`dispatch-stop${focusStop===stop.id?" dispatch-stop-focused":""}`} key={stop.id}>
        <h4>{stop.sequence}. {stop.partner_name_snapshot}</h4><strong>{label(stop.status)}</strong>
        <p>Order {stop.order_number} | Shipment {stop.shipment_number}<br/>Manifest: {stop.manifest_reference||"Not recorded"}</p>
        <p className="dispatch-text">{stop.address_snapshot}<br/>{stop.contact_snapshot}</p>
        <p>Window: {time(stop.planned_start)} to {time(stop.planned_end)}</p><p className="dispatch-text">{stop.notes}</p>
        {planning?<div className="dispatch-actions"><button aria-label={`Move stop ${stop.sequence} up`} disabled={index===0} onClick={()=>move(index,-1)}>Move up</button><button aria-label={`Move stop ${stop.sequence} down`} disabled={index===run.stops.length-1} onClick={()=>move(index,1)}>Move down</button><button onClick={()=>mutate(`/stops/${stop.id}/remove`)}>Remove planned stop</button></div>:null}
        {stop.delivered_at?<p>Received by {stop.recipient_name} at {time(stop.delivered_at)}{stop.acknowledgment_name?` | Acknowledged by ${stop.acknowledgment_name}`:""}</p>:null}
        {stop.outcome_notes?<p className="dispatch-text">{stop.outcome_notes}</p>:null}
        {stop.work_item_id?<a href={`/work?item=${encodeURIComponent(stop.work_item_id)}`}>Open Work</a>:["partial","rejected","returned"].includes(stop.status)?<button onClick={()=>mutate(`/stops/${stop.id}/create-reconciliation-work`)}>Create reconciliation work</button>:null}
        <StopOutcome key={`${stop.id}:${stop.status}`} stop={stop} onSave={body=>mutate(`/stops/${stop.id}/status`,body)}/>
      </article>)}</div>
    </fieldset>
  </div>;
}

function AddStopForm({onAdd}:{onAdd:(body:Record<string,unknown>)=>void}) {
  const [offset,setOffset]=useState(0);
  const [shipment,setShipment]=useState("");
  const candidates=useQuery({queryKey:["dispatch","candidates",offset],queryFn:({signal})=>apiGet<{shipments:Candidate[];has_more:boolean}>(`${base}/shipments?offset=${offset}`,signal)});
  const selected=candidates.data?.shipments.find(s=>s.id===shipment);
  function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); const raw=formValues(event.currentTarget);
    onAdd({...raw,latitude:raw.latitude?Number(raw.latitude):null,longitude:raw.longitude?Number(raw.longitude):null,planned_start:raw.planned_start?new Date(String(raw.planned_start)).toISOString():null,planned_end:raw.planned_end?new Date(String(raw.planned_end)).toISOString():null});
  }
  return <details><summary>Add shipment stop</summary>
    {candidates.error?<p role="alert">{candidates.error.message}</p>:null}
    <form className="dispatch-form" onSubmit={submit}>
      <label>Shipment<select name="shipment_id" value={selected?.id??""} required onChange={e=>setShipment(e.target.value)}><option value="">Select shipment</option>{candidates.data?.shipments.map(s=><option value={s.id} key={s.id}>{s.shipment_number} | {s.order_number} | {s.partner_name}</option>)}</select></label>
      <label>Delivery address snapshot<textarea name="address_snapshot" required maxLength={2000}/></label>
      <label>Contact snapshot<textarea key={selected?.id??"none"} name="contact_snapshot" defaultValue={selected?.contact_snapshot??""} maxLength={2000}/></label>
      <label>Window start (local time)<input name="planned_start" type="datetime-local"/></label>
      <label>Window end (local time)<input name="planned_end" type="datetime-local"/></label>
      <label>Latitude (optional)<input name="latitude" type="number" min={-90} max={90} step="any"/></label>
      <label>Longitude (optional)<input name="longitude" type="number" min={-180} max={180} step="any"/></label>
      <label>Stop notes<textarea name="notes" maxLength={4000}/></label><button disabled={!selected}>Add stop</button>
    </form><div className="dispatch-actions"><button disabled={offset===0} onClick={()=>{setOffset(Math.max(0,offset-200));setShipment("");}}>Previous shipments</button><button disabled={!candidates.data?.has_more} onClick={()=>{setOffset(offset+200);setShipment("");}}>More shipments</button></div>
  </details>;
}

export function StopOutcome({stop,onSave}:{stop:Stop;onSave:(body:Record<string,unknown>)=>void}) {
  const [status,setStatus]=useState(stop.allowed_statuses[0]??"");
  if (!stop.allowed_statuses.length) return null;
  const pod=status==="delivered"||status==="partial";
  const exception=["partial","rejected","returned"].includes(status);
  return <form className="dispatch-form" onSubmit={event=>{event.preventDefault();const raw=formValues(event.currentTarget);onSave({...raw,delivered_at:raw.delivered_at?new Date(String(raw.delivered_at)).toISOString():null});}}>
    <label>Next status<select name="status" value={status} onChange={event=>setStatus(event.target.value)}>{stop.allowed_statuses.map(s=><option key={s} value={s}>{label(s)}</option>)}</select></label>
    {pod?<><label>Recipient name<input name="recipient_name" required maxLength={255}/></label><label>Delivered at (local time, defaults to now)<input name="delivered_at" type="datetime-local"/></label><label>Optional typed name acknowledgment<input name="acknowledgment_name" maxLength={255}/></label></>:null}
    <label>{exception?"Exception notes (required)":"Delivery notes"}<textarea name="outcome_notes" required={exception} maxLength={4000}/></label>
    <button className="primary">Record {label(status)}</button>
  </form>;
}
