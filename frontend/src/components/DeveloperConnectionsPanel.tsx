import { useEffect, useRef, useState } from "react";
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
  sandbox_user_provisioning_enabled?: boolean;
  facility_discovery_enabled?: boolean;
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
type LocalFacility = { id: string; name: string; code: string; license_number: string; license_type: string };
type DiscoveredFacility = {
  name: string;
  license_number: string;
  provider_facility_id: string;
  license_type: string;
  status: "created" | "linked" | "needs_confirmation" | "ready_to_create";
  match_reason?: string;
  mapping_permanent?: boolean;
  message?: string;
  doobielogic_facility?: LocalFacility;
  suggested_matches?: LocalFacility[];
  bootstrap_error?: string;
};
type FacilityDiscoveryResponse = {
  ok: boolean;
  state: string;
  environment: "sandbox";
  provider: "metrc";
  facility_count: number;
  facilities: DiscoveredFacility[];
  auto_created: number;
  auto_linked: number;
  needs_confirmation: number;
  bootstrap_resources: string[];
};
type ProvisionResponse = {
  ok: boolean;
  status: string;
  http_status: number;
  state: string;
  environment: "sandbox";
  endpoint: string;
  user_key_returned: boolean;
  user_key_saved: boolean;
  facility_discovery: FacilityDiscoveryResponse | null;
  facility_discovery_error: string;
  message: string;
};
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
    { key: "license_number", label: "Sandbox license / facility", placeholder: "Leave blank — DoobieLogic discovers this from Metrc" },
    { key: "base_url", label: "Sandbox API base URL", placeholder: "Optional; verified jurisdiction routing is used for provider calls" },
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

  if (data.isError) return null;
  if (!data.data) return null;

  return <section className="page developer-connections">
    <div className="page-heading">
      <div>
        <div className="eyebrow">Developer Connections · Sandbox only</div>
        <h2>Future provider connections</h2>
        <p>Connect the provider once. DoobieLogic discovers the provider-owned regulatory structure and builds the operational mirror underneath it.</p>
      </div>
      <span className="status-pill warning">SANDBOX ONLY</span>
    </div>
    <div className="info-banner">
      Production credentials and production writes are disabled here. Sandbox secrets are encrypted server-side and are never returned to the browser. Organization <strong>{data.data.organization_id}</strong> · Current workspace <strong>{data.data.facility_id}</strong>.
    </div>
    <div className="integration-grid">
      {(Object.keys(data.data.providers) as ProviderKey[]).map(provider => <ProviderCard key={`${data.data!.organization_id}:${data.data!.facility_id}:${provider}`} provider={provider} value={data.data!.providers[provider]} />)}
    </div>
  </section>;
}

