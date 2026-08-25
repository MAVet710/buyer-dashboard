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
  future_use: string;
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
  organization_id: string;
  facility_id: string;
  scope: "facility";
  providers: Record<ProviderKey, Connection>;
};
type TestResponse = Connection & { result: { ok: boolean; configuration_ready: boolean; connected: boolean; verified: boolean; environment: string; message: string } };

type Field = { key: string; label: string; placeholder?: string };

const FIELDS: Record<ProviderKey, Field[]> = {
  metrc: [
    { key: "state", label: "State / jurisdiction", placeholder: "MA" },
    { key: "license_number", label: "Sandbox license / facility" },
    { key: "base_url", label: "Sandbox API base URL", placeholder: "Optional until provider adapter is enabled" },
    { key: "notes", label: "Connection notes" },
  ],
  dutchie: [
    { key: "location_id", label: "Sandbox location ID" },
    { key: "account_id", label: "Sandbox account ID" },
    { key: "client_id", label: "Developer client ID" },
    { key: "base_url", label: "Sandbox API base URL", placeholder: "Optional until provider adapter is enabled" },
    { key: "notes", label: "Connection notes" },
  ],
  biotrack: [
    { key: "state", label: "State / jurisdiction" },
    { key: "license_number", label: "Sandbox license / facility" },
    { key: "username", label: "Sandbox username" },
    { key: "base_url", label: "Sandbox API base URL", placeholder: "Optional until provider adapter is enabled" },
    { key: "notes", label: "Connection notes" },
  ],
  quickbooks: [
    { key: "client_id", label: "Sandbox client ID" },
    { key: "realm_id", label: "Sandbox company / realm ID", placeholder: "Can be added after OAuth authorization" },
    { key: "redirect_uri", label: "OAuth redirect URI" },
    { key: "base_url", label: "Sandbox API base URL", placeholder: "Optional until OAuth adapter is enabled" },
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
        <p>Configure isolated developer credentials now so METRC, Dutchie, BioTrack, and QuickBooks adapters can use the same facility-scoped connection records as Phases 1–7 come online.</p>
      </div>
      <span className="status-pill warning">SANDBOX ONLY</span>
    </div>
    <div className="info-banner">
      Production credentials are disabled here. Sandbox secrets are encrypted server-side and are never returned to the browser. Organization <strong>{data.data.organization_id}</strong> · Facility <strong>{data.data.facility_id}</strong>.
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

  const refresh = () => client.invalidateQueries({ queryKey: ["sandbox-provider-connections"] });
  const save = useMutation({
    mutationFn: () => apiPost<Connection>(`/api/v1/integrations/sandbox/${provider}`, { configuration, secret: secret || null }),
    onSuccess: async () => { setSecret(""); await refresh(); },
  });
  const test = useMutation({
    mutationFn: () => apiPost<TestResponse>(`/api/v1/integrations/sandbox/${provider}/test`, {}),
    onSuccess: refresh,
  });
  const clear = useMutation({
    mutationFn: () => apiPost<Connection>(`/api/v1/integrations/sandbox/${provider}/clear`, {}),
    onSuccess: async () => { setConfiguration({}); setSecret(""); await refresh(); },
  });
  const missing = value.required_fields.some(field => !String(configuration[field] ?? "").trim());
  const pending = save.isPending || test.isPending || clear.isPending;
  const error = save.error?.message || test.error?.message || clear.error?.message;
  const readiness = test.data?.result;

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
    <p className="source-caption">Environment: sandbox · Scope: active facility · Production credential use: disabled</p>
    <div className="button-row">
      <button className="primary" type="button" disabled={pending || missing || (!value.configured && !secret.trim())} onClick={() => save.mutate()}>Save sandbox connection</button>
      <button className="secondary" type="button" disabled={pending || !value.configured} onClick={() => test.mutate()}>Test readiness</button>
      <button className="secondary" type="button" disabled={pending || !value.configured} onClick={() => clear.mutate()}>Clear</button>
    </div>
    {readiness ? <div className="connection-result success">{readiness.message}</div> : null}
    {error ? <div className="form-error">{error}</div> : null}
    {value.last_error ? <div className="form-error">Last provider error: {value.last_error}</div> : null}
    {value.last_validated_at ? <p className="source-caption">Last provider validation: {new Date(value.last_validated_at).toLocaleString()}</p> : null}
  </article>;
}
