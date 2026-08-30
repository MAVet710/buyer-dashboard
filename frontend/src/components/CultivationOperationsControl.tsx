import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import type { CultivationPlant } from "../types/inventory";
import { StreamlitDialog } from "./StreamlitDialog";
import { WorkspaceWindow } from "./WorkspaceWindow";

type Room = {
  id:string; room_code:string; display_name:string; phase:string; plant_capacity:number; active_plants:number;
  capacity_remaining:number|null; utilization_pct:number; over_capacity:boolean; phase_mismatch_count:number;
  phase_counts:Record<string,number>; square_feet:number; target_cycle_days:number; next_estimated_harvest:string|null;
  total_cost_usd:number; active:boolean; notes:string;
};
type Harvest = {
  id:string; harvest_code:string; strain_name:string; room_code:string; status:string;
  started_at:string|null; finished_at:string|null; plant_count:number; wet_weight:number; dry_weight:number;
  waste_weight:number; unit:string; dry_yield_pct:number|null; labor_hours?:number; labor_cost_usd:number; material_cost_usd:number;
  overhead_cost_usd:number; total_cogs_usd:number; cost_per_dry_unit:number|null; notes:string; created_by:string;
};
type CostEntry = {
  id:string; entity_type:string; entity_id:string; cost_type:string; description:string; quantity:number; unit:string;
  unit_cost:number; amount:number; occurred_on:string; actor:string; notes:string;
};
type HarvestDetail = Harvest & { plants:CultivationPlant[]; cost_entries:CostEntry[] };

type Props = { plants:CultivationPlant[]; canWrite:boolean; onSelectPlant:(plant:CultivationPlant)=>void };

