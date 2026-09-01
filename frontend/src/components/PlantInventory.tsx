import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ChangeEvent } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { CultivationPlant, PlantEvent, PlantPhase } from "../types/inventory";
import { CultivationBatchManager } from "./CultivationBatchManager";
import { CultivationIntelligencePanel } from "./CultivationIntelligencePanel";
import { CultivationOperationsControl } from "./CultivationOperationsControl";
import { CultivationRegulatoryHealth } from "./CultivationRegulatoryHealth";
import { CultivationToday } from "./CultivationToday";
import { StreamlitDialog } from "./StreamlitDialog";
import { WorkspaceWindow } from "./WorkspaceWindow";

const phases: PlantPhase[] = ["clone", "seedling", "vegetative", "flowering", "harvested", "destroyed"];
const next: Record<PlantPhase, PlantPhase[]> = { clone: ["seedling", "vegetative", "destroyed"], seedling: ["vegetative", "destroyed"], vegetative: ["flowering", "destroyed"], flowering: ["harvested", "destroyed"], harvested: [], destroyed: [] };
const writeRoles = new Set(["dev", "admin", "supervisor", "operator", "qa"]);

type PlantLineage = {
  plant_id:string; plant_tag:string; strain_name:string;
  group:null|{id:string;group_code:string;group_type:string;status:string};
  mother:null|{id:string;plant_tag:string;strain_name:string;phase:string};
  source_lot:null|{id:string;lot_code:string;compliance_package_id:string};
};
type Room = { id:string;room_code:string;display_name:string;phase:string;plant_capacity:number;active:boolean;active_plants?:number };
type RoomList = { items:Room[] };
type BulkResult = { count:number;changed_count:number;phase:string|null;room_code:string|null;items:Array<{id:string;plant_tag:string;strain_name:string;phase:PlantPhase;room_code:string}> };

