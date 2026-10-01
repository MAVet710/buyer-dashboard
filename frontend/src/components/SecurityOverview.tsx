import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type Context = { user: { id: string; role: string }; facility_id: string };
type Source = { checked_at?: number; status: string; failures?: number; last_error_category?: string | null; last_event_at?: number; detail?: Record<string, unknown> };
type Status = {
  notifications?: string;
  notification_detail?: { last_accepted?: number | null; state?: string; last_error?: string };
  state: string;
  last_success?: number | null;
  dropped?: number;
  failures?: number;
  new_failures?: number;
  new_dropped?: number;
  clean_cycles?: number;
  last_error_category?: string | null;
  last_error_at?: number | null;
  coverage?: Record<string, string>;
  perimeter?: Record<string, Source>;
};
type Incident = {
  id: string; rule: string; title: string; severity: string; status: string; occurrences: number;
  notification_status?: string; evidence: Record<string, unknown>; recovery?: Record<string, unknown>;
  recovered_at?: number;
};
type Guard = {
  state: string; checked_at?: number; threat_level: string; risk_score?: number;
  active_investigations?: number; metrc_write_protection: boolean; deception_armed: boolean;
  ai_state?: string; ai_last_success?: number;
  investigations?: Array<{ id: string; risk_score: number; confidence: number; classification: string;
    recommended_state: string; evidence_hash: string; ai_summary?: string }>;
};

const sourceLabel: Record<string, string> = {
  "windows:defender": "Windows Defender",
  "supabase:auth_audit": "Supabase Auth",
  "cloudflare:tunnel": "Cloudflare Tunnel",
};
const formatTime = (value?: number | null) => value ? new Date(value * 1000).toLocaleString() : "Not observed";

export function SecurityOverview() {
  const [open, setOpen] = useState(false);
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<Context>("/api/v1/account/context", signal) });
  const isDev = context.data?.user.role === "dev";
  const scope = `${context.data?.user.id ?? ""}:${context.data?.facility_id ?? ""}`;
  const status = useQuery({
    queryKey: ["security-observer", scope], enabled: open && isDev, retry: false,
    refetchInterval: open ? 10_000 : false, refetchIntervalInBackground: false,
    queryFn: ({ signal }) => apiGet<Status>("/api/v1/security/status", signal),
  });
  const incidents = useQuery({
    queryKey: ["security-incidents", scope], enabled: open && isDev, retry: false,
    refetchInterval: open ? 10_000 : false, refetchIntervalInBackground: false,
    queryFn: ({ signal }) => apiGet<{ items: Incident[]; total: number }>("/api/v1/security/incidents?limit=25", signal),
  });
  const guard = useQuery({
    queryKey: ["security-guard", scope], enabled: open && isDev, retry: false,
    refetchInterval: open ? 10_000 : false, refetchIntervalInBackground: false,
    queryFn: ({ signal }) => apiGet<Guard>("/api/v1/security/guard", signal),
  });
  if (!isDev) return null;
  const sources = Object.entries(status.data?.perimeter ?? {});
  return <details className="streamlit-expander" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Security Center</summary><div className="streamlit-expander-body">
      <p className="warning-banner">Security findings are observations, not proof of intrusion. Containment decisions remain deterministic and fail closed.</p>
      <button type="button" className="secondary" disabled={!open || status.isFetching || incidents.isFetching || guard.isFetching}
        onClick={() => { void status.refetch(); void incidents.refetch(); void guard.refetch(); }}>Refresh security observations</button>
      {status.isError || incidents.isError || guard.isError ? <p role="alert">Security observations are unavailable. Monitoring coverage is not verified.</p> : null}

      {guard.data && !guard.isError ? <section>
        <h4>Security Guard: {guard.data.state.toUpperCase()}</h4>
        <p>Threat: {guard.data.threat_level}. Risk score: {guard.data.risk_score ?? 0}/100. Active investigations: {guard.data.active_investigations ?? 0}. Local AI: {guard.data.ai_state ?? "not_checked"}.</p>
        <p>Metrc write protection: {guard.data.metrc_write_protection ? "ARMED" : "standby"}. Deception network: {guard.data.deception_armed ? "ARMED" : "disabled"}.</p>
        {guard.data.investigations?.map(row => <article key={row.id}><strong>{row.classification}</strong>
          <p>Risk {row.risk_score}/100 | Confidence {Math.round(row.confidence * 100)}% | Recommended: {row.recommended_state}</p>
          {row.ai_summary ? <p>Local Security Guard analysis: {row.ai_summary}</p> : null}
          <small>Evidence seal: {row.evidence_hash}</small></article>)}
      </section> : null}

      {status.data && !status.isError ? <section>
        <h4>Observer health</h4>
        <p>Observer: {status.data.state}. Dropped total: {status.data.dropped ?? 0}. Failure total: {status.data.failures ?? 0}. New failures since the last persisted cycle: {status.data.new_failures ?? 0}. Clean cycles: {status.data.clean_cycles ?? 0}.</p>
        <p>Last successful cycle: {formatTime(status.data.last_success)}. Last error: {status.data.last_error_category ?? "none"}{status.data.last_error_at ? ` at ${formatTime(status.data.last_error_at)}` : ""}.</p>
        <p>Notifications: {status.data.notifications ?? "not_connected"}. Provider acceptance is not inbox delivery.</p>
      </section> : null}

      {sources.length ? <section><h4>Perimeter coverage</h4>
        <div className="report-card-grid">{sources.map(([key, value]) => <article key={key} className="inventory-panel">
          <strong>{sourceLabel[key] ?? key}</strong>
          <p>Status: {value.status}. Collector failures: {value.failures ?? 0}.</p>
          <p>Last event: {formatTime(value.last_event_at)}. Last collector check: {formatTime(value.checked_at)}.</p>
          {value.last_error_category ? <p>Last collector error: {value.last_error_category}.</p> : null}
        </article>)}</div>
      </section> : null}

      {incidents.data && !incidents.isError ? <p>Showing the latest {incidents.data.items.length} of {incidents.data.total} incidents. Recovered incidents remain available for review.</p> : null}
      {!incidents.isError && incidents.data?.items.map(row => <article key={row.id}>
        <h4>{row.title}</h4>
        <p>{row.severity} | {row.status} | {row.occurrences} {row.rule === "monitoring_degraded" ? "new failure/drop observation" : "observation"}{row.occurrences === 1 ? "" : "s"} | Notification: {row.notification_status ?? "not_connected"}</p>
        {row.recovered_at ? <p>Recovered at {formatTime(row.recovered_at)} after clean monitoring cycles. This does not erase the incident.</p> : null}
        <details><summary>Evidence {row.id}</summary>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify({ evidence: row.evidence, recovery: row.recovery }, null, 2)}</pre>
        </details>
      </article>)}
    </div>
  </details>;
}
