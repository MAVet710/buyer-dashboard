import { useState, type FormEvent } from "react";
import { CultivationEventForm, RoomEvidence } from "./Room360";
import { ConnectionFreshness, AggregateWindow, ZoneSelect, EvidenceList, ReadState, WriteState } from "./CultivationIntelligenceShared";
import { useIntelligence, useIntelligenceWrite } from "./cultivationIntelligenceQueries";
import { record, rows, textValue, type Cycle, type Recipe, type Room } from "./cultivationIntelligenceTypes";

type Detail = { connection_freshness?: unknown; cycle: Cycle; approved_recipe?: Recipe | null; edge_summary?: unknown; post_harvest?: unknown; lineage_outputs?: unknown[]; quality?: unknown[]; members: unknown[]; occupancy: unknown[]; harvest: unknown; economics: { allocated_cost: number | null; allocation_status: string; provenance: unknown[] }; events: unknown[]; lineage: unknown[]; truncated: boolean; can_manage: boolean };
export function CropCycle360({ cycleId, rooms, recipes }: { cycleId: string; rooms: Room[]; recipes: Recipe[] }) {
  const [window, setWindow] = useState("");
  const query = useIntelligence<Detail>(`/cycles/${encodeURIComponent(cycleId)}${window}`);
  const [tab, setTab] = useState("Crop");
  return <ReadState query={query}>{data => data.cycle.id !== cycleId ? <p role="alert">Requested cycle is unavailable. No alternative cycle was selected.</p> : <div className="cultivation-intelligence"><h3>{data.cycle.display_name || data.cycle.cycle_code}</h3><p>{data.cycle.status} · Version {data.cycle.version} · Genetics: {data.cycle.genetics_label || "Unknown"}</p>{data.truncated && <p>Evidence is incomplete because the result limit was reached.</p>}
    <nav className="ci-tabs" aria-label="Cycle sections">{["Crop", "Environment", "History", "Economics", "Manage"].filter(name => name !== "Manage" || data.can_manage).map(name => <button className="secondary" aria-pressed={tab === name} key={name} onClick={() => setTab(name)}>{name}</button>)}</nav>
    {tab === "Crop" && <><p>Started: {data.cycle.started_on || "Unknown"} · Estimated harvest: {data.cycle.estimated_harvest_date || "Unknown"}</p><p>Approved recipe: {(data.approved_recipe || recipes.find(recipe => recipe.id === data.cycle.recipe_id))?.name || "No evidenced recipe"}</p><h4>Canonical membership</h4><EvidenceList value={data.members} empty="No canonical membership evidence. Current room does not prove historical cycle membership." />{data.cycle.harvest_id ? <p>Canonical harvest ID: {data.cycle.harvest_id}. <a href="/cultivation/post-harvest">Open existing harvest workspace</a></p> : <p>No canonical harvest is linked.</p>}</>}
    {tab === "Environment" && <><ConnectionFreshness value={data.connection_freshness} /><AggregateWindow onApply={setWindow} />{record(data.edge_summary).truncated === true && <p>Cycle room summaries are incomplete.</p>}{rows(record(data.edge_summary).rooms).length ? rows(record(data.edge_summary).rooms).map((entry, i) => <section key={i}><h4>Room {textValue(entry.room_id)}</h4><RoomEvidence summary={entry.summary} /></section>) : <p>No cycle aggregate evidence. Coverage is unknown.</p>}</>}
    {tab === "History" && <><h4>Occupancy and stage history</h4><EvidenceList value={data.occupancy} empty="Occupancy and stage history are unknown until intervals are recorded." /><h4>Events</h4><EvidenceList value={data.events} empty="No cycle events have been recorded." /><h4>Post-harvest reference</h4><EvidenceList value={data.post_harvest ? [data.post_harvest] : []} empty="No canonical post-harvest reference." /><h4>Lineage output references</h4><EvidenceList value={data.lineage_outputs} empty="No canonical output references." /><h4>Quality references</h4><EvidenceList value={data.quality} empty="No verified quality references." /><h4>Material lineage</h4><EvidenceList value={data.lineage} empty="No material lineage evidence is supplied for this cycle." /></>}
    {tab === "Economics" && <><p>True COGS, grade and revenue remain unknown. Allocated cost: {data.economics.allocated_cost === null ? "Unknown" : data.economics.allocated_cost} · {data.economics.allocation_status}</p><EvidenceList value={data.economics.provenance} empty="No cost allocation provenance is available. True COGS, grade and revenue remain unknown." /><a href="/cultivation">Open canonical cultivation costs</a></>}
    {tab === "Manage" && data.can_manage && <><CycleActions cycle={data.cycle} rooms={rooms} recipes={data.approved_recipe ? [data.approved_recipe] : recipes} occupancy={data.occupancy} members={data.members} /><CultivationEventForm cycleId={cycleId} /></>}
  </div>}</ReadState>;
}
function CycleActions({ cycle, rooms, recipes, occupancy, members }: { cycle: Cycle; rooms: Room[]; recipes: Recipe[]; occupancy: unknown[]; members: unknown[] }) {
  const [boundary, setBoundary] = useState("");
  const [action, setAction] = useState("occupancy");
  return <>{boundary && <p role="status">Occupancy closed at {boundary}. The next interval is not saved until you submit below; its entry is prefilled at that same half-open boundary.</p>}{rows(occupancy).filter(item => !item.exited_at && typeof item.id === "string").map(item => <CloseOccupancy key={String(item.id)} cycle={cycle} occupancy={item} onClosed={setBoundary} />)}<label>Cycle action<select value={action} onChange={event => setAction(event.target.value)}><option value="occupancy">Record room / stage interval</option><option value="members">Change canonical membership</option><option value="harvest">Link existing harvest</option></select></label><CycleActionForm key={`${cycle.id}:${action}:${boundary}`} boundary={boundary} members={members} action={action} cycle={cycle} rooms={rooms} recipes={recipes} /></>;
}
function CloseOccupancy({ cycle, occupancy, onClosed }: { cycle: Cycle; occupancy: Record<string, unknown>; onClosed: (boundary: string) => void }) {
  const [version, setVersion] = useState(cycle.version);
  const [boundary, setBoundary] = useState("");
  const save = useIntelligenceWrite<{ version: number }>(`/cycles/${encodeURIComponent(cycle.id)}/occupancy/${encodeURIComponent(String(occupancy.id))}/close`, () => onClosed(boundary));
  return <form onSubmit={event => { event.preventDefault(); save.mutate({ version, exited_at: boundary }); }}><h4>Close open occupancy</h4><p>Room {textValue(occupancy.room_id)}, stage {textValue(occupancy.stage_id)}, entered {textValue(occupancy.entered_at)}. Closing is a separate durable action. Add the next room/stage below at the same boundary after it succeeds.</p>{version !== cycle.version && <button type="button" onClick={() => { setVersion(cycle.version); save.reset(); }}>Use current close version {cycle.version}</button>}<fieldset disabled={save.isPending || save.isSuccess}><label>Transition boundary (ISO with timezone)<input required value={boundary} onChange={event => setBoundary(event.target.value)} /></label><button className="primary">Close this occupancy</button></fieldset><WriteState error={save.error} success={save.isSuccess} /></form>;
}
function CycleActionForm({ action, cycle, rooms, recipes, boundary, members }: { action: string; cycle: Cycle; rooms: Room[]; recipes: Recipe[]; boundary: string; members: unknown[] }) {
  const [roomId, setRoomId] = useState("");
  const choices = useIntelligence<{ plants: {id: string; plant_tag: string}[]; truncated: boolean }>(`/rooms/${encodeURIComponent(roomId)}`, Boolean(roomId) && action === "members");
  // Freeze the version while input is being edited. Refetches cannot silently rebase a write.
  const [version, setVersion] = useState(cycle.version);
  const [validation, setValidation] = useState("");
  const save = useIntelligenceWrite<{ version: number }>(`/cycles/${encodeURIComponent(cycle.id)}/${action}`, result => setVersion(result.version));
  const recipe = recipes.find(item => item.id === cycle.recipe_id && item.status === "approved");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    let body: unknown;
    if (action === "occupancy") body = { version, room_id: fields.get("room_id"), zone_id: fields.get("zone_id") || null, stage_id: fields.get("stage_id") || null, entered_at: fields.get("entered_at"), exited_at: fields.get("exited_at") || null };
    else if (action === "members") {
      const ids = fields.getAll("plant_ids").map(String);
      if (!ids.length || ids.length > 200 || new Set(ids).size !== ids.length) { setValidation("Enter 1 to 200 unique canonical plant IDs."); return; }
      body = { version, plant_ids: ids, action: fields.get("member_action"), effective_at: fields.get("effective_at") };
    } else body = { version, harvest_id: fields.get("harvest_id") };
    setValidation(""); save.mutate(body);
  }
  return <form onSubmit={submit}><p>Editing cycle version {version}. IDs must reference existing records in this facility.</p>{cycle.version !== version && <button type="button" className="secondary" onClick={() => { setVersion(cycle.version); save.reset(); }}>Use current version {cycle.version} and keep input</button>}
    <fieldset disabled={save.isPending || save.isSuccess}><div className="form-grid">
      {action === "occupancy" && <><label>Room<select name="room_id" required value={roomId} onChange={event => setRoomId(event.target.value)}><option value="">Choose canonical room</option>{rooms.map(room => <option key={room.id} value={room.id}>{room.display_name || room.room_code}</option>)}</select></label><ZoneSelect key={roomId} roomId={roomId} /><label>Approved recipe stage<select name="stage_id" defaultValue=""><option value="">No evidenced stage</option>{recipe?.stages.filter(stage => stage.id).map(stage => <option key={stage.id} value={stage.id}>{stage.display_name}</option>)}</select></label><label>Entered at (ISO with timezone)<input name="entered_at" required defaultValue={boundary} /></label><label>Exited at (optional ISO with timezone)<input name="exited_at" /></label></>}
      {action === "members" && <><label>Plant choice room<select value={roomId} onChange={event => setRoomId(event.target.value)}><option value="">Choose canonical room</option>{rooms.map(room => <option key={room.id} value={room.id}>{room.display_name || room.room_code}</option>)}</select></label><label>Canonical plant IDs<select name="plant_ids" multiple required>{Array.from(new Map([...rows(members).filter(item => typeof item.plant_id === "string").map(item => [String(item.plant_id), textValue(item.plant_tag ?? item.plant_id)] as const), ...(choices.data?.plants || []).map(item => [item.id, item.plant_tag] as const)]).entries()).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>{roomId && <ReadState query={choices}>{data => <p>{data.truncated ? "Plant choices are incomplete." : `${data.plants.length} canonical room plants available.`}</p>}</ReadState>}<label>Membership action<select name="member_action"><option value="add">Add</option><option value="remove">Remove</option></select></label><label>Effective at (ISO with timezone)<input name="effective_at" required /></label></>}
      {action === "harvest" && <label>Existing canonical harvest ID<input name="harvest_id" required /><small>Server validates exclusive, complete harvest membership.</small></label>}
    </div><button className="primary">Save cycle action</button></fieldset>{validation && <p role="alert">{validation}</p>}<WriteState error={save.error} success={save.isSuccess} />{save.isSuccess && <button type="button" className="secondary" onClick={() => save.reset()}>Start another action</button>}</form>;
}