export function CultivationOperationsControl({plants,canWrite,onSelectPlant}:Props) {
  const client=useQueryClient();
  const [roomEditor,setRoomEditor]=useState<Room|null|"new">(null);
  const [harvestBuilder,setHarvestBuilder]=useState(false);
  const [selectedHarvestId,setSelectedHarvestId]=useState("");
  const rooms=useQuery({queryKey:["cultivation-rooms"],queryFn:({signal})=>apiGet<{items:Room[]}>("/api/v1/inventory/production/plants/rooms",signal)});
  const harvests=useQuery({queryKey:["cultivation-harvests"],queryFn:({signal})=>apiGet<{items:Harvest[]}>("/api/v1/inventory/production/plants/harvests",signal)});
  const refresh=async()=>{await Promise.all([
    client.invalidateQueries({queryKey:["cultivation-rooms"]}),
    client.invalidateQueries({queryKey:["cultivation-harvests"]}),
    client.invalidateQueries({queryKey:["plants"]}),
    client.invalidateQueries({queryKey:["plants-overview"]}),
  ])};
  const activeRooms=(rooms.data?.items??[]).filter(row=>row.active);
  const openHarvests=(harvests.data?.items??[]).filter(row=>!["completed","cancelled"].includes(row.status));
  const overCapacity=activeRooms.filter(row=>row.over_capacity).length;
  const phaseMismatch=activeRooms.reduce((sum,row)=>sum+row.phase_mismatch_count,0);
  const harvestValue=(harvests.data?.items??[]).reduce((sum,row)=>sum+row.total_cogs_usd,0);

  return <section className="cultivation-operations-control">
    <div className="section-heading"><div><div className="eyebrow">CULTIVATION OPERATIONS</div><h3>Rooms, Harvests & Cost</h3><p className="source-caption">Run the physical cultivation operation in DoobieLogic. These are local operational records; they do not issue or imply a Metrc mutation.</p></div><div className="audit-actions">{canWrite?<><button className="secondary" type="button" onClick={()=>setRoomEditor("new")}>Add room</button><button className="primary" type="button" onClick={()=>setHarvestBuilder(true)}>Plan harvest</button></>:null}</div></div>
    <div className="metrics four"><Metric label="Active rooms" value={activeRooms.length}/><Metric label="Open harvests" value={openHarvests.length}/><Metric label="Capacity alerts" value={overCapacity}/><Metric label="Harvest COGS" value={money(harvestValue)}/></div>
    {phaseMismatch?<div className="warning-banner"><strong>{phaseMismatch} plant{phaseMismatch===1?" is":"s are"} in a room configured for another phase.</strong><br/><span>Review room assignment before the next cultivation move.</span></div>:null}

    <div className="two-col">
      <section className="inventory-panel"><div className="section-heading"><div><h4>Room Capacity</h4><p className="source-caption">Plant count, configured capacity, phase fit, and next estimated harvest.</p></div></div>
        {rooms.isLoading?<div className="state">Loading cultivation rooms…</div>:null}{rooms.isError?<div className="state error">{rooms.error.message}</div>:null}
        {rooms.data?.items.length?<div className="table-wrap"><table><thead><tr><th>Room</th><th>Phase</th><th>Plants</th><th>Utilization</th><th>Next harvest</th></tr></thead><tbody>{rooms.data.items.map(room=><tr key={room.id} onClick={()=>canWrite&&setRoomEditor(room)}><td><strong>{room.display_name||room.room_code}</strong><br/><small>{room.room_code}{room.active?"":" · inactive"}</small></td><td>{title(room.phase)||"Any"}{room.phase_mismatch_count?<><br/><small className="warning-text">{room.phase_mismatch_count} phase mismatch</small></>:null}</td><td>{room.active_plants}{room.plant_capacity?` / ${room.plant_capacity}`:" / unbounded"}</td><td><strong className={room.over_capacity?"warning-text":""}>{room.plant_capacity?`${room.utilization_pct.toFixed(1)}%`:"—"}</strong>{room.over_capacity?<><br/><small>Over capacity</small></>:null}</td><td>{room.next_estimated_harvest||"—"}</td></tr>)}</tbody></table></div>:rooms.data?<div className="empty">Configure cultivation rooms to measure capacity and room utilization.</div>:null}
      </section>

      <section className="inventory-panel"><div className="section-heading"><div><h4>Harvest Queue</h4><p className="source-caption">Plan flowering plants into a durable harvest, then track wet weight, dry weight, waste, yield and COGS in Harvest 360.</p></div></div>
        {harvests.isLoading?<div className="state">Loading harvests…</div>:null}{harvests.isError?<div className="state error">{harvests.error.message}</div>:null}
        {harvests.data?.items.length?<div className="table-wrap"><table><thead><tr><th>Harvest</th><th>Status</th><th>Plants</th><th>Yield</th><th>COGS</th></tr></thead><tbody>{harvests.data.items.slice(0,30).map(row=><tr key={row.id} onClick={()=>setSelectedHarvestId(row.id)}><td><strong>{row.harvest_code}</strong><br/><small>{row.strain_name} · {row.room_code||"Mixed"}</small></td><td><span className="badge">{title(row.status)}</span><br/><small>{row.started_at?`Started ${dateTime(row.started_at)}`:"Planned locally"}</small></td><td>{row.plant_count}</td><td>{row.dry_yield_pct==null?"—":`${row.dry_yield_pct.toFixed(1)}%`}<br/><small>{number(row.dry_weight)} {row.unit} dry</small></td><td>{money(row.total_cogs_usd)}{row.cost_per_dry_unit==null?null:<><br/><small>{money(row.cost_per_dry_unit)}/{row.unit}</small></>}</td></tr>)}</tbody></table></div>:harvests.data?<div className="empty">No harvests have been planned yet.</div>:null}
      </section>
    </div>

    <div className="info-banner"><strong>Regulatory boundary:</strong> starting or completing a Harvest 360 record changes DoobieLogic operational state only. Metrc plant/harvest writes remain separately fail-closed and are not enabled by this workspace.</div>
    {roomEditor?<RoomEditor room={roomEditor==="new"?null:roomEditor} onClose={()=>setRoomEditor(null)} onSaved={async()=>{setRoomEditor(null);await refresh()}}/>:null}
    {harvestBuilder?<HarvestBuilder plants={plants} onClose={()=>setHarvestBuilder(false)} onSaved={async row=>{setHarvestBuilder(false);setSelectedHarvestId(row.id);await refresh()}}/>:null}
    <WorkspaceWindow open={Boolean(selectedHarvestId)} onClose={()=>setSelectedHarvestId("")} eyebrow="CULTIVATION · HARVEST 360" title="Harvest 360" subtitle="Execution, yield, loss and true cultivation cost" ariaLabel="Harvest 360" windowKey={selectedHarvestId?`harvest-360-${selectedHarvestId}`:"harvest-360"}>
      {selectedHarvestId?<HarvestWorkspace harvestId={selectedHarvestId} canWrite={canWrite} onSelectPlant={onSelectPlant} onChanged={refresh}/>:null}
    </WorkspaceWindow>
  </section>;
}

