import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type ProviderKey = "metrc" | "dutchie" | "biotrack" | "quickbooks";
type Configuration = Record<string, string | boolean>;
type Connection = {
  provider: ProviderKey;
  provider_id: string;
  label: string;
  environment: "sandbox";
  auth_mode: string;
  secret_label: string;
  required_fields: string[];
  allowed_fields: string[];
  sandbox_resources: string[];
  future_use: string;
  production_writes_enabled: boolean;
  configured: boolean;
  status: string;
  secret_hint: string;
  configuration: Configuration;
  last_validated_at: string | null;
  last_error: string;
};
type Payload = {
  environment: "sandbox";
  production_credentials_enabled: boolean;
  production_writes_enabled: boolean;
  organization_id: string;
  facility_id: string;
  scope: "facility";
  providers: Record<ProviderKey, Connection>;
};
type TestResponse = Connection & { result: { ok: boolean; configuration_ready: boolean; connected: boolean; verified: boolean; environment: string; message: string } };
type RuntimeState = {
  resource: string;
  status: "idle" | "running" | "succeeded" | "failed";
  cursor: string;
  last_started_at: string | null;
  last_completed_at: string | null;
  last_success_at: string | null;
  last_error: string;
  records_seen: number;
  records_written: number;
};
type RuntimeStatus = {
  provider: ProviderKey;
  provider_id: string;
  environment: "sandbox";
  resources: string[];
  configured_resources: string[];
  read_mode: string;
  production_writes_enabled: boolean;
  adapter_contract_ready: boolean;
  states: RuntimeState[];
  recent_attempts: Array<{
    run_id: string;
    resource: string;
    status: string;
    record_count: number;
    accepted_count: number;
    duplicate_count: number;
    error_count: number;
    error_message: string;
    started_at: string | null;
    completed_at: string | null;
  }>;
};
type SyncResult = {
  provider: ProviderKey;
  environment: "sandbox";
  production_writes_enabled: boolean;
  transport: string;
  resources: Array<{
    resource: string;
    run_id: string;
    status: string;
    cursor_before: string;
    cursor_after: string;
    record_count: number;
    accepted_count: number;
    duplicate_count: number;
    error_count: number;
    transport: string;
  }>;
  totals: { records: number; accepted: number; duplicates: number; errors: number };
};

type Field = { key: string; label: string; placeholder?: string };

const FIELDS: Record<ProviderKey, Field[]> = {
  metrc: [
    { key: "state", label: "State / jurisdiction", placeholder: "MA" },
    { key: "license_number", label: "Sandbox license / facility" },
    { key: "base_url", label: "Sandbox API base URL", placeholder: "Optional until authenticated transport is enabled" },
    { key: "notes", label: "Connection notes" },
  ],
  dutchie: [
    { key: "location_id", label: "Sandbox location ID" },
    { key: "account_id", label: "Sandbox account ID" },
    { key: "client_id", label: "Developer client ID" },
    { key: "base_url", label: "Sandbox API base URL", placeholder: "Optional until authenticated transport is enabled" },
    { key: "notes", label: "Connection notes" },
  ],
  biotrack: [
    { key: "state", label: "State / jurisdiction" },
    { key: "license_number", label: "Sandbox license / facility" },
    { key: "username", label: "Sandbox username" },
    { key: "base_url", label: "Sandbox API base URL", placeholder: "Optional until authenticated transport is enabled" },
    { key: "notes", label: "Connection notes" },
  ],
  quickbooks: [
    { key: "client_id", label: "Sandbox client ID" },
    { key: "realm_id", label: "Sandbox company / realm ID", placeholder: "Can be added after OAuth authorization" },
    { key: "redirect_uri", label: "OAuth redirect URI" },
    { key: "base_url", label: "Sandbox API base URL", placeholder: "Optional until authenticated transport is enabled" },
    { key: "notes", label: "Connection notes" },
  ],
};

export function DeveloperConnectionsPanel() {
  const data = useQuery({
    queryKey: ["sandbox-provider-connections"],
    queryFn: ({ signal }) => apiGet<Payload>("/api/v1/integrations/sandbox", signal),
    retry: false,
  });

  // Non DEV/Admin users receive 403 and simply keep the existing Integrations screen.
  if (data.isError) return null;
  if (!data.data) return null;

  return <section className="page developer-connections">
    <div className="page-heading">
      <div>
        <div className="eyebrow">Developer Connections · Sandbox only</div>
        <h2>Future provider connections</h2>
        <p>Configure isolated developer credentials now and exercise the production-shaped sync pipeline before any provider is allowed to touch production data.</p>
      </div>
      <span className="status-pill warning">SANDBOX ONLY</span>
    </div>
    <div className="info-banner">
      Production credentials and production writes are disabled here. Sandbox secrets are encrypted server-side and are never returned to the browser. Organization <strong>{data.data.organization_id}</strong> · Facility <strong>{data.data.facility_id}</strong>.
    </div>
    <div className="integration-grid">
      {(Object.keys(data.data.providers) as ProviderKey[]).map(provider => <ProviderCard key={provider} provider={provider} value={data.data!.providers[provider]} />)}
    </div>
  </section>;
}

