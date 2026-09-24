import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type Context = { user: { id: string; role: string }; facility_id: string };
type Status = { state: string; last_success?: number | null; dropped?: number; failures?: number };
type Incident = { id: string; title: string; severity: string; status: string; occurrences: number; evidence: unknown };
export function SecurityOverview() {
  const [open, setOpen] = useState(false);
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<Context>("/api/v1/account/context", signal) });
  const isDev = context.data?.user.role === "dev";
  const scope = `${context.data?.user.id ?? ""}:${context.data?.facility_id ?? ""}`;
  const status = useQuery({ queryKey: ["security-observer", scope], enabled: open && isDev, retry: false,
    queryFn: ({ signal }) => apiGet<Status>("/api/v1/security/status", signal) });
  const incidents = useQuery({ queryKey: ["security-incidents", scope], enabled: open && isDev, retry: false,
    queryFn: ({ signal }) => apiGet<{ items: Incident[]; total: number }>("/api/v1/security/incidents?limit=25", signal) });
  if (!isDev) return null;
  return <details className="streamlit-expander" onToggle={event => setOpen(event.currentTarget.open)}><summary>Security Center</summary><div className="streamlit-expander-body">
    <p className="warning-banner">Read-only incident review. Email and external monitoring are not connected. An alert is not proof of intrusion.</p>
    <button type="button" className="secondary" disabled={!open || status.isFetching || incidents.isFetching} onClick={() => { void status.refetch(); void incidents.refetch(); }}>Refresh security observations</button>
    {status.isError || incidents.isError ? <p role="alert">Security observations are unavailable. Monitoring coverage is not verified.</p> : null}
    {status.data && !status.isError ? <p>Observer: {status.data.state}. Dropped: {status.data.dropped ?? 0}. Failures: {status.data.failures ?? 0}. Last check: {status.data.last_success ? new Date(status.data.last_success * 1000).toLocaleString() : "Not observed"}.</p> : null}
    {incidents.data && !incidents.isError ? <p>Showing the latest {incidents.data.items.length} of {incidents.data.total} incidents. No records does not mean attack-free.</p> : null}
    {!incidents.isError && incidents.data?.items.map(row => <article key={row.id}><h4>{row.title}</h4><p>{row.severity} | {row.status} | {row.occurrences} observations</p><details><summary>Evidence {row.id}</summary><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(row.evidence, null, 2)}</pre></details></article>)}
  </div></details>;
}