function RoomEditor({room,onClose,onSaved}:{room:Room|null;onClose:()=>void;onSaved:()=>void|Promise<void>}) {
  const [form,setForm]=useState({room_code:room?.room_code??"",display_name:room?.display_name??"",phase:room?.phase??"",plant_capacity:room?.plant_capacity??0,square_feet:room?.square_feet??0,target_cycle_days:room?.target_cycle_days??0,active:room?.active??true,notes:room?.notes??""});
  const save=useMutation({mutationFn:()=>apiPost<Room>("/api/v1/inventory/production/plants/rooms",form),onSuccess:onSaved});
  return <StreamlitDialog open onClose={onClose} eyebrow="Cultivation" title={room?`Room · ${room.room_code}`:"Add cultivation room"} subtitle="Capacity and operating expectations stay attached to the facility room."><div className="form-grid two"><label>Room code<input value={form.room_code} disabled={Boolean(room)} onChange={e=>setForm({...form,room_code:e.target.value})}/></label><label>Display name<input value={form.display_name} onChange={e=>setForm({...form,display_name:e.target.value})}/></label><label>Expected phase<select value={form.phase} onChange={e=>setForm({...form,phase:e.target.value})}><option value="">Any phase</option><option value="clone">Clone</option><option value="seedling">Seedling</option><option value="vegetative">Vegetative</option><option value="flowering">Flowering</option></select></label><label>Plant capacity<input type="number" min="0" value={form.plant_capacity} onChange={e=>setForm({...form,plant_capacity:Number(e.target.value)})}/></label><label>Square feet<input type="number" min="0" step="0.1" value={form.square_feet} onChange={e=>setForm({...form,square_feet:Number(e.target.value)})}/></label><label>Target cycle days<input type="number" min="0" value={form.target_cycle_days} onChange={e=>setForm({...form,target_cycle_days:Number(e.target.value)})}/></label><label className="checkbox-row"><input type="checkbox" checked={form.active} onChange={e=>setForm({...form,active:e.target.checked})}/> Active room</label><label className="span-2">Notes<textarea rows={3} value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></label></div><button className="primary submit" disabled={!form.room_code.trim()||save.isPending} onClick={()=>save.mutate()}>{save.isPending?"Saving…":"Save room"}</button>{save.isError?<div className="form-error">{save.error.message}</div>:null}</StreamlitDialog>;
}

function HarvestBuilder({plants,onClose,onSaved}:{plants:CultivationPlant[];onClose:()=>void;onSaved:(row:HarvestDetail)=>void}) {
  const flowering=useMemo(()=>plants.filter(row=>row.phase==="flowering"),[plants]);
  const [harvestCode,setHarvestCode]=useState("");const [notes,setNotes]=useState("");const [selected,setSelected]=useState<string[]>([]);
  const create=useMutation({mutationFn:()=>apiPost<HarvestDetail>("/api/v1/inventory/production/plants/harvests",{harvest_code:harvestCode.trim(),plant_ids:selected,notes:notes.trim()}),onSuccess:onSaved});
  const toggle=(id:string)=>setSelected(current=>current.includes(id)?current.filter(value=>value!==id):[...current,id]);
  return <StreamlitDialog open onClose={onClose} eyebrow="Cultivation" title="Plan harvest" subtitle="Assign flowering plants to one operational harvest. Timing stays on each plant's estimated harvest date; this does not submit a Metrc harvest."><div className="form-grid"><label>Harvest code<input value={harvestCode} onChange={e=>setHarvestCode(e.target.value)} placeholder="HARV-2026-001"/></label><label>Notes<textarea rows={2} value={notes} onChange={e=>setNotes(e.target.value)}/></label></div><div className="table-wrap"><table><thead><tr><th></th><th>Plant</th><th>Strain</th><th>Room</th><th>Est. harvest</th></tr></thead><tbody>{flowering.map(plant=><tr key={plant.id} onClick={()=>toggle(plant.id)}><td><input type="checkbox" checked={selected.includes(plant.id)} onChange={()=>toggle(plant.id)} onClick={e=>e.stopPropagation()}/></td><td><strong>{plant.plant_tag}</strong></td><td>{plant.strain_name}</td><td>{plant.room_code}</td><td>{plant.estimated_harvest_date||"—"}</td></tr>)}</tbody></table>{!flowering.length?<div className="empty">No flowering plants are available to assign.</div>:null}</div><div className="audit-actions"><span className="source-caption">{selected.length} selected</span><button className="primary" disabled={!harvestCode.trim()||!selected.length||create.isPending} onClick={()=>create.mutate()}>{create.isPending?"Creating…":"Create harvest"}</button></div>{create.isError?<div className="form-error">{create.error.message}</div>:null}</StreamlitDialog>;
}