function ProviderCard({ provider, value }: { provider: ProviderKey; value: Connection }) {
  const client = useQueryClient();
  const [configuration, setConfiguration] = useState<Record<string, string>>({});
  const [secret, setSecret] = useState("");

  useEffect(() => {
    const next: Record<string, string> = {};
    for (const field of FIELDS[provider]) next[field.key] = String(value.configuration[field.key] ?? "");
    setConfiguration(next);
    setSecret("");
  }, [provider, value]);

  const runtime = useQuery({
    queryKey: ["sandbox-provider-runtime", provider],
    queryFn: ({ signal }) => apiGet<RuntimeStatus>(`/api/v1/integrations/sandbox/${provider}/runtime`, signal),
    enabled: value.configured,
    retry: false,
  });
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["sandbox-provider-connections"] }),
      client.invalidateQueries({ queryKey: ["sandbox-provider-runtime", provider] }),
    ]);
  };
  const save = useMutation({
    mutationFn: () => apiPost<Connection>(`/api/v1/integrations/sandbox/${provider}`, { configuration, secret: secret || null }),
    onSuccess: async () => { setSecret(""); await refresh(); },
  });
  const test = useMutation({
    mutationFn: () => apiPost<TestResponse>(`/api/v1/integrations/sandbox/${provider}/test`, {}),
    onSuccess: refresh,
  });
  const sync = useMutation({
    mutationFn: () => apiPost<SyncResult>(`/api/v1/integrations/sandbox/${provider}/sync`, { resource: "" }),
    onSuccess: refresh,
  });
  const retry = useMutation({
    mutationFn: () => apiPost<{ provider: ProviderKey; environment: string; retried: number }>(`/api/v1/integrations/sandbox/${provider}/retry`, {}),
    onSuccess: refresh,
  });
  const clear = useMutation({
    mutationFn: () => apiPost<Connection>(`/api/v1/integrations/sandbox/${provider}/clear`, {}),
    onSuccess: async () => { setConfiguration({}); setSecret(""); await refresh(); },
  });
  const missing = value.required_fields.some(field => !String(configuration[field] ?? "").trim());
  const pending = save.isPending || test.isPending || sync.isPending || retry.isPending || clear.isPending;
  const error = save.error?.message || test.error?.message || sync.error?.message || retry.error?.message || clear.error?.message || runtime.error?.message;
  const readiness = test.data?.result;
  const syncSummary = sync.data?.totals;
  const failedCount = runtime.data?.states.filter(state => state.status === "failed").length ?? 0;

  return <article className="integration-card">
    <div className="integration-card-heading">
      <div><div className="eyebrow">Sandbox · {value.auth_mode}</div><h3>{value.label}</h3></div>
      <span className={`status-pill ${value.configured ? "success" : ""}`}>{value.configured ? "Sandbox configured" : "Not connected"}</span>
    </div>
    <p>{value.future_use}</p>
    <div className="form-grid">
      {FIELDS[provider].map(field => <label className={field.key === "base_url" || field.key === "notes" ? "span-2" : ""} key={field.key}>
        {field.label}{value.required_fields.includes(field.key) ? " *" : ""}
        <input value={configuration[field.key] ?? ""} placeholder={field.placeholder ?? ""} onChange={event => setConfiguration(current => ({ ...current, [field.key]: event.target.value }))}/>
      </label>)}
      <label className="span-2">{value.secret_label} *
        <input type="password" autoComplete="new-password" value={secret} placeholder={value.configured ? `Saved ${value.secret_hint} · leave blank to keep` : "Enter sandbox credential"} onChange={event => setSecret(event.target.value)}/>
      </label>
    </div>
    <p className="source-caption">Environment: sandbox · Scope: active facility · Production credential use: disabled · Production writes: disabled</p>
    <div className="button-row">
      <button className="primary" type="button" disabled={pending || missing || (!value.configured && !secret.trim())} onClick={() => save.mutate()}>Save sandbox connection</button>
      <button className="secondary" type="button" disabled={pending || !value.configured} onClick={() => test.mutate()}>Test readiness</button>
      <button className="secondary" type="button" disabled={pending || !value.configured} onClick={() => sync.mutate()}>Run sandbox sync</button>
      <button className="secondary" type="button" disabled={pending || !value.configured || failedCount === 0} onClick={() => retry.mutate()}>Retry failed syncs</button>
      <button className="secondary" type="button" disabled={pending || !value.configured} onClick={() => clear.mutate()}>Clear</button>
    </div>
    <div className="connection-result">
      <strong>Sandbox runtime</strong>
      <p>Resources: {value.sandbox_resources.join(", ")}. Read transport: deterministic sandbox fixture until authenticated vendor sandbox transport is enabled. This still exercises durable cursors, raw-record staging, normalization, dedupe, retry and reconciliation state.</p>
      {runtime.data?.states.length ? <div className="runtime-state-list">
        {runtime.data.states.map(state => <p className="source-caption" key={state.resource}>
          <strong>{state.resource}</strong> · {state.status} · cursor {state.cursor || "not started"} · seen {state.records_seen} · written {state.records_written}{state.last_error ? ` · ${state.last_error}` : ""}
        </p>)}
      </div> : <p className="source-caption">No sandbox sync has run yet.</p>}
    </div>
    {readiness ? <div className="connection-result success">{readiness.message}</div> : null}
    {syncSummary ? <div className="connection-result success">Sandbox sync complete: {syncSummary.records} records, {syncSummary.accepted} accepted, {syncSummary.duplicates} deduplicated, {syncSummary.errors} errors.</div> : null}
    {retry.data ? <div className="connection-result success">Retry pass completed for {retry.data.retried} failed resource{retry.data.retried === 1 ? "" : "s"}.</div> : null}
    {error ? <div className="form-error">{error}</div> : null}
    {value.last_error ? <div className="form-error">Last provider error: {value.last_error}</div> : null}
    {value.last_validated_at ? <p className="source-caption">Last provider validation: {new Date(value.last_validated_at).toLocaleString()}</p> : null}
  </article>;
}
