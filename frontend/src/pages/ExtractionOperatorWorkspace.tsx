import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../lib/api";

type Stage = {
  key: string;
  label: string;
  qa_gate?: boolean;
  release_gate?: boolean;
  optional?: boolean;
  output_fields?: string[];
};

type Workflow = {
  key: string;
  label: string;
  method: string;
  stages: Stage[];
};

type Run = {
  id: string;
  batch_number: string;
  method: string;
  workflow_key: string;
  current_stage_key: string;
  status: string;
  release_status: string;
  strain: string;
  operator: string;
  final_output_g?: number;
  intermediate_product_type?: string;
  final_product_type?: string;
  formulation_used?: boolean;
  formulation_base_g?: number;
  terpene_handling_mode?: string;
  terpene_type?: string;
  terpene_source?: string;
  terpene_percentage?: number;
  terpene_weight_g?: number;
};

type StageEvent = {
  id: string;
  stage_key: string;
  event_type: string;
  input_weight_g: number | null;
  output_weight_g: number | null;
  loss_weight_g: number | null;
  loss_reason: string;
  stage_output_field?: string;
  metrc_stage_input_id?: string;
  metrc_stage_output_id?: string;
  operator: string;
  notes: string;
  occurred_at: string;
};

type Detail = {
  run: Run;
  workflow: Workflow;
  events: StageEvent[];
  mass_balance: Record<string, number>;
  cogs: Record<string, number>;
};

type StageForm = {
  input_weight_g: number;
  output_weight_g: number;
  loss_reason: string;
  notes: string;
  stage_output_field: string;
  metrc_stage_input_id: string;
  metrc_stage_output_id: string;
  intermediate_product_type: string;
  final_product_type: string;
  formulation_base_g: number;
  terpene_handling_mode: string;
  terpene_type: string;
  terpene_source: string;
  terpene_percentage: number;
  terpene_weight_g: number;
};

type StageAction = "started" | "measurement" | "completed" | "hold" | "released";

const CLOSED = new Set(["complete", "cancelled", "failed"]);
const TERPENE_MODES = [
  "Native / No Add-Back",
  "Reintroduced Cannabis Terpenes",
  "Botanically Derived Terpenes",
  "Terp Fraction Recombined",
  "Custom Blend",
];

const emptyForm = (): StageForm => ({
  input_weight_g: 0,
  output_weight_g: 0,
  loss_reason: "",
  notes: "",
  stage_output_field: "",
  metrc_stage_input_id: "",
  metrc_stage_output_id: "",
  intermediate_product_type: "",
  final_product_type: "",
  formulation_base_g: 0,
  terpene_handling_mode: "Native / No Add-Back",
  terpene_type: "",
  terpene_source: "",
  terpene_percentage: 0,
  terpene_weight_g: 0,
});