export function PlantInventory() {
  const client = useQueryClient();
  const account = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<{ user: { role: string } }>("/api/v1/account/context", signal) });
  const canWrite = writeRoles.has(account.data?.user.role ?? "");
  const [search, setSearch] = useState(""); const [phase, setPhase] = useState(""); const [room, setRoom] = useState("");
  const [creating, setCreating] = useState(false); const [selected, setSelected] = useState<CultivationPlant | null>(null);
  const [selectedIds,setSelectedIds]=useState<string[]>([]); const [bulkOpen,setBulkOpen]=useState(false); const [bulkPhase,setBulkPhase]=useState<PlantPhase|"">(""); const [bulkRoom,setBulkRoom]=useState(""); const [bulkReason,setBulkReason]=useState(""); const [bulkNotes,setBulkNotes]=useState(""); const [flash,setFlash]=useState("");
  const overview = useQuery({ queryKey: ["plants-overview"], queryFn: ({ signal }) => apiGet<CultivationPlant[]>("/api/v1/inventory/production/plants", signal) });
  const query = useQuery({ queryKey: ["plants", search, phase, room], queryFn: ({ signal }) => apiGet<CultivationPlant[]>(`/api/v1/inventory/production/plants?${new URLSearchParams({ search, phase, room })}`, signal) });
  const roomsQuery=useQuery({queryKey:["cultivation-rooms"],queryFn:({signal})=>apiGet<RoomList>("/api/v1/inventory/production/plants/rooms",signal)});
  const refresh = () => { void client.invalidateQueries({ queryKey: ["plants"] }); void client.invalidateQueries({ queryKey: ["plants-overview"] }); void client.invalidateQueries({ queryKey:["cultivation-rooms"] }); void client.invalidateQueries({ queryKey: ["cultivation-intelligence"] }); };
  const rooms = [...new Set((overview.data ?? query.data ?? []).map(plant => plant.room_code))];
  const visibleIds=(query.data??[]).map(plant=>plant.id);
  const allVisibleSelected=Boolean(visibleIds.length)&&visibleIds.every(id=>selectedIds.includes(id));
  const selectedPlants=(overview.data??query.data??[]).filter(plant=>selectedIds.includes(plant.id));
  const toggle=(id:string)=>setSelectedIds(ids=>ids.includes(id)?ids.filter(value=>value!==id):[...ids,id]);
  const toggleAll=()=>setSelectedIds(ids=>allVisibleSelected?ids.filter(id=>!visibleIds.includes(id)):[...new Set([...ids,...visibleIds])]);
  const clearSelection=()=>setSelectedIds([]);
  const bulkMutation=useMutation({mutationFn:()=>apiPost<BulkResult>("/api/v1/inventory/production/plants/bulk-transition",{plant_ids:selectedIds,phase:bulkPhase||null,room_code:bulkRoom||null,reason:bulkReason,notes:bulkNotes}),onSuccess:result=>{setFlash(`${result.changed_count} of ${result.count} selected plant(s) updated atomically.`);setBulkOpen(false);setBulkPhase("");setBulkRoom("");setBulkReason("");setBulkNotes("");clearSelection();refresh();}});
  return <>
    {flash?<div className="success-banner">{flash}</div>:null}
    {overview.data ? <CultivationToday plants={overview.data} onSelect={setSelected} /> : null}
    {overview.data ? <CultivationBatchManager plants={overview.data} canWrite={canWrite} onChanged={refresh} /> : null}
    {overview.data ? <CultivationOperationsControl plants={overview.data} canWrite={canWrite} onSelectPlant={setSelected} /> : null}
    <CultivationIntelligencePanel />
    <CultivationRegulatoryHealth />
    <div className="plant-toolbar"><input placeholder="Search tag, strain, room…" value={search} onChange={event => {setSearch(event.target.value);clearSelection();}} /><select value={phase} onChange={event => {setPhase(event.target.value);clearSelection();}}><option value="">All phases</option>{phases.map(value => <option key={value}>{value}</option>)}</select><select value={room} onChange={event => {setRoom(event.target.value);clearSelection();}}><option value="">All rooms</option>{rooms.map(value => <option key={value}>{value}</option>)}</select>{canWrite ? <button className="secondary" onClick={() => setCreating(true)}>Add one plant</button> : null}</div>
    {!canWrite && account.data ? <p className="source-caption">Plant inventory is read-only for the {account.data.user.role} role.</p> : null}
    {selectedIds.length?<section className="inventory-panel selection-toolbar"><strong>{selectedIds.length} plant(s) selected</strong><span className="source-caption">Bulk changes are validated as one transaction. If any plant or destination fails validation, none are changed.</span><button className="primary" disabled={!canWrite} onClick={()=>setBulkOpen(true)}>Move / change phase</button><button className="secondary" onClick={clearSelection}>Clear selection</button></section>:null}
    {overview.isError ? <div className="state error">Cultivation Today could not load: {overview.error.message}</div> : null}
    {query.isLoading ? <div className="state">Loading plant inventory…</div> : null}{query.isError ? <div className="state error">{query.error.message}</div> : null}
    {query.data ? <div className="table-wrap"><table><thead><tr><th><input type="checkbox" aria-label="Select all visible plants" checked={allVisibleSelected} disabled={!query.data.length} onChange={toggleAll}/></th><th>Plant tag</th><th>Strain</th><th>Phase</th><th>Room</th><th>Mother</th><th>Planted</th><th>Est. harvest</th></tr></thead><tbody>{query.data.map(plant => <tr key={plant.id} className={selectedIds.includes(plant.id)?"selected-row":""} onClick={() => setSelected(plant)}><td><input type="checkbox" aria-label={`Select ${plant.plant_tag}`} checked={selectedIds.includes(plant.id)} onChange={()=>toggle(plant.id)} onClick={event=>event.stopPropagation()}/></td><td>{plant.plant_tag}</td><td>{plant.strain_name}</td><td><span className="badge">{plant.phase}</span></td><td>{plant.room_code}</td><td>{plant.mother_plant_tag || "—"}</td><td>{plant.planted_at || "—"}</td><td>{plant.estimated_harvest_date || "—"}</td></tr>)}</tbody></table>{query.data.length === 0 ? <div className="empty">No plants match these filters.</div> : null}</div> : null}
    {creating ? <CreatePlant onClose={() => setCreating(false)} onSaved={refresh} /> : null}
    <WorkspaceWindow open={bulkOpen} onClose={()=>setBulkOpen(false)} eyebrow="CULTIVATION · BULK ACTION" title={`Move ${selectedIds.length} selected plant(s)`} subtitle="The whole selection commits together or not at all. Room capacity and lifecycle transitions are checked before any plant changes." ariaLabel="Bulk plant movement" windowKey="cultivation-bulk-move" className="workspace-window-wide">
      <div className="form-grid"><label>New phase<select aria-label="New phase" value={bulkPhase} onChange={event=>setBulkPhase(event.target.value as PlantPhase|"")}><option value="">Keep current phase</option>{phases.map(value=><option key={value} value={value}>{value}</option>)}</select></label><label>Destination room<select aria-label="Destination room" value={bulkRoom} onChange={event=>setBulkRoom(event.target.value)}><option value="">Keep current room</option>{(roomsQuery.data?.items??[]).filter(row=>row.active).map(row=><option key={row.id} value={row.room_code}>{row.display_name||row.room_code} · {row.room_code}{row.phase?` · ${row.phase}`:""}{row.plant_capacity?` · cap ${row.plant_capacity}`:""}</option>)}</select></label><label className="span-2">Reason<input aria-label="Bulk change reason" value={bulkReason} onChange={event=>setBulkReason(event.target.value)} placeholder="Why are these plants moving?" /></label><label className="span-2">Notes<textarea aria-label="Bulk change notes" value={bulkNotes} onChange={event=>setBulkNotes(event.target.value)} /></label></div>
      <section className="inventory-panel"><div className="eyebrow">SELECTION</div><h3>{selectedIds.length} plant(s)</h3><div className="table-wrap"><table><thead><tr><th>Tag</th><th>Strain</th><th>Current phase</th><th>Current room</th></tr></thead><tbody>{selectedPlants.slice(0,100).map(plant=><tr key={plant.id}><td>{plant.plant_tag}</td><td>{plant.strain_name}</td><td>{plant.phase}</td><td>{plant.room_code}</td></tr>)}</tbody></table>{selectedPlants.length>100?<div className="source-caption">Showing the first 100 selected plants. All {selectedIds.length} will be validated and committed together.</div>:null}</div></section>
      <div className="audit-actions"><button className="primary" disabled={bulkMutation.isPending||(!bulkPhase&&!bulkRoom)||!selectedIds.length} onClick={()=>bulkMutation.mutate()}>Validate and apply to all</button><button className="secondary" onClick={()=>setBulkOpen(false)}>Cancel</button></div>{bulkMutation.isError?<div className="form-error">{bulkMutation.error.message}</div>:null}
    </WorkspaceWindow>
    <WorkspaceWindow open={Boolean(selected)} onClose={() => setSelected(null)} eyebrow="CULTIVATION · PLANT 360" title={selected?.plant_tag ?? "Plant 360"} subtitle={selected ? `${selected.strain_name} · ${selected.phase} · ${selected.room_code}` : undefined} ariaLabel="Plant 360" windowKey={selected ? `plant-360-${selected.id}` : "plant-360"}>
      {selected ? <PlantDetail key={selected.id} plant={selected} canWrite={canWrite} onSaved={(plant) => { setSelected(plant); refresh(); }} /> : null}
    </WorkspaceWindow>
  </>;
}

