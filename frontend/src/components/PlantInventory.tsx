import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ChangeEvent } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { CultivationPlant, PlantEvent, PlantPhase } from "../types/inventory";
import { StreamlitDialog } from "./StreamlitDialog";

const phases: PlantPhase[] = ["clone", "seedling", "vegetative", "flowering", "harvested", "destroyed"];
const next: Record<PlantPhase, PlantPhase[]> = { clone: ["seedling", "vegetative", "destroyed"], seedling: ["vegetative", "destroyed"], vegetative: ["flowering", "destroyed"], flowering: ["harvested", "destroyed"], harvested: [], destroyed: [] };
const writeRoles = new Set(["dev", "admin", "supervisor", "operator", "qa"]);

export function PlantInventory() {
  const client = useQueryClient();
  const account = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<{ user: { role: string } }>("/api/v1/account/context", signal) });
  const canWrite = writeRoles.has(account.data?.user.role ?? "");
  const [search, setSearch] = useState(""); const [phase, setPhase] = useState(""); const [room, setRoom] = useState("");
  const [creating, setCreating] = useState(false); const [selected, setSelected] = useState<CultivationPlant | null>(null);
  const query = useQuery({ queryKey: ["plants", search, phase, room], queryFn: ({ signal }) => apiGet<CultivationPlant[]>(`/api/v1/inventory/production/plants?${new URLSearchParams({ search, phase, room })}`, signal) });
  const refresh = () => client.invalidateQueries({ queryKey: ["plants"] });
  const rooms = [...new Set((query.data ?? []).map(plant => plant.room_code))];
  return <>
    <div className="plant-toolbar"><input placeholder="Search tag, strain, room…" value={search} onChange={event => setSearch(event.target.value)} /><select value={phase} onChange={event => setPhase(event.target.value)}><option value="">All phases</option>{phases.map(value => <option key={value}>{value}</option>)}</select><select value={room} onChange={event => setRoom(event.target.value)}><option value="">All rooms</option>{rooms.map(value => <option key={value}>{value}</option>)}</select>{canWrite ? <button className="primary" onClick={() => setCreating(true)}>Add plant</button> : null}</div>
    {!canWrite && account.data ? <p className="source-caption">Plant inventory is read-only for the {account.data.user.role} role.</p> : null}
    {query.isLoading ? <div className="state">Loading plant inventory…</div> : null}{query.isError ? <div className="state error">{query.error.message}</div> : null}
    {query.data ? <div className="table-wrap"><table><thead><tr><th>Plant tag</th><th>Strain</th><th>Phase</th><th>Room</th><th>Mother</th><th>Planted</th><th>Est. harvest</th></tr></thead><tbody>{query.data.map(plant => <tr key={plant.id} onClick={() => setSelected(plant)}><td>{plant.plant_tag}</td><td>{plant.strain_name}</td><td><span className="badge">{plant.phase}</span></td><td>{plant.room_code}</td><td>{plant.mother_plant_tag || "—"}</td><td>{plant.planted_at || "—"}</td><td>{plant.estimated_harvest_date || "—"}</td></tr>)}</tbody></table>{query.data.length === 0 ? <div className="empty">No plants match these filters.</div> : null}</div> : null}
    {creating ? <CreatePlant onClose={() => setCreating(false)} onSaved={refresh} /> : null}
    {selected ? <PlantDetail plant={selected} canWrite={canWrite} onClose={() => setSelected(null)} onSaved={(plant) => { setSelected(plant); refresh(); }} /> : null}
  </>;
}

function CreatePlant({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ plant_tag: "", strain_name: "", phase: "clone" as PlantPhase, room_code: "UNASSIGNED", mother_plant_tag: "", planted_at: "", estimated_harvest_date: "", notes: "" });
  const mutation = useMutation({ mutationFn: () => apiPost<CultivationPlant>("/api/v1/inventory/production/plants", { ...form, planted_at: form.planted_at || null, estimated_harvest_date: form.estimated_harvest_date || null }), onSuccess: () => { onSaved(); onClose(); } });
  const field = (key: keyof typeof form) => ({ value: form[key], onChange: (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [key]: event.target.value }) });
  return <StreamlitDialog open onClose={onClose} eyebrow="Cultivation" title="Add plant" subtitle="Create a plant tag in the active cultivation facility."><div className="form-grid"><label>Plant tag<input {...field("plant_tag")} /></label><label>Strain<input {...field("strain_name")} /></label><label>Phase<select {...field("phase")}>{phases.map(value => <option key={value}>{value}</option>)}</select></label><label>Room<input {...field("room_code")} /></label><label>Mother plant tag<input {...field("mother_plant_tag")} /></label><label>Planted date<input type="date" {...field("planted_at")} /></label><label>Estimated harvest<input type="date" {...field("estimated_harvest_date")} /></label><label className="span-2">Notes<input {...field("notes")} /></label></div><button className="primary submit" disabled={!form.plant_tag || !form.strain_name || mutation.isPending} onClick={() => mutation.mutate()}>Save plant</button>{mutation.isError ? <div className="form-error">{mutation.error.message}</div> : null}</StreamlitDialog>;
}

function PlantDetail({ plant, canWrite, onClose, onSaved }: { plant: CultivationPlant; canWrite: boolean; onClose: () => void; onSaved: (plant: CultivationPlant) => void }) {
  const [target, setTarget] = useState<PlantPhase | "">(next[plant.phase][0] ?? ""); const [room, setRoom] = useState(plant.room_code); const [reason, setReason] = useState("");
  const events = useQuery({ queryKey: ["plant-events", plant.id], queryFn: ({ signal }) => apiGet<PlantEvent[]>(`/api/v1/inventory/production/plants/${plant.id}/events`, signal) });
  const mutation = useMutation({ mutationFn: () => apiPost<CultivationPlant>(`/api/v1/inventory/production/plants/${plant.id}/transition`, { phase: target || plant.phase, room_code: room, reason, notes: "" }), onSuccess: onSaved });
  return <StreamlitDialog open onClose={onClose} eyebrow="Plant 360" title={plant.plant_tag} subtitle={`${plant.strain_name} · ${plant.phase} · ${plant.room_code}`}>
    {canWrite ? <><div className="form-grid"><label>Next phase<select value={target} onChange={event => setTarget(event.target.value as PlantPhase)}><option value="">No phase change</option>{next[plant.phase].map(value => <option key={value}>{value}</option>)}</select></label><label>Room<input value={room} onChange={event => setRoom(event.target.value)} /></label><label className="span-2">Reason<input value={reason} onChange={event => setReason(event.target.value)} /></label></div><button className="primary submit" disabled={mutation.isPending || (!target && room === plant.room_code)} onClick={() => mutation.mutate()}>Record change</button>{mutation.isError ? <div className="form-error">{mutation.error.message}</div> : null}</> : <div className="info-banner">Your role can review this plant and its lifecycle history but cannot post cultivation changes.</div>}
    <h3>Lifecycle history</h3>{events.isLoading ? <div className="state">Loading plant history…</div> : null}{events.isError ? <div className="state error">{events.error.message}</div> : null}{events.data?.map(event => <article className="plant-event" key={event.id}><strong>{event.event_type.replaceAll("_", " ")}</strong><span>{event.from_value ? `${event.from_value} → ` : ""}{event.to_value}</span><small>{new Date(event.occurred_at).toLocaleString()} · {event.actor}{event.reason ? ` · ${event.reason}` : ""}</small></article>)}{events.data && events.data.length === 0 ? <div className="empty">No lifecycle events have been recorded yet.</div> : null}
  </StreamlitDialog>;
}
