import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import "./adoption.css";

type Item = { key: string; label: string; route: string; status: string; evidence: string; manual: boolean; manual_status: string | null; notes: string; owner: string; target_date: string | null };
type Checklist = { items: Item[]; can_manage: boolean };

function ChecklistItem({ item, canManage, onNavigate }: { item: Item; canManage: boolean; onNavigate: (page: string) => void }) {
  const client = useQueryClient();
  const [notes, setNotes] = useState(item.notes);
  const [owner, setOwner] = useState(item.owner);
  const [target, setTarget] = useState(item.target_date ?? "");
  const [status, setStatus] = useState(item.manual_status ?? "");
  const save = useMutation({
    mutationFn: () => apiPost(`/api/v1/implementation-readiness/${item.key}`, { notes, owner, target_date: target || null, manual_status: status || null }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["implementation-readiness"] }),
  });
  return <article className="inventory-panel">
    <h2>{item.label}</h2><strong>{item.status.replaceAll("_", " ")}</strong><p>{item.evidence}</p>
    <button className="secondary" onClick={() => onNavigate(item.route)}>Open {item.route}</button>
    {canManage ? <form onSubmit={event => { event.preventDefault(); save.mutate(); }}>
      <label>Owner<input value={owner} maxLength={160} onChange={event => setOwner(event.target.value)} /></label>
      <label>Target date<input type="date" value={target} onChange={event => setTarget(event.target.value)} /></label>
      <label>Notes<textarea value={notes} maxLength={4000} onChange={event => setNotes(event.target.value)} /></label>
      {item.manual && <label>Manual attestation<select value={status} onChange={event => setStatus(event.target.value)}>
        <option value="">Use evidence / clear attestation</option>
        {["complete", "incomplete", "not_applicable", "needs_review"].map(value => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}
      </select></label>}
      <button className="primary" disabled={save.isPending}>Save review</button>
      {save.isError && <p role="alert">{save.error.message}</p>}{save.isSuccess && <p role="status">Review saved.</p>}
    </form> : <p>Owner: {item.owner || "Unassigned"}. Target: {item.target_date || "Not set"}. {item.notes}</p>}
  </article>;
}

export function ImplementationReadinessPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const query = useQuery({ queryKey: ["implementation-readiness"], queryFn: ({ signal }) => apiGet<Checklist>("/api/v1/implementation-readiness", signal) });
  return <div className="page adoption-page"><h1>Implementation Readiness</h1>
    <p>Readiness for the selected facility, derived from current records. Manual reviews require supporting notes. A configured credential does not verify an operational workflow.</p>
    {query.isPending && <p role="status">Loading readiness...</p>}
    {query.isError && <p role="alert">{query.error.message}</p>}
    <div className="report-card-grid">{query.data?.items.map(item => <ChecklistItem key={item.key} item={item} canManage={query.data.can_manage} onNavigate={onNavigate} />)}</div>
  </div>;
}