function CreatePlant({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ plant_tag: "", strain_name: "", phase: "clone" as PlantPhase, room_code: "UNASSIGNED", mother_plant_tag: "", planted_at: "", estimated_harvest_date: "", notes: "" });
  const mutation = useMutation({ mutationFn: () => apiPost<CultivationPlant>("/api/v1/inventory/production/plants", { ...form, planted_at: form.planted_at || null, estimated_harvest_date: form.estimated_harvest_date || null }), onSuccess: () => { onSaved(); onClose(); } });
  const field = (key: keyof typeof form) => ({ value: form[key], onChange: (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [key]: event.target.value }) });
  return <StreamlitDialog open onClose={onClose} eyebrow="Cultivation" title="Add one plant" subtitle="Use this for an exception or individual tag. For nursery/clone work, create a plant group instead."><div className="form-grid"><label>Plant tag<input {...field("plant_tag")} /></label><label>Strain<input {...field("strain_name")} /></label><label>Phase<select {...field("phase")}>{phases.map(value => <option key={value}>{value}</option>)}</select></label><label>Room<input {...field("room_code")} /></label><label>Legacy mother tag<input {...field("mother_plant_tag")} /></label><label>Planted date<input type="date" {...field("planted_at")} /></label><label>Estimated harvest<input type="date" {...field("estimated_harvest_date")} /></label><label className="span-2">Notes<input {...field("notes")} /></label></div><button className="primary submit" disabled={!form.plant_tag || !form.strain_name || mutation.isPending} onClick={() => mutation.mutate()}>Save plant</button>{mutation.isError ? <div className="form-error">{mutation.error.message}</div> : null}</StreamlitDialog>;
}

