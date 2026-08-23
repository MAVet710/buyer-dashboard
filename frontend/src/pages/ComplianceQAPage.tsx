import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiDownload, apiGet, apiPost, apiPostForm, downloadBlob } from "../lib/api";

type Status = {
  configured: boolean;
  rows: number;
  filename: string;
  quality?: string;
  topics: string[];
  columns: string[];
  preview: Record<string, string>[];
  error?: string;
};
type Source = {
  state: string;
  scope: string;
  topic: string;
  answer: string;
  source_citation: string;
  source_url: string;
  last_updated: string;
  review_status: string;
};
type Answer = { answer: string; sources: Source[]; source_file: string; grounded?: boolean };

const REQUIRED_COLUMNS = [
  "state",
  "scope",
  "topic",
  "answer",
  "source_citation",
  "source_url",
  "last_updated",
  "review_status",
] as const;

const DEFAULT_QUESTION = "What are the packaging requirements for adult-use products?";

export function ComplianceQAPage() {
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["compliance-qa-status"],
    queryFn: ({ signal }) => apiGet<Status>("/api/v1/compliance-qa/status", signal),
  });
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [state, setState] = useState("CA");
  const [scope, setScope] = useState("adult-use");
  const [topic, setTopic] = useState("packaging");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [message, setMessage] = useState("");
  const [warning, setWarning] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);

  const ask = async () => {
    setError("");
    setWarning("");
    setMessage("");
    if (!status.data?.configured) {
      setWarning("Upload structured compliance source rows first.");
      return;
    }
    setBusy(true);
    try {
      setAnswer(await apiPost<Answer>("/api/v1/compliance-qa/query", { question, state, scope, topic }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Compliance query failed.");
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file?: File) => {
    if (!file) return;
    setUploadBusy(true);
    setError("");
    setWarning("");
    setMessage("");
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await apiPostForm<{ rows: number }>("/api/v1/compliance-qa/sources", form);
      setMessage(`Loaded ${result.rows.toLocaleString()} compliance source row(s).`);
      setAnswer(null);
      await client.invalidateQueries({ queryKey: ["compliance-qa-status"] });
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Compliance source upload failed.";
      setError(`Could not load compliance sources: ${detail}`);
    } finally {
      setUploadBusy(false);
    }
  };

  const template = async () => {
    setError("");
    try {
      downloadBlob(await apiDownload("/api/v1/compliance-qa/template"), "compliance_sources_template.csv");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Template download failed.");
    }
  };

  const previewColumns = status.data?.columns?.length ? status.data.columns : [...REQUIRED_COLUMNS];
  const previewRows = status.data?.preview ?? [];
  const loadedMessage = message || (status.data?.configured ? `Loaded ${status.data.rows.toLocaleString()} compliance source row(s).` : "");

  return <div className="page exact-compliance-qa">
    <div className="page-heading">
      <div>
        <h1>🧭 Compliance Q&amp;A</h1>
        <p>Grounded compliance answers from structured sources only. Upload reviewed source rows and query by state/scope/topic.</p>
      </div>
    </div>

    <p><strong>Required source columns</strong>: {REQUIRED_COLUMNS.join(", ")}</p>

    <div className="form-actions">
      <button className="secondary" type="button" onClick={template}>Download compliance source template (CSV)</button>
    </div>

    <label className="file-drop">
      {uploadBusy ? "Loading compliance sources…" : "Upload structured compliance sources (CSV)"}
      <input
        type="file"
        accept=".csv,text/csv"
        disabled={uploadBusy}
        onChange={event => upload(event.target.files?.[0])}
      />
    </label>

    {loadedMessage ? <div className="success-banner">{loadedMessage}</div> : null}
    {status.data?.error ? <div className="form-error">Could not load compliance sources: {status.data.error}</div> : null}
    {error ? <div className="form-error">{error}</div> : null}

    {previewRows.length ? <div className="table-wrap compact-table" aria-label="Compliance source preview">
      <table>
        <thead><tr>{previewColumns.map(column => <th key={column}>{column}</th>)}</tr></thead>
        <tbody>{previewRows.slice(0, 100).map((row, rowIndex) => <tr key={rowIndex}>{previewColumns.map(column => <td key={column}>{row[column] ?? ""}</td>)}</tr>)}</tbody>
      </table>
    </div> : null}

    <div className="form-grid three compliance-qa-filters">
      <label>METRC State<input value={state} onChange={event => setState(event.target.value)} /></label>
      <label>Scope<select value={scope} onChange={event => setScope(event.target.value)}><option value="adult-use">adult-use</option><option value="medical">medical</option></select></label>
      <label>Topic<input value={topic} onChange={event => setTopic(event.target.value)} /></label>
    </div>

    <label>Compliance question<textarea rows={5} value={question} onChange={event => setQuestion(event.target.value)} /></label>
    <div className="form-actions">
      <button className="primary" type="button" disabled={busy} onClick={ask}>{busy ? "Answering…" : "Answer from structured sources"}</button>
    </div>

    {warning ? <div className="info-banner">{warning}</div> : null}

    {answer ? <section className="inventory-panel compliance-answer">
      <div className="answer-copy" role="status">
        {answer.answer.split("\n").map((line, index) => {
          if (line.trim() === "---") return <hr key={index} />;
          if (line.startsWith("- ")) return <p key={index}>• {line.slice(2)}</p>;
          if (line.trim() === "Source Records") return <h4 key={index}>Source Records</h4>;
          return <p key={index}>{line || <>&nbsp;</>}</p>;
        })}
      </div>
    </section> : null}
  </div>;
}
