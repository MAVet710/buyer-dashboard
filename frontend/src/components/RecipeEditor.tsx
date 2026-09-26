import { useState, type FormEvent } from "react";
import { recipeDraftPayload } from "./recipeDraftPayload";
import { ReadState, WriteState } from "./CultivationIntelligenceShared";
import { useIntelligence, useIntelligenceWrite } from "./cultivationIntelligenceQueries";
import { metricLabel, type Recipe, type RegistryMetric, type Stage } from "./cultivationIntelligenceTypes";

export function RecipeEditor({ recipes, canManage }: { recipes: Recipe[]; canManage: boolean }) {
  const registry = useIntelligence<{ metrics: RegistryMetric[] }>("/metrics");
  const [editing, setEditing] = useState<Recipe | "new" | null>(null);
  return <div className="cultivation-intelligence"><p>Setpoint targets and derived exception thresholds are decision support, not equipment controls. Facility-defined standards. Approved versions are immutable. Changes create a new draft version.</p>
    {recipes.length === 0 && <p>No recipes have been defined for this facility.</p>}
    {recipes.map(recipe => <section className="ci-stage" key={recipe.id}><h3>{recipe.name} · Version {recipe.version}</h3><p>{recipe.status} · {recipe.description}</p>
      {recipe.approved_at && <p>Approved {recipe.approved_at} by {recipe.approved_by || "Unknown approver"}</p>}
      {recipe.stages.map(stage => <details key={stage.stage_key}><summary>{stage.display_name}</summary>{stage.targets.map(target => <p key={target.metric}>{metricLabel(target.metric, registry.data?.metrics)}: {target.minimum ?? "No minimum"} to {target.maximum ?? "no maximum"} {target.unit}. Continuous deviation threshold: {target.threshold_seconds == null ? "not configured" : `${target.threshold_seconds} seconds (${target.threshold_seconds / 60} minutes)`}</p>)}</details>)}
      {canManage && <div className="ci-actions"><button className="secondary" onClick={() => setEditing(recipe)}>New version from this recipe</button>{recipe.status === "draft" && <ApproveRecipe recipe={recipe} />}</div>}
    </section>)}
    {canManage && <button className="secondary" onClick={() => setEditing("new")}>New recipe</button>}
    {canManage && editing && <ReadState query={registry}>{data => <RecipeForm key={editing === "new" ? "new" : editing.id} recipe={editing === "new" ? undefined : editing} metrics={data.metrics} onSaved={() => setEditing(null)} />}</ReadState>}
  </div>;
}
function ApproveRecipe({ recipe }: { recipe: Recipe }) {
  const save = useIntelligenceWrite(`/recipes/${encodeURIComponent(recipe.id)}/approve`);
  return <div><button className="primary" disabled={save.isPending || save.isSuccess} onClick={() => save.mutate({ version: recipe.version })}>Approve version {recipe.version}</button><WriteState error={save.error} /></div>;
}
function RecipeForm({ recipe, metrics, onSaved }: { recipe?: Recipe; metrics: RegistryMetric[]; onSaved: () => void }) {
  const [name, setName] = useState(recipe?.name || "");
  const [description, setDescription] = useState(recipe?.description || "");
  const [stages, setStages] = useState<Stage[]>(recipe?.stages.map(({ stage_key, display_name, sequence, targets }) => ({ stage_key, display_name, sequence, targets: targets.map(target => ({ ...target })) })) || []);
  const [validation, setValidation] = useState("");
  const save = useIntelligenceWrite<Recipe>("/recipes", onSaved);
  const update = (index: number, stage: Stage) => setStages(current => current.map((value, i) => i === index ? stage : value));
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!stages.length || new Set(stages.map(stage => stage.stage_key)).size !== stages.length) { setValidation("Add at least one stage and use unique stage keys."); return; }
    if (stages.some(stage => stage.targets.some(target => (target.minimum === null && target.maximum === null) || (target.minimum !== null && target.maximum !== null && target.minimum > target.maximum) || !metrics.some(metric => metric.metric === target.metric && metric.unit === target.unit)))) { setValidation("Every target needs a registry metric, its normalized unit and at least one valid bound. Minimum cannot exceed maximum."); return; }
    setValidation(""); save.mutate(recipeDraftPayload(name, description, stages));
  }
  return <form onSubmit={submit}><h3>{recipe ? "New recipe version" : "Create recipe"}</h3><fieldset disabled={save.isPending}>
    <label>Recipe name<input required value={name} onChange={event => setName(event.target.value)} /></label><label>Description<textarea value={description} onChange={event => setDescription(event.target.value)} /></label>
    {stages.map((stage, index) => <section className="ci-stage" key={index}><div className="form-grid"><label>Stage key<input required value={stage.stage_key} onChange={event => update(index, { ...stage, stage_key: event.target.value })} /></label><label>Stage name<input required value={stage.display_name} onChange={event => update(index, { ...stage, display_name: event.target.value })} /></label></div>
      {stage.targets.map((target, targetIndex) => <div className="form-grid" key={targetIndex}><label>Measurement<select required value={target.metric} onChange={event => { const metric = metrics.find(item => item.metric === event.target.value); if (metric) update(index, { ...stage, targets: stage.targets.map((item, i) => i === targetIndex ? { ...item, metric: metric.metric, unit: metric.unit } : item) }); }}><option value="">Choose measurement</option>{!metrics.some(item => item.metric === target.metric) && target.metric && <option value={target.metric}>{metricLabel(target.metric)} (unavailable)</option>}{metrics.map(metric => <option key={metric.metric} value={metric.metric}>{metricLabel(metric.metric, metrics)} ({metric.unit})</option>)}</select></label>
        {(["minimum", "maximum"] as const).map(bound => <label key={bound}>{bound === "minimum" ? "Minimum" : "Maximum"} ({target.unit || "select unit"})<input type="number" step="any" value={target[bound] ?? ""} onChange={event => update(index, { ...stage, targets: stage.targets.map((item, i) => i === targetIndex ? { ...item, [bound]: event.target.value === "" ? null : Number(event.target.value) } : item) })} /></label>)}
        <label>Continuous deviation threshold (seconds, optional)<input type="number" min="1" max="2678400" step="1" value={target.threshold_seconds ?? ""} onChange={event => update(index, { ...stage, targets: stage.targets.map((item, i) => i === targetIndex ? { ...item, threshold_seconds: event.target.value === "" ? null : Number(event.target.value) } : item) })} /><small>{target.threshold_seconds == null ? "Not configured" : `${target.threshold_seconds / 60} minutes; 60 seconds = 1 minute`}</small></label><button type="button" className="secondary" onClick={() => update(index, { ...stage, targets: stage.targets.filter((_, i) => i !== targetIndex) })}>Remove target</button></div>)}
      <div className="ci-actions"><button type="button" className="secondary" onClick={() => update(index, { ...stage, targets: [...stage.targets, { metric: "", unit: "", minimum: null, maximum: null }] })}>Add target</button><button type="button" className="secondary" onClick={() => setStages(stages.filter((_, i) => i !== index))}>Remove stage</button></div>
    </section>)}
    <div className="ci-actions"><button type="button" className="secondary" onClick={() => setStages([...stages, { stage_key: "", display_name: "", sequence: stages.length, targets: [] }])}>Add facility stage</button><button className="primary" type="submit">Save draft version</button></div>
  </fieldset>{validation && <p role="alert">{validation}</p>}<WriteState error={save.error} /></form>;
}
