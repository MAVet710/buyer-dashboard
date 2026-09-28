import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type Context = { user: { id: string; role: string }; facility_id: string };
type Status = { notifications?: string; notification_detail?: { last_accepted?: number | null }; state: string; last_success?: number | null; dropped?: number; failures?: number };
type Incident = { id: string; title: string; severity: string; status: string; occurrences: number; notification_status?: string; evidence: unknown };
type Guard = { state: string; checked_at?: number; threat_level: string; risk_score?: number; active_investigations?: number; metrc_write_protection: boolean; deception_armed: boolean; ai_state?: string; ai_last_success?: number; investigations?: Array<{ id: string; risk_score: number; confidence: number; classification: string; recommended_state: string; evidence_hash: string; ai_summary?: string }> };
export function SecurityOverview() {
  const [open, setOpen] = useState(false);
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<Context>("/api/v1/account/context", signal) });
  const isDev = context.data?.user.role === "dev";
  const scope = `${context.data?.user.id ?? ""}:${context.data?.facility_id ?? ""}`;
  const status = useQuery({ queryKey: ["security-observer", scope], enabled: open && isDev, retry: false,
    queryFn: ({ signal }) => apiGet<Status>("/api/v1/security/status", signal) });
  const incidents = useQuery({ queryKey: ["security-incidents", scope], enabled: open && isDev, retry: false,
    queryFn: ({ signal }) => apiGet<{ items: Incident[]; total: number }>("/api/v1/security/incidents?limit=25", signal) });
  const guard = useQuery({ queryKey: ["security-guard", scope], enabled: open && isDev, retry: false,
    queryFn: ({ signal }) => apiGet<Guard>("/api/v1/security/guard", signal) });
  if (!isDev) return null;
  return <details className="streamlit-expander" onToggle={event => setOpen(event.currentTarget.open)}><summary>Security Center</summary><div className="streamlit-expander-body">
    <p className="warning-banner">Read-only incident review. An alert is not proof of intrusion. Email is not connected unless explicitly configured and verified.</p>
    <button type="button" className="secondary" disabled={!open || status.isFetching || incidents.isFetching || guard.isFetching} onClick={() => { void status.refetch(); void incidents.refetch(); void guard.refetch(); }}>Refresh security observations</button>
    {status.isError || incidents.isError || guard.isError ? <p role="alert">Security observations are unavailable. Monitoring coverage is not verified.</p> : null}
    {guard.data && !guard.isError ? <section><h4>Security Guard: {guard.data.state.toUpperCase()}</h4><p>Threat: {guard.data.threat_level}. Risk score: {guard.data.risk_score ?? 0}/100. Active investigations: {guard.data.active_investigations ?? 0}. Local AI: {guard.data.ai_state ?? "not_checked"}.</p><p>Metrc write protection: {guard.data.metrc_write_protection ? "ARMED" : "standby"}. Deception network: {guard.data.deception_armed ? "ARMED" : "disabled"}.</p>{guard.data.investigations?.map(row => <article key={row.id}><strong>{row.classification}</strong><p>Risk {row.risk_score}/100 | Confidence {Math.round(row.confidence * 100)}% | Recommended: {row.recommended_state}</p>{row.ai_summary ? <p>Local Security Guard analysis: {row.ai_summary}</p> : null}<small>Evidence seal: {row.evidence_hash}</small></article>)}</section> : null}
    {status.data && !status.isError ? <p>Notifications: {status.data.notifications ?? "not_connected"}. Provider acceptance is not inbox delivery. Observer: {status.data.state}. Dropped: {status.data.dropped ?? 0}. Failures: {status.data.failures ?? 0}. Last check: {status.data.last_success ? new Date(status.data.last_success * 1000).toLocaleString() : "Not observed"}.</p> : null}
    {incidents.data && !incidents.isError ? <p>Showing the latest {incidents.data.items.length} of {incidents.data.total} incidents. No records does not mean attack-free.</p> : null}
    {!incidents.isError && incidents.data?.items.map(row => <article key={row.id}><h4>{row.title}</h4><p>{row.severity} | {row.status} | {row.occurrences} observations | Notification: {row.notification_status ?? "not_connected"}</p><details><summary>Evidence {row.id}</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(row.evidence, null, 2)}</pre></details></article>)}
  </div></details>;
}