export function ExtractionOperatorWorkspace({ onOpenAdvanced }: { onOpenAdvanced: () => void }) {
  const client = useQueryClient();
  const [selected, setSelected] = useState("");
  const [search, setSearch] = useState("");
  const [showClosed, setShowClosed] = useState(false);

  const runs = useQuery({
    queryKey: ["extraction-runs"],
    queryFn: ({ signal }) => apiGet<Run[]>("/api/v1/extraction/runs", signal),
  });
  const detail = useQuery({
    queryKey: ["extraction-run", selected],
    enabled: Boolean(selected),
    queryFn: ({ signal }) => apiGet<Detail>(`/api/v1/extraction/runs/${selected}`, signal),
  });

  const filtered = useMemo(() => (runs.data ?? []).filter(row => {
    if (!showClosed && CLOSED.has(row.status)) return false;
    if (!search.trim()) return true;
    const haystack = [row.batch_number, row.strain, row.method, row.current_stage_key, row.status].join(" ").toLowerCase();
    return haystack.includes(search.trim().toLowerCase());
  }), [runs.data, search, showClosed]);

  useEffect(() => {
    if (selected || !filtered.length) return;
    const active = filtered.find(row => !CLOSED.has(row.status));
    setSelected((active ?? filtered[0]).id);
  }, [filtered, selected]);

  const activeCount = (runs.data ?? []).filter(row => !CLOSED.has(row.status)).length;
  const holdCount = (runs.data ?? []).filter(row => row.status === "hold").length;
  const qaCount = (runs.data ?? []).filter(row => row.status === "qa").length;

  return <div className="extraction-operator-workspace">
    <section className="inventory-panel">
      <div className="section-heading">
        <div>
          <div className="eyebrow">Extractor workspace</div>
          <h2>Run Floor</h2>
          <p>Open the run you are working, enter the scale readings, and let DoobieLogic calculate the process math. Advanced QA, COGS and traceability remain available without cluttering the floor workflow.</p>
        </div>
        <button className="secondary" type="button" onClick={onOpenAdvanced}>Advanced Run 360</button>
      </div>
      <div className="metrics extraction-metrics">
        <Metric label="Active" value={activeCount} />
        <Metric label="On Hold" value={holdCount} />
        <Metric label="At QA" value={qaCount} />
      </div>
      <div className="inventory-toolbar extraction-board-filters">
        <label className="inventory-search"><span>Find run</span><input aria-label="Find extraction run" value={search} placeholder="Batch, strain, method…" onChange={event => setSearch(event.target.value)} /></label>
        <label className="checkbox-field"><input type="checkbox" checked={showClosed} onChange={event => setShowClosed(event.target.checked)} /> Closed runs</label>
      </div>
      {runs.isError ? <div className="state error">{runs.error.message}</div> : null}
      <div className="table-wrap"><table><thead><tr><th>Run</th><th>Stage</th><th>Method</th><th>Strain</th><th>Latest output</th><th>Status</th></tr></thead><tbody>
        {filtered.map(row => <tr key={row.id} className="selectable-row" onClick={() => setSelected(row.id)}>
          <td><strong>{row.batch_number}</strong></td><td>{title(row.current_stage_key)}</td><td>{row.method}</td><td>{row.strain || "—"}</td><td>{row.final_output_g ? `${formatNumber(row.final_output_g)} g` : "—"}</td><td>{title(row.status)}</td>
        </tr>)}
      </tbody></table>{!runs.isLoading && !filtered.length ? <div className="empty">No matching extraction runs.</div> : null}</div>
    </section>

    {detail.isLoading && selected ? <div className="state">Loading run…</div> : null}
    {detail.isError ? <div className="state error">{detail.error.message}</div> : null}
    {detail.data ? <CurrentRun detail={detail.data} onSaved={() => {
      void client.invalidateQueries({ queryKey: ["extraction-runs"] });
      void client.invalidateQueries({ queryKey: ["extraction-parity-overview"] });
      void client.invalidateQueries({ queryKey: ["extraction-run", selected] });
    }} onOpenAdvanced={onOpenAdvanced} /> : null}
  </div>;
}