function ProviderCard({ provider, value }: { provider: ProviderKey; value: Connection }) {
  const client = useQueryClient();
  const [configuration, setConfiguration] = useState<Record<string, string>>({});
  const [secret, setSecret] = useState("");
  const [initialSync, setInitialSync] = useState<Record<string, string>>({});
  const [syncing, setSyncing] = useState(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);

  const bootstrapFacilities = async (rows: DiscoveredFacility[]) => {
    setSyncing(true);
    try {
      for (const row of rows) {
        if (!active.current) break;
        const facility = row.doobielogic_facility;
        if (!facility) continue;
        setInitialSync(current => ({ ...current, [row.license_number]: "Syncing initial METRC data…" }));
        try {
          const result = await apiPost<{ ok: boolean; bootstrap: { totals: { failed: number; records: number }; resources: { status: string; message?: string }[] } }>(
            "/api/v1/integrations/sandbox/metrc/facilities/bootstrap",
            { facility_id: facility.id, license_number: row.license_number },
          );
          if (active.current) setInitialSync(current => ({ ...current, [row.license_number]: result.ok
            ? `Initial sync complete · ${result.bootstrap.totals.records} records.`
            : `Initial sync incomplete · ${result.bootstrap.totals.failed} resources failed. ${result.bootstrap.resources.find(resource => resource.status === "failed")?.message ?? "Retry is available."}` }));
          if (!result.ok) break;
        } catch (error) {
          if (active.current) setInitialSync(current => ({ ...current, [row.license_number]: error instanceof Error ? error.message : "Initial sync failed. Retry is available." }));
          break; // Do not cascade a database/provider outage across every facility.
        }
      }
    } finally {
      if (active.current) setSyncing(false);
    }
  };

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
      client.invalidateQueries({ queryKey: ["integrations"] }),
      client.invalidateQueries({ queryKey: ["admin-tenants"] }),
    ]);
  };
  const save = useMutation({
    mutationFn: () => apiPost<Connection>(`/api/v1/integrations/sandbox/${provider}`, { configuration, secret: secret || null }),
    onSuccess: async () => { setSecret(""); await refresh(); },
  });
  const discovery = useMutation({
    mutationFn: () => apiPost<FacilityDiscoveryResponse>("/api/v1/integrations/sandbox/metrc/discover-facilities", {}),
    onSuccess: data => { void bootstrapFacilities(data.facilities).then(() => { if (active.current) void refresh(); }); },
  });
  const confirm = useMutation({
    mutationFn: (input: { license_number: string; target_facility_id?: string; create_new?: boolean }) => apiPost<{ ok: boolean; facility: DiscoveredFacility }>("/api/v1/integrations/sandbox/metrc/facilities/confirm", input),
    onSuccess: async () => { await refresh(); discovery.mutate(); },
  });
  const provision = useMutation({
    mutationFn: () => apiPost<ProvisionResponse>("/api/v1/integrations/sandbox/metrc/provision-user", {}),
    onSuccess: data => {
      if (data.facility_discovery) void bootstrapFacilities(data.facility_discovery.facilities).then(() => { if (active.current) void refresh(); });
      else void refresh();
    },
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
  const pending = syncing || save.isPending || provision.isPending || discovery.isPending || confirm.isPending || test.isPending || sync.isPending || retry.isPending || clear.isPending;
  const error = save.error?.message || provision.error?.message || discovery.error?.message || confirm.error?.message || test.error?.message || sync.error?.message || retry.error?.message || clear.error?.message || runtime.error?.message;
  const readiness = test.data?.result;
  const syncSummary = sync.data?.totals;
  const failedCount = runtime.data?.states.filter(state => state.status === "failed").length ?? 0;
  const secretLabel = provider === "metrc" ? "Metrc Integrator / Vendor API Key" : value.secret_label;
  const facilityDiscovery = discovery.data ?? provision.data?.facility_discovery ?? null;

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
      <label className="span-2">{secretLabel} *
        <input type="password" autoComplete="new-password" value={secret} placeholder={value.configured ? `Saved ${value.secret_hint} · leave blank to keep` : "Enter sandbox credential"} onChange={event => setSecret(event.target.value)}/>
      </label>
    </div>
    {provider === "metrc" ? <p className="source-caption">1. Save MA + the Metrc Connect Integrator/Vendor key. 2. Provision the sandbox user. 3. DoobieLogic calls GET /facilities/v2/ and creates or maps each regulatory facility automatically. You do not type the Metrc facility/license into DoobieLogic first.</p> : null}
    <p className="source-caption">Environment: sandbox · Production credential use: disabled · Production writes: disabled</p>
    <div className="button-row">
      <button className="primary" type="button" disabled={pending || missing || (!value.configured && !secret.trim())} onClick={() => save.mutate()}>Save sandbox connection</button>
      {provider === "metrc" && value.sandbox_user_provisioning_enabled ? <button className="secondary" type="button" disabled={pending || !value.configured} onClick={() => provision.mutate()}>Provision sandbox user</button> : null}
      {provider === "metrc" && value.facility_discovery_enabled ? <button className="secondary" type="button" disabled={pending || !value.configured} onClick={() => discovery.mutate()}>Discover Metrc facilities</button> : null}
      <button className="secondary" type="button" disabled={pending || !value.configured} onClick={() => test.mutate()}>Test readiness</button>
      <button className="secondary" type="button" disabled={pending || !value.configured} onClick={() => sync.mutate()}>Run sandbox sync</button>
      <button className="secondary" type="button" disabled={pending || !value.configured || failedCount === 0} onClick={() => retry.mutate()}>Retry failed syncs</button>
      <button className="secondary" type="button" disabled={pending || !value.configured} onClick={() => clear.mutate()}>Clear</button>
    </div>
    {provider === "metrc" && facilityDiscovery ? <div className="connection-result success">
      <strong>Metrc facility discovery</strong>
      <p>Metrc returned {facilityDiscovery.facility_count} facilit{facilityDiscovery.facility_count === 1 ? "y" : "ies"}. DoobieLogic automatically created {facilityDiscovery.auto_created} and linked {facilityDiscovery.auto_linked}. {facilityDiscovery.needs_confirmation ? `${facilityDiscovery.needs_confirmation} possible existing match${facilityDiscovery.needs_confirmation === 1 ? " needs" : "es need"} one confirmation.` : "No duplicate decisions are waiting."}</p>
      <div className="runtime-state-list">
        {facilityDiscovery.facilities.map(row => <div key={row.license_number} className="connection-result">
          <strong>{row.name} · {row.license_number}</strong>
          {row.doobielogic_facility ? <p className="source-caption">{row.status === "created" ? "Created" : "Connected to"} DoobieLogic facility: {row.doobielogic_facility.name}. Mapping is durable for MA sandbox.</p> : null}
          {row.doobielogic_facility ? <>
            {row.bootstrap_error ? <p className="form-error">{row.bootstrap_error}</p> : null}
            <p role="status">{initialSync[row.license_number] ?? "Initial sync pending. Saved mappings remain available if you leave this page."}</p>
            <button className="secondary" type="button" disabled={pending} onClick={() => { void bootstrapFacilities([row]); }}>Retry initial sync</button>
          </> : null}
          {row.status === "needs_confirmation" ? <>
            <p className="source-caption">{row.message}</p>
            <div className="button-row">
              {(row.suggested_matches ?? []).map(match => <button className="secondary" type="button" disabled={pending} key={match.id} onClick={() => confirm.mutate({ license_number: row.license_number, target_facility_id: match.id, create_new: false })}>Connect to {match.name}</button>)}
              <button className="secondary" type="button" disabled={pending} onClick={() => confirm.mutate({ license_number: row.license_number, create_new: true })}>Create new DoobieLogic facility</button>
            </div>
          </> : null}
        </div>)}
      </div>
      <p className="source-caption">Next bootstrap scope: {facilityDiscovery.bootstrap_resources.join(", ")}.</p>
    </div> : null}
    {provider === "metrc" && provision.data?.facility_discovery_error ? <div className="connection-result">Sandbox user setup succeeded, but automatic facility discovery needs a retry: {provision.data.facility_discovery_error}</div> : null}
    <div className="connection-result">
      <strong>Sandbox runtime</strong>
      <p>Resources: {value.sandbox_resources.join(", ")}. Provider credentials stay encrypted server-side. Normal Metrc API traffic uses the distinct Integrator + User key pair after provisioning.</p>
      {runtime.data?.states.length ? <div className="runtime-state-list">
        {runtime.data.states.map(state => <p className="source-caption" key={state.resource}>
          <strong>{state.resource}</strong> · {state.status} · cursor {state.cursor || "not started"} · seen {state.records_seen} · written {state.records_written}{state.last_error ? ` · ${state.last_error}` : ""}
        </p>)}
      </div> : <p className="source-caption">No sandbox sync has run yet.</p>}
    </div>
    {provision.data ? <div className="connection-result success">{provision.data.message}</div> : null}
    {readiness ? <div className="connection-result success">{readiness.message}</div> : null}
    {confirm.data ? <div className="connection-result success">Metrc facility mapping saved. Refreshing discovery.</div> : null}
    {syncSummary ? <div className="connection-result success">Sandbox sync complete: {syncSummary.records} records, {syncSummary.accepted} accepted, {syncSummary.duplicates} deduplicated, {syncSummary.errors} errors.</div> : null}
    {retry.data ? <div className="connection-result success">Retry pass completed for {retry.data.retried} failed resource{retry.data.retried === 1 ? "" : "s"}.</div> : null}
    {error ? <div className="form-error">{error}</div> : null}
    {value.last_error ? <div className="form-error">Last provider error: {value.last_error}</div> : null}
    {value.last_validated_at ? <p className="source-caption">Last provider validation: {new Date(value.last_validated_at).toLocaleString()}</p> : null}
  </article>;
}
