import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiDownload, apiGet, apiPost, apiPostForm, downloadBlob } from "../lib/api";

type Status = { configured: boolean; rows: number; filename: string; quality?: string; topics: string[]; error?: string };
type Source = { state: string; scope: string; topic: string; answer: string; source_citation: string; source_url: string; last_updated: string; review_status: string };
type Answer = { answer: string; sources: Source[]; source_file: string; grounded?: boolean };

export function ComplianceQAPage() {
  const client = useQueryClient();
  const status = useQuery({ queryKey: ["compliance-qa-status"], queryFn: ({ signal }) => apiGet<Status>("/api/v1/compliance-qa/status", signal) });
  const [question, setQuestion] = useState("");
  const [state, setState] = useState("MA");
  const [scope, setScope] = useState("adult-use");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const ask = async () => {
    if (!question.trim()) return;
    setBusy(true); setError("");
    try { setAnswer(await apiPost<Answer>("/api/v1/compliance-qa/query", { question, state, scope })); }
    catch (err) { setError(err instanceof Error ? err.message : "Compliance query failed."); }
    finally { setBusy(false); }
  };

  const upload = async (file?: File) => {
    if (!file) return;
    setError(""); setMessage("");
    try {
      const form = new FormData(); form.append("file", file);
      const result = await apiPostForm<{ rows: number; quality: string }>("/api/v1/compliance-qa/sources", form);
      setMessage(`Published ${result.rows.toLocaleString()} compliance source rows · ${result.quality}.`);
      setAnswer(null);
      await client.invalidateQueries({ queryKey: ["compliance-qa-status"] });
    } catch (err) { setError(err instanceof Error ? err.message : "Compliance source upload failed."); }
  };

  const template = async () => {
    try { downloadBlob(await apiDownload("/api/v1/compliance-qa/template"), "Buyer_Dash_Compliance_Source_Template.csv"); }
    catch (err) { setError(err instanceof Error ? err.message : "Template download failed."); }
  };

  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">Compliance intelligence</div><h1>Grounded Compliance Q&A</h1><p>Buyer Dash answers from the active reviewed source file for this organization and facility. It does not invent a regulation when no reviewed source supports the answer.</p></div><span className={`status-pill ${status.data?.configured ? "passed" : "warning"}`}>{status.data?.configured ? `${status.data.rows} source rows` : "Source required"}</span></div>
    <div className="two-column-grid">
      <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Ask</div><h3>Compliance question</h3></div></div><div className="form-grid"><label>State<input value={state} onChange={event => setState(event.target.value)} /></label><label>Scope<select value={scope} onChange={event => setScope(event.target.value)}><option value="adult-use">Adult-use</option><option value="medical">Medical</option><option value="both">Both</option></select></label></div><label>Question<textarea rows={5} placeholder="What does our reviewed source say about inventory adjustments?" value={question} onChange={event => setQuestion(event.target.value)} /></label><div className="form-actions"><button className="primary" disabled={busy || !status.data?.configured || !question.trim()} onClick={ask}>{busy ? "Checking sources…" : "Answer from reviewed sources"}</button></div>{status.data?.topics.length ? <p className="muted">Available topics: {status.data.topics.join(" · ")}</p> : null}</section>
      <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Source administration</div><h3>Reviewed source file</h3></div></div><p className="muted">{status.data?.configured ? `${status.data.filename} · ${status.data.rows.toLocaleString()} rows · ${status.data.quality ?? "Active"}` : "No active compliance source is available in this facility."}</p><div className="form-actions"><button className="secondary" onClick={template}>Download template</button><label className="file-drop inline-file">Publish reviewed source<input type="file" accept=".csv,.xlsx,.xls" onChange={event => upload(event.target.files?.[0])} /></label></div>{status.data?.error ? <div className="form-error">{status.data.error}</div> : null}</section>
    </div>
    {message ? <div className="success-banner">{message}</div> : null}{error ? <div className="form-error">{error}</div> : null}
    {answer ? <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Grounded answer</div><h3>{answer.grounded ? "Supported by reviewed evidence" : "No supported answer found"}</h3></div><span className="access-badge">{answer.source_file}</span></div><div className="answer-copy">{answer.answer.split("\n").map((line, index) => <p key={index}>{line || <>&nbsp;</>}</p>)}</div>{answer.sources.length ? <div className="source-grid">{answer.sources.map((source, index) => <article className="dataset-card" key={`${source.source_citation}-${index}`}><strong>{source.topic}</strong><p>{source.answer}</p><small>{source.source_citation} · Updated {source.last_updated} · {source.review_status}</small>{source.source_url ? <a href={source.source_url} target="_blank" rel="noreferrer">Open source</a> : null}</article>)}</div> : null}</section> : null}
  </div>;
}