function CurrentRun({ detail, onSaved, onOpenAdvanced }: { detail: Detail; onSaved: () => void; onOpenAdvanced: () => void }) {
  const currentStage = detail.workflow.stages.find(stage => stage.key === detail.run.current_stage_key) ?? detail.workflow.stages[0];
  const stageIndex = Math.max(0, detail.workflow.stages.findIndex(stage => stage.key === currentStage.key));
  const latestByStage = useMemo(() => {
    const rows = new Map<string, StageEvent>();
    [...detail.events].sort((a, b) => Date.parse(a.occurred_at) - Date.parse(b.occurred_at)).forEach(event => {
      if (["measurement", "completed"].includes(event.event_type)) rows.set(event.stage_key, event);
    });
    return rows;
  }, [detail.events]);
  const currentEvent = latestByStage.get(currentStage.key);
  const previousStage = detail.workflow.stages[stageIndex - 1];
  const previousEvent = previousStage ? latestByStage.get(previousStage.key) : undefined;
  const consumed = Number(detail.mass_balance.consumed_input ?? 0);
  const suggestedInput = Number(currentEvent?.input_weight_g ?? previousEvent?.output_weight_g ?? consumed ?? 0);

  const [form, setForm] = useState<StageForm>(emptyForm);
  const [advanced, setAdvanced] = useState(false);

  useEffect(() => {
    const stageEvent = latestByStage.get(currentStage.key);
    setForm({
      input_weight_g: Number(stageEvent?.input_weight_g ?? previousEvent?.output_weight_g ?? consumed ?? 0),
      output_weight_g: Number(stageEvent?.output_weight_g ?? 0),
      loss_reason: stageEvent?.loss_reason ?? "",
      notes: "",
      stage_output_field: stageEvent?.stage_output_field ?? currentStage.output_fields?.[0] ?? "",
      metrc_stage_input_id: stageEvent?.metrc_stage_input_id ?? "",
      metrc_stage_output_id: stageEvent?.metrc_stage_output_id ?? "",
      intermediate_product_type: detail.run.intermediate_product_type ?? "",
      final_product_type: detail.run.final_product_type ?? "",
      formulation_base_g: Number(detail.run.formulation_base_g ?? previousEvent?.output_weight_g ?? consumed ?? 0),
      terpene_handling_mode: detail.run.terpene_handling_mode ?? "Native / No Add-Back",
      terpene_type: detail.run.terpene_type ?? "",
      terpene_source: detail.run.terpene_source ?? "",
      terpene_percentage: Number(detail.run.terpene_percentage ?? 0),
      terpene_weight_g: Number(detail.run.terpene_weight_g ?? 0),
    });
    setAdvanced(false);
  }, [consumed, currentStage.key, currentStage.output_fields, detail.run, latestByStage, previousEvent]);

  const hasOutput = form.output_weight_g > 0;
  const stageLoss = hasOutput ? Math.max(0, form.input_weight_g - form.output_weight_g) : 0;
  const stageGain = hasOutput ? Math.max(0, form.output_weight_g - form.input_weight_g) : 0;
  const stageYield = form.input_weight_g > 0 && hasOutput ? form.output_weight_g / form.input_weight_g * 100 : 0;
  const lossPct = form.input_weight_g > 0 && hasOutput ? stageLoss / form.input_weight_g * 100 : 0;
  const calculatedTerpene = form.terpene_handling_mode === "Native / No Add-Back"
    ? 0
    : (form.terpene_weight_g > 0 ? form.terpene_weight_g : form.formulation_base_g * form.terpene_percentage / 100);
  const expectedFormulatedMass = Math.max(0, form.formulation_base_g) + Math.max(0, calculatedTerpene);

  const latestMeasuredOutput = [...detail.events]
    .sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at))
    .find(event => Number(event.output_weight_g ?? 0) > 0)?.output_weight_g ?? detail.run.final_output_g ?? detail.mass_balance.recorded_output ?? 0;
  const recordedStageLoss = Array.from(latestByStage.values()).reduce((sum, event) => sum + Number(event.loss_weight_g ?? 0), 0);
  const massReduction = Math.max(0, consumed - Number(latestMeasuredOutput || 0));
  const unexplainedVariance = Math.max(0, massReduction - recordedStageLoss);
  const overallYield = consumed > 0 && Number(latestMeasuredOutput || 0) > 0 ? Number(latestMeasuredOutput) / consumed * 100 : Number(detail.mass_balance.yield_pct ?? 0);

  const isQaGate = Boolean(currentStage.qa_gate);
  const isReleaseGate = Boolean(currentStage.release_gate);
  const isFormulation = currentStage.key === "formulation";
  const outputFields = currentStage.output_fields ?? [];
  const requiresOutput = outputFields.length > 0 || currentStage.key === "final_output";

  const mutation = useMutation({
    mutationFn: (eventType: StageAction) => apiPost(`/api/v1/extraction/runs/${detail.run.id}/events`, {
      stage_key: currentStage.key,
      event_type: eventType,
      input_weight_g: form.input_weight_g > 0 ? form.input_weight_g : null,
      output_weight_g: form.output_weight_g > 0 ? form.output_weight_g : null,
      // Leave deterministic loss math to the backend. A manual loss value should
      // never be required when input and output weights already prove the answer.
      loss_weight_g: null,
      loss_reason: form.loss_reason,
      notes: form.notes,
      operator: "",
      stage_output_field: form.stage_output_field,
      metrc_stage_input_id: form.metrc_stage_input_id,
      metrc_stage_output_id: form.metrc_stage_output_id,
      intermediate_product_type: form.intermediate_product_type,
      final_product_type: form.final_product_type,
      formulation_used: isFormulation ? true : undefined,
      formulation_base_g: isFormulation ? form.formulation_base_g : undefined,
      terpene_handling_mode: isFormulation ? form.terpene_handling_mode : undefined,
      terpene_type: isFormulation ? form.terpene_type : undefined,
      terpene_source: isFormulation ? form.terpene_source : undefined,
      terpene_percentage: isFormulation ? form.terpene_percentage : undefined,
      terpene_weight_g: isFormulation ? calculatedTerpene : undefined,
    }),
    onSuccess: onSaved,
  });

  const canComplete = !requiresOutput || form.output_weight_g > 0;
  const recentEvents = [...detail.events].sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at)).slice(0, 8);

  return <section className="inventory-panel">
    <div className="section-heading"><div><div className="eyebrow">{detail.run.method} · {detail.workflow.label}</div><h2>{detail.run.batch_number}</h2><p>{detail.run.strain || "No strain set"} · {title(detail.run.status)} · current stage: <strong>{currentStage.label}</strong></p></div><button className="secondary" type="button" onClick={onOpenAdvanced}>Open full Run 360</button></div>

    <div className="metrics">
      <Metric label="Consumed input" value={`${formatNumber(consumed)} g`} />
      <Metric label="Latest measured output" value={`${formatNumber(Number(latestMeasuredOutput || 0))} g`} />
      <Metric label="Overall yield" value={`${formatNumber(overallYield, 1)}%`} />
      <Metric label="Recorded process loss" value={`${formatNumber(recordedStageLoss)} g`} />
      <Metric label="Unexplained variance" value={`${formatNumber(unexplainedVariance)} g`} />
    </div>

    <div className="detail-facts"><p><strong>Progress:</strong> Step {stageIndex + 1} of {detail.workflow.stages.length}</p><p><strong>Operator:</strong> {detail.run.operator || "Uses signed-in operator / run lead"}</p><p><strong>Release:</strong> {title(detail.run.release_status)}</p><p><strong>Input carried forward:</strong> {formatNumber(suggestedInput)} g</p></div>
    <progress max={Math.max(detail.workflow.stages.length, 1)} value={stageIndex + 1} />
    <p className="section-note">{detail.workflow.stages.map(stage => `${stage.label}${stage.key === currentStage.key ? " ← current" : ""}`).join(" → ")}</p>

    {isQaGate || isReleaseGate ? <div className="info-banner">{isQaGate ? "This run is at the QA / COA gate." : "This run is at the release gate."} Keep the floor view clean and complete the controlled QA/release action in full Run 360.</div> : <>
      <div className="section-heading"><div><div className="eyebrow">Current step</div><h3>{currentStage.label}</h3><p>Enter what the extractor actually knows. DoobieLogic calculates the loss, yield and running balance from the measurements.</p></div></div>
      <div className="form-grid">
        <NumberField label="Stage input (g)" value={form.input_weight_g} onChange={value => setForm({ ...form, input_weight_g: value })} />
        <NumberField label="Scale output (g)" value={form.output_weight_g} onChange={value => setForm({ ...form, output_weight_g: value })} />
        {outputFields.length > 1 ? <label>What was measured?<select value={form.stage_output_field} onChange={event => setForm({ ...form, stage_output_field: event.target.value })}>{outputFields.map(field => <option value={field} key={field}>{title(field)}</option>)}</select></label> : null}
        <label className="span-2">Quick note<textarea value={form.notes} placeholder="Optional operator note…" onChange={event => setForm({ ...form, notes: event.target.value })} /></label>
      </div>

      {hasOutput ? <div className="metrics">
        <Metric label="Calculated stage loss" value={`${formatNumber(stageLoss)} g`} />
        <Metric label="Loss %" value={`${formatNumber(lossPct, 1)}%`} />
        <Metric label="Stage yield" value={`${formatNumber(stageYield, 1)}%`} />
        {stageGain > 0 ? <Metric label="Net addition / gain" value={`${formatNumber(stageGain)} g`} /> : null}
      </div> : <div className="info-banner">Enter the scale output and the stage loss and yield will calculate automatically. Loss is not a required manual field.</div>}

      {isFormulation ? <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Formulation</div><h3>Blend calculation</h3></div></div><div className="form-grid">
        <NumberField label="Base material (g)" value={form.formulation_base_g} onChange={value => setForm({ ...form, formulation_base_g: value })} />
        <label>Terpene handling<select value={form.terpene_handling_mode} onChange={event => setForm({ ...form, terpene_handling_mode: event.target.value, terpene_weight_g: event.target.value === "Native / No Add-Back" ? 0 : form.terpene_weight_g })}>{TERPENE_MODES.map(mode => <option key={mode}>{mode}</option>)}</select></label>
        {form.terpene_handling_mode !== "Native / No Add-Back" ? <>
          <Field label="Terpene type" value={form.terpene_type} onChange={value => setForm({ ...form, terpene_type: value })} />
          <Field label="Terpene source" value={form.terpene_source} onChange={value => setForm({ ...form, terpene_source: value })} />
          <NumberField label="Terpene %" value={form.terpene_percentage} max={20} step={0.1} onChange={value => setForm({ ...form, terpene_percentage: value, terpene_weight_g: 0 })} />
          <NumberField label="Weight override (g)" value={form.terpene_weight_g} step={0.1} onChange={value => setForm({ ...form, terpene_weight_g: value })} />
        </> : null}
      </div><div className="info-banner">Calculated terpene addition: <strong>{formatNumber(calculatedTerpene, 3)} g</strong> · Expected formulated mass before handling loss: <strong>{formatNumber(expectedFormulatedMass, 3)} g</strong>. The extractor still confirms the actual scale output.</div></section> : null}

      <details open={advanced} onToggle={event => setAdvanced((event.currentTarget as HTMLDetailsElement).open)}><summary>More details / traceability</summary><div className="form-grid">
        <Field label="Loss / variance reason" value={form.loss_reason} onChange={value => setForm({ ...form, loss_reason: value })} />
        <Field label="METRC stage input ID" value={form.metrc_stage_input_id} onChange={value => setForm({ ...form, metrc_stage_input_id: value })} />
        <Field label="METRC stage output ID" value={form.metrc_stage_output_id} onChange={value => setForm({ ...form, metrc_stage_output_id: value })} />
        <Field label="Intermediate product type" value={form.intermediate_product_type} onChange={value => setForm({ ...form, intermediate_product_type: value })} />
        <Field label="Final product type" value={form.final_product_type} onChange={value => setForm({ ...form, final_product_type: value })} />
      </div></details>

      <div className="heading-actions">
        {detail.run.status === "hold" ? <button className="secondary" type="button" disabled={mutation.isPending} onClick={() => mutation.mutate("released")}>Resume run</button> : <button className="secondary" type="button" disabled={mutation.isPending} onClick={() => mutation.mutate("hold")}>Put on hold</button>}
        <button className="secondary" type="button" disabled={mutation.isPending} onClick={() => mutation.mutate("started")}>Start / mark active</button>
        <button className="secondary" type="button" disabled={mutation.isPending || (requiresOutput && !hasOutput)} onClick={() => mutation.mutate("measurement")}>Save update</button>
        <button className="primary" type="button" disabled={mutation.isPending || !canComplete} onClick={() => mutation.mutate("completed")}>{mutation.isPending ? "Saving…" : "Complete & move to next"}</button>
      </div>
      {mutation.isError ? <div className="form-error">{mutation.error.message}</div> : null}
      {mutation.isSuccess ? <div className="success-banner">Run updated. Calculations and stage status refreshed.</div> : null}
    </>}

    <details><summary>Recent process history</summary><div className="table-wrap"><table><thead><tr><th>Time</th><th>Stage</th><th>Update</th><th>Input</th><th>Output</th><th>Loss</th><th>Operator</th></tr></thead><tbody>{recentEvents.map(event => <tr key={event.id}><td>{dateTime(event.occurred_at)}</td><td>{detail.workflow.stages.find(stage => stage.key === event.stage_key)?.label ?? title(event.stage_key)}</td><td>{title(event.event_type)}</td><td>{event.input_weight_g == null ? "—" : `${formatNumber(event.input_weight_g)} g`}</td><td>{event.output_weight_g == null ? "—" : `${formatNumber(event.output_weight_g)} g`}</td><td>{event.loss_weight_g == null ? "—" : `${formatNumber(event.loss_weight_g)} g`}</td><td>{event.operator || "—"}</td></tr>)}</tbody></table>{!recentEvents.length ? <div className="empty">No process updates recorded yet.</div> : null}</div></details>
  </section>;
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label>{label}<input value={value} onChange={event => onChange(event.target.value)} /></label>;
}

function NumberField({ label, value, onChange, max, step = 0.1 }: { label: string; value: number; onChange: (value: number) => void; max?: number; step?: number }) {
  return <label>{label}<input type="number" min="0" max={max} step={step} value={Number.isFinite(value) ? value : 0} onChange={event => onChange(Number(event.target.value || 0))} /></label>;
}

function title(value: string | undefined): string {
  return String(value || "").replace(/_/g, " ").replace(/\b\w/g, char => char.toUpperCase());
}

function formatNumber(value: number, digits = 2): string {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function dateTime(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}