function HarvestWorkspace({harvestId,canWrite,onSelectPlant,onChanged}:{harvestId:string;canWrite:boolean;onSelectPlant:(plant:CultivationPlant)=>void;onChanged:()=>void|Promise<void>}) {
  const client=useQueryClient();
  const query=useQuery({queryKey:["cultivation-harvest",harvestId],queryFn:({signal})=>apiGet<HarvestDetail>(`/api/v1/inventory/production/plants/harvests/${harvestId}`,signal)});
  const [weights,setWeights]=useState({wet_weight:"",dry_weight:"",waste_weight:"",unit:"g",notes:""});
  const [cost,setCost]=useState({cost_type:"labor",description:"",quantity:"",unit:"hr",unit_cost:"",amount:"",notes:""});
  const refresh=async()=>{await client.invalidateQueries({queryKey:["cultivation-harvest",harvestId]});await onChanged()};
  const transition=useMutation({mutationFn:(status:string)=>apiPost<HarvestDetail>(`/api/v1/inventory/production/plants/harvests/${harvestId}/transition`,{status,wet_weight:numOrNull(weights.wet_weight),dry_weight:numOrNull(weights.dry_weight),waste_weight:numOrNull(weights.waste_weight),unit:weights.unit.trim()||"g",notes:weights.notes.trim()}),onSuccess:refresh});
  const addCost=useMutation({mutationFn:()=>apiPost<CostEntry>("/api/v1/inventory/production/plants/costs",{entity_type:"harvest",entity_id:harvestId,cost_type:cost.cost_type,description:cost.description.trim(),quantity:Number(cost.quantity||0),unit:cost.unit.trim(),unit_cost:Number(cost.unit_cost||0),amount:cost.amount===""?null:Number(cost.amount),notes:cost.notes.trim()}),onSuccess:async()=>{setCost({...cost,description:"",quantity:"",unit_cost:"",amount:"",notes:""});await refresh()}});
  const row=query.data;
  if(query.isLoading)return <div className="state">Loading Harvest 360…</div>;
  if(query.isError||!row)return <div className="state error">{query.error?.message||"Harvest could not be loaded."}</div>;
  const next=harvestNext(row.status);
  return <div className="harvest-360-workspace">
    <div className="metrics four"><Metric label="Plants" value={row.plant_count}/><Metric label="Dry yield" value={row.dry_yield_pct==null?"—":`${row.dry_yield_pct.toFixed(1)}%`}/><Metric label="Total COGS" value={money(row.total_cogs_usd)}/><Metric label={`Cost / ${row.unit}`} value={row.cost_per_dry_unit==null?"—":money(row.cost_per_dry_unit)}/></div>
    <div className="info-banner"><strong>{row.harvest_code}</strong> · {row.strain_name} · {row.room_code} · {title(row.status)}<br/><span>Local cultivation execution only. No Metrc harvest mutation is issued from Harvest 360.</span></div>
    <div className="two-col"><section className="inventory-panel"><h3>Assigned plants</h3><div className="table-wrap"><table><thead><tr><th>Tag</th><th>Strain</th><th>Room</th><th>Phase</th></tr></thead><tbody>{row.plants.map(plant=><tr key={plant.id} onClick={()=>onSelectPlant(plant)}><td><strong>{plant.plant_tag}</strong></td><td>{plant.strain_name}</td><td>{plant.room_code}</td><td>{title(plant.phase)}</td></tr>)}</tbody></table></div></section><section className="inventory-panel"><h3>Yield & loss</h3><div className="metrics"><Metric label="Wet" value={`${number(row.wet_weight)} ${row.unit}`}/><Metric label="Dry" value={`${number(row.dry_weight)} ${row.unit}`}/><Metric label="Waste" value={`${number(row.waste_weight)} ${row.unit}`}/></div>{canWrite&&!['completed','cancelled'].includes(row.status)?<><div className="form-grid two"><label>Wet weight (g)<input type="number" min="0" value={weights.wet_weight} onChange={e=>setWeights({...weights,wet_weight:e.target.value})}/></label><label>Dry weight (g)<input type="number" min="0" value={weights.dry_weight} onChange={e=>setWeights({...weights,dry_weight:e.target.value})}/></label><label>Waste weight (g)<input type="number" min="0" value={weights.waste_weight} onChange={e=>setWeights({...weights,waste_weight:e.target.value})}/></label><label>Unit<input value="g" disabled/></label><label className="span-2">Execution notes<input value={weights.notes} onChange={e=>setWeights({...weights,notes:e.target.value})}/></label></div><div className="audit-actions">{next.map(status=><button key={status} className={status==="cancelled"?"secondary":"primary"} disabled={transition.isPending} onClick={()=>transition.mutate(status)}>{transition.isPending?"Saving…":harvestAction(status)}</button>)}</div>{transition.isError?<div className="form-error">{transition.error.message}</div>:null}</>:null}</section></div>
    <section className="inventory-panel"><div className="section-heading"><div><h3>Cultivation COGS</h3><p className="source-caption">Labor, material and overhead are accumulated against the harvest so cost follows the crop instead of disappearing into a generic facility total.</p></div></div><div className="metrics four"><Metric label="Labor" value={money(row.labor_cost_usd)}/><Metric label="Material" value={money(row.material_cost_usd)}/><Metric label="Overhead" value={money(row.overhead_cost_usd)}/><Metric label="Total" value={money(row.total_cogs_usd)}/></div>{row.cost_entries.length?<div className="table-wrap"><table><thead><tr><th>Date</th><th>Type</th><th>Description</th><th>Qty</th><th>Amount</th></tr></thead><tbody>{row.cost_entries.map(entry=><tr key={entry.id}><td>{entry.occurred_on}</td><td>{title(entry.cost_type)}</td><td>{entry.description||"—"}</td><td>{number(entry.quantity)} {entry.unit}</td><td>{money(entry.amount)}</td></tr>)}</tbody></table></div>:<div className="empty">No cultivation cost entries are attached to this harvest yet.</div>}{canWrite?<div className="form-grid two"><label>Cost type<select value={cost.cost_type} onChange={e=>setCost({...cost,cost_type:e.target.value})}><option value="labor">Labor</option><option value="material">Material</option><option value="overhead">Overhead</option></select></label><label>Description<input value={cost.description} onChange={e=>setCost({...cost,description:e.target.value})}/></label><label>Quantity<input type="number" min="0" step="0.01" value={cost.quantity} onChange={e=>setCost({...cost,quantity:e.target.value})}/></label><label>Unit<input value={cost.unit} onChange={e=>setCost({...cost,unit:e.target.value})}/></label><label>Unit cost<input type="number" min="0" step="0.01" value={cost.unit_cost} onChange={e=>setCost({...cost,unit_cost:e.target.value})}/></label><label>Amount override<input type="number" min="0" step="0.01" value={cost.amount} onChange={e=>setCost({...cost,amount:e.target.value})} placeholder="Optional"/></label><label className="span-2">Notes<input value={cost.notes} onChange={e=>setCost({...cost,notes:e.target.value})}/></label><button className="primary" disabled={addCost.isPending} onClick={()=>addCost.mutate()}>{addCost.isPending?"Adding…":"Add cost"}</button>{addCost.isError?<div className="form-error">{addCost.error.message}</div>:null}</div>:null}</section>
  </div>;
}

function Metric({label,value}:{label:string;value:string|number}) {return <article className="metric"><span>{label}</span><strong>{typeof value==="number"?value.toLocaleString():value}</strong></article>}
function title(value:string){return (value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function money(value:number){return new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:2}).format(value||0)}
function number(value:number){return new Intl.NumberFormat("en-US",{maximumFractionDigits:2}).format(value||0)}
function dateTime(value:string|null|undefined){if(!value)return "—";const parsed=new Date(value);return Number.isNaN(parsed.getTime())?value:parsed.toLocaleString()}
function numOrNull(value:string){return value===""?null:Number(value)}
function harvestNext(status:string){return status==="planned"?["active","cancelled"]:status==="active"?["drying","completed"]:status==="drying"?["completed"]:[]}
function harvestAction(status:string){return status==="active"?"Start harvest":status==="drying"?"Move to drying":status==="completed"?"Complete harvest":"Cancel harvest"}