function PlantDetail({ plant, canWrite, onSaved }: { plant: CultivationPlant; canWrite: boolean; onSaved: (plant: CultivationPlant) => void }) {
  const [target, setTarget] = useState<PlantPhase | "">(next[plant.phase][0] ?? ""); const [room, setRoom] = useState(plant.room_code); const [reason, setReason] = useState("");
  const events = useQuery({ queryKey: ["plant-events", plant.id], queryFn: ({ signal }) => apiGet<PlantEvent[]>(`/api/v1/inventory/production/plants/${plant.id}/events`, signal) });
  const lineage = useQuery({ queryKey:["plant-lineage",plant.id], queryFn:({signal})=>apiGet<PlantLineage>(`/api/v1/inventory/production/plants/${plant.id}/lineage`,signal) });
  const mutation = useMutation({ mutationFn: () => apiPost<CultivationPlant>(`/api/v1/inventory/production/plants/${plant.id}/transition`, { phase: target || plant.phase, room_code: room, reason, notes: "" }), onSuccess: onSaved });
  return <div className="plant-360-workspace">
    <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Genetics & source</div><h3>Plant lineage</h3></div></div>{lineage.isLoading?<div className="state">Loading lineage…</div>:null}{lineage.isError?<div className="state error">{lineage.error.message}</div>:null}{lineage.data?<div className="detail-facts"><p><strong>Group:</strong> {lineage.data.group?.group_code||"Individual plant"}</p><p><strong>Mother:</strong> {lineage.data.mother?`${lineage.data.mother.plant_tag} · ${lineage.data.mother.strain_name}`:"No first-class mother link"}</p><p><strong>Source lot:</strong> {lineage.data.source_lot?.lot_code||"—"}</p><p><strong>External package:</strong> {lineage.data.source_lot?.compliance_package_id||"—"}</p></div>:null}</section>
    {canWrite ? <><div className="form-grid"><label>Next phase<select value={target} onChange={event => setTarget(event.target.value as PlantPhase)}><option value="">No phase change</option>{next[plant.phase].map(value => <option key={value}>{value}</option>)}</select></label><label>Room<input value={room} onChange={event => setRoom(event.target.value)} /></label><label className="span-2">Reason<input value={reason} onChange={event => setReason(event.target.value)} /></label></div><button className="primary submit" disabled={mutation.isPending || (!target && room === plant.room_code)} onClick={() => mutation.mutate()}>Record change</button>{mutation.isError ? <div className="form-error">{mutation.error.message}</div> : null}</> : <div className="info-banner">Your role can review this plant and its lifecycle history but cannot post cultivation changes.</div>}
    <h3>Lifecycle history</h3>{events.isLoading ? <div className="state">Loading plant history…</div> : null}{events.isError ? <div className="state error">{events.error.message}</div> : null}{events.data?.map(event => <article className="plant-event" key={event.id}><strong>{event.event_type.replaceAll("_", " ")}</strong><span>{event.from_value ? `${event.from_value} → ` : ""}{event.to_value}</span><small>{new Date(event.occurred_at).toLocaleString()} · {event.actor}{event.reason ? ` · ${event.reason}` : ""}</small></article>)}{events.data && events.data.length === 0 ? <div className="empty">No lifecycle events have been recorded yet.</div> : null}
  </div>;
}
