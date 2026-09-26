import { useState } from "react";
import { WorkspaceWindow } from "./WorkspaceWindow";
import { RecipeEditor } from "./RecipeEditor";
import { Room360 } from "./Room360";
import { CropCycle360 } from "./CropCycle360";
import { ReadState, WriteState } from "./CultivationIntelligenceShared";
import { useIntelligence, useIntelligenceWrite } from "./cultivationIntelligenceQueries";
import { type Cycle, type Recipe, type Workspace } from "./cultivationIntelligenceTypes";
import "./cultivation-intelligence.css";

export function CultivationIntelligenceWorkspace({ initialRoomId = "", initialCycleId = "" }: { initialRoomId?: string; initialCycleId?: string }) {
  const query = useIntelligence<Workspace>("/workspace");
  const [room, setRoom] = useState(initialRoomId);
  const [cycle, setCycle] = useState(initialCycleId);
  const [panel, setPanel] = useState("");
  function close(kind: "room" | "cycle") {
    if (kind === "room") setRoom(""); else setCycle("");
    const url = new URL(window.location.href); url.searchParams.delete(kind); if (kind === "room") for (const key of ["edge_exception", "start", "end"]) url.searchParams.delete(key); window.history.replaceState(window.history.state, "", url);
  }
  return <section className="inventory-panel cultivation-intelligence"><div className="section-heading"><div><h2>Cultivation command panel</h2><p>Canonical rooms and crop cycles with evidence on demand. Decision support only.</p></div></div>
    <ReadState query={query}>{data => <><div className="ci-actions"><a className="secondary" href="/settings/integrations?provider=cultivation">Cultivation connection setup</a>{data.can_manage && <><button className="primary" onClick={() => setPanel("create")}>Create Cycle</button><button className="secondary" onClick={() => setPanel("recipes")}>Recipes</button></>}</div>
      <p>Connection data: {data.connections.length ? `${data.connections.filter(item => !item.revoked_at && item.status !== "revoked").length} active cultivation connections` : "No cultivation connections"}. Normalized HTTP push and file evidence are separate collection modes. Native vendor activation requires a reviewed contract. Environmental status requires room evidence.</p>
      {!data.rooms.length && <p className="empty">No canonical rooms are configured. Use the existing room workflow below to create one.</p>}
      {data.truncated && <p role="status">Showing a bounded workspace summary. Additional records may not be included.</p>}
      <div className="ci-cards">{data.rooms.map(item => <article className="ci-stage" key={item.id}><h3>{item.display_name || item.room_code}</h3><p>{item.phase} · {item.active ? "Active" : "Inactive"}</p><p>Canonical plant count: {item.plant_count ?? "Unknown"}. Current stage: {item.current_stage?.display_name || "Unknown"}. {item.context_truncated ? "Context incomplete. " : ""}Plant capacity: {item.plant_capacity ?? "Unknown"}. Open room evidence for canonical plants and cycle occupancy.</p>{item.current_cycle_ids?.map(id => <p key={id}><a href={`/cultivation?cycle=${encodeURIComponent(id)}`}>Current cycle {id}</a></p>)}<a className="secondary" href={`/cultivation?room=${encodeURIComponent(item.id)}`}>Open Room 360</a></article>)}</div>
      <details><summary>Crop cycles ({data.cycles.length})</summary>{data.cycles.length ? data.cycles.map(item => <p key={item.id}><a href={`/cultivation?cycle=${encodeURIComponent(item.id)}`}>Open Crop Cycle: {item.display_name || item.cycle_code}</a> · {item.status}</p>) : <p>No crop cycles recorded in this facility.</p>}</details>
      <WorkspaceWindow open={Boolean(room)} title="Room 360" windowKey={`room360-${room}`} onClose={() => close("room")} className="cultivation-intelligence">{room && <Room360 key={room} roomId={room} recipes={data.recipes} />}</WorkspaceWindow>
      <WorkspaceWindow open={Boolean(cycle)} title="Crop Cycle 360" windowKey={`cycle360-${cycle}`} onClose={() => close("cycle")} className="cultivation-intelligence">{cycle && <CropCycle360 key={cycle} cycleId={cycle} rooms={data.rooms} recipes={data.recipes} />}</WorkspaceWindow>
      <WorkspaceWindow open={Boolean(panel) && data.can_manage} title={panel === "create" ? "Create Cycle" : "Recipes"} windowKey="cultivation-editor" onClose={() => setPanel("")} className="cultivation-intelligence">{panel === "create" ? <CreateCycle recipes={data.recipes} onSaved={created => { setPanel(""); setCycle(created.id); const url = new URL(window.location.href); url.searchParams.set("cycle", created.id); window.history.replaceState(window.history.state, "", url); }} /> : <RecipeEditor recipes={data.recipes} canManage={data.can_manage} />}</WorkspaceWindow>
    </>}</ReadState>
  </section>;
}
function CreateCycle({ recipes, onSaved }: { recipes: Recipe[]; onSaved: (cycle: Cycle) => void }) {
  const save = useIntelligenceWrite<Cycle>("/cycles", onSaved);
  return <form onSubmit={event => { event.preventDefault(); const fields = new FormData(event.currentTarget); save.mutate({ cycle_code: fields.get("cycle_code"), display_name: fields.get("display_name"), genetics_label: fields.get("genetics_label") || "", nursery_group_id: fields.get("nursery_group_id") || null, recipe_id: fields.get("recipe_id") || null, started_on: fields.get("started_on") || null, estimated_harvest_date: fields.get("estimated_harvest_date") || null }); }}><fieldset disabled={save.isPending}><div className="form-grid">
    <label>Cycle code<input name="cycle_code" required /></label><label>Cycle name<input name="display_name" required /></label><label>Genetics label<input name="genetics_label" /></label><label>Canonical nursery group ID (optional)<input name="nursery_group_id" /></label>
    <label>Approved recipe<select name="recipe_id"><option value="">No recipe</option>{recipes.filter(recipe => recipe.status === "approved").map(recipe => <option value={recipe.id} key={recipe.id}>{recipe.name} · Version {recipe.version}</option>)}</select></label><label>Started on<input type="date" name="started_on" /></label><label>Estimated harvest date<input type="date" name="estimated_harvest_date" /></label>
  </div><button className="primary">Save cycle</button></fieldset><WriteState error={save.error} /></form>;
}
