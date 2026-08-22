import { useMutation } from "@tanstack/react-query";
import { apiPost } from "../lib/api";

type Row = Record<string, unknown>;
type Brief = {
  answer: string;
  explanation?: string;
  recommendations?: unknown[];
  risk_flags?: unknown[];
  inefficiencies?: unknown[];
  confidence?: string;
  mode?: string;
  routed_by?: string;
  ai?: { provider?: string; model?: string };
};

export function ExtractionDoobieBrief({
  runs,
  alerts,
  onNavigate,
}: {
  runs: Row[];
  alerts: string[];
  onNavigate: (page: string) => void;
}) {
  const brief = useMutation({
    mutationFn: () => apiPost<Brief>("/api/v1/extraction-parity/doobie-brief", {
      state: "MA",
      question: "Which extraction risks and process opportunities matter most in the current run evidence?",
    }),
  });

  return <section className="inventory-panel">
    <div className="section-heading"><div><div className="eyebrow">Doobie Ops Brief</div><h2>Grounded extraction operations brief</h2><p>Doobie evaluates the current run, yield, QA, toll-job and cost evidence. Unsupported process measurements stay explicitly unavailable instead of being invented.</p></div><div className="heading-actions"><button className="secondary" onClick={() => onNavigate("Doobie")}>Open Doobie Action Center</button><button className="primary" disabled={!runs.length || brief.isPending} onClick={() => brief.mutate()}>{brief.isPending ? "Generating…" : "Generate Doobie Ops Brief"}</button></div></div>
    <h3>Current deterministic alerts</h3>
    {alerts.length ? <ul className="exception-list">{alerts.map(value => <li key={value}>{value}</li>)}</ul> : <div className="success-banner">No current automated extraction exceptions.</div>}
    {brief.isError ? <div className="state error">{brief.error.message}</div> : null}
    {brief.data ? <div className="doobie-answer"><div className="success-banner"><strong>{brief.data.confidence ? `${brief.data.confidence} confidence · ` : ""}Doobie extraction brief</strong><div className="answer-copy">{brief.data.answer.split("\n").map((line, index) => <p key={index}>{line || <>&nbsp;</>}</p>)}</div>{brief.data.explanation ? <p>{brief.data.explanation}</p> : null}<small>{brief.data.routed_by || brief.data.mode || "Grounded extraction evidence"}{brief.data.ai?.provider ? ` · ${brief.data.ai.provider}` : ""}</small></div><List title="Recommendations" values={brief.data.recommendations}/><List title="Risk flags" values={brief.data.risk_flags}/><List title="Inefficiencies" values={brief.data.inefficiencies}/></div> : null}
    <h3>Evidence table</h3>
    <Table rows={runs.slice(0, 50)} columns={["batch_id_internal","method","input_weight_g","finished_output_g","yield_pct","status","coa_status","qa_hold","cogs_usd"]}/>
  </section>;
}

function List({ title, values = [] }: { title: string; values?: unknown[] }) {
  if (!values.length) return null;
  return <><h3>{title}</h3><ul className="exception-list">{values.map((value, index) => <li key={index}>{typeof value === "string" ? value : JSON.stringify(value)}</li>)}</ul></>;
}
function heading(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase()); }
function show(value: unknown) { if (value == null || value === "") return "—"; if (typeof value === "object") return JSON.stringify(value); if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 }); return String(value); }
function Table({ rows, columns }: { rows: Row[]; columns: string[] }) { const visible = columns.filter(column => rows.some(row => row[column] !== undefined)); return <div className="table-wrap"><table><thead><tr>{visible.map(column => <th key={column}>{heading(column)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{visible.map(column => <td key={column}>{show(row[column])}</td>)}</tr>)}</tbody></table>{rows.length === 0 ? <div className="empty">No extraction runs are available for this brief.</div> : null}</div>; }
