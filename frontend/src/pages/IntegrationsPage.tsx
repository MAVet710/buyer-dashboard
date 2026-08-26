import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type PropsWithChildren } from "react";
import { KnowledgeLibraryCard } from "../components/KnowledgeLibraryCard";
import { apiGet, apiPost } from "../lib/api";

type Configuration = Record<string, string | boolean>;
type Integration = { configured: boolean; status: string; secret_hint: string; configuration: Configuration; last_validated_at: string | null; last_error: string };
type Payload = { metrc: Integration; doobie: Integration | null; ai_runtime?: Integration | null; spacemail?: Integration | null };
type NativePayload = { metrc: Integration; biotrack: Integration; quickbooks: Integration; activation_rules: Record<string, string>; quickbooks_sync?: { managed_entities: string[]; manual_mapping_required: string[]; idempotent: boolean } };

export function IntegrationsPage() {
  const client = useQueryClient();
  const data = useQuery({ queryKey: ["integrations"], queryFn: ({ signal }) => apiGet<Payload>("/api/v1/integrations", signal), retry: false });
  const native = useQuery({ queryKey: ["native-integrations"], queryFn: ({ signal }) => apiGet<NativePayload>("/api/v1/native-integrations", signal), retry: false });
  const refresh = () => { client.invalidateQueries({ queryKey: ["integrations"] }); client.invalidateQueries({ queryKey: ["native-integrations"] }); };
  const devMode = Boolean(data.data?.doobie || data.data?.ai_runtime || data.data?.spacemail);
  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">Secure connections</div><h1>{devMode ? "AI & METRC Integrations" : "METRC Integrations"}</h1><p>{devMode ? "Level DEV settings for DoobieLogic AI, Spacemail onboarding, grounded knowledge, cloud fallback, and METRC connections." : "Connect the METRC account and licensed facility used by your workflows. These settings are stored for your app account and active facility only."}</p></div></div>
    {data.isError ? <div className="state error">{data.error.message}</div> : null}
    {data.data ? <div className="integration-grid">{data.data.spacemail ? <SpacemailCard value={data.data.spacemail} onSaved={refresh}/> : null}{data.data.ai_runtime ? <AIRuntimeCard value={data.data.ai_runtime} onSaved={refresh}/> : null}{devMode ? <KnowledgeLibraryCard canSeedApproved={true}/> : null}{data.data.doobie ? <DoobieCard value={data.data.doobie} onSaved={refresh}/> : null}<MetrcCard value={data.data.metrc} onSaved={refresh}/></div> : null}
    <div className="page-heading"><div><div className="eyebrow">Native operations</div><h2>State & Accounting Connections</h2><p>Facility-scoped production connectors. A saved credential is not treated as live until the provider-specific validation succeeds.</p></div></div>
    {native.isError ? <div className="state error">{native.error.message}</div> : null}
    {native.data ? <div className="integration-grid"><BioTrackCard value={native.data.biotrack} onSaved={refresh}/><QuickBooksCard value={native.data.quickbooks} onSaved={refresh}/></div> : null}
  </div>;
}

function MetrcCard({ value, onSaved }: { value: Integration; onSaved: () => void }) {
  const [form, setForm] = useState({ state: "", license_number: "", api_key: "" });
  useEffect(() => setForm(current => ({ ...current, state: String(value.configuration.state ?? ""), license_number: String(value.configuration.license_number ?? "") })), [value]);
  const save = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/metrc", { state: form.state, license_number: form.license_number, api_key: form.api_key || null }), onSuccess: () => { setForm({ ...form, api_key: "" }); onSaved(); } });
  const test = useMutation({ mutationFn: () => apiPost<Integration & { result: { ok: boolean; message: string } }>("/api/v1/integrations/metrc/test", {}), onSuccess: onSaved });
  const clear = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/metrc/clear", {}), onSuccess: () => { setForm({ state: "", license_number: "", api_key: "" }); onSaved(); } });
  return <IntegrationCard title="METRC" description="The app performs a read-only facility check. Your METRC user key is masked after it is saved." value={value}>
    <div className="form-grid">
      <label>METRC User API Key<input type="password" autoComplete="off" placeholder={value.configured ? `Saved ${value.secret_hint} · leave blank to keep` : "Enter API key"} value={form.api_key} onChange={event => setForm({ ...form, api_key: event.target.value })}/></label>
      <label>METRC State<input value={form.state} placeholder="e.g., CA, MA, MI, or https://api-ca.metrc.com" onChange={event => setForm({ ...form, state: event.target.value })}/></label>
      <label className="span-2">METRC License / Facility<input value={form.license_number} onChange={event => setForm({ ...form, license_number: event.target.value })}/></label>
    </div>
    <Actions save={() => save.mutate()} test={() => test.mutate()} clear={() => clear.mutate()} disabled={!form.state || !form.license_number || (!value.configured && !form.api_key)} pending={save.isPending || test.isPending || clear.isPending}/>
    {save.isError || test.isError || clear.isError ? <div className="form-error">{save.error?.message || test.error?.message || clear.error?.message}</div> : null}
    {test.data ? <div className={test.data.result.ok ? "connection-result success" : "connection-result error"}>{test.data.result.message}</div> : null}
  </IntegrationCard>;
}

function BioTrackCard({ value, onSaved }: { value: Integration; onSaved: () => void }) {
  const [form, setForm] = useState({ base_url: "", license_number: "", username: "", password: "", environment: "sandbox", login_path: "/v1/login", confirm_production: false });
  useEffect(() => setForm(current => ({ ...current, base_url: String(value.configuration.base_url ?? ""), license_number: String(value.configuration.license_number ?? ""), environment: String(value.configuration.environment ?? "sandbox"), login_path: String(value.configuration.login_path ?? "/v1/login"), confirm_production: false })), [value]);
  const save = useMutation({ mutationFn: () => apiPost("/api/v1/native-integrations/biotrack", { ...form, username: form.username || null, password: form.password || null }), onSuccess: () => { setForm(current => ({ ...current, username: "", password: "", confirm_production: false })); onSaved(); } });
  const test = useMutation({ mutationFn: () => apiPost<Integration & { result: { ok: boolean; message: string; training?: boolean } }>("/api/v1/native-integrations/biotrack/test", {}), onSuccess: onSaved });
  const clear = useMutation({ mutationFn: () => apiPost("/api/v1/native-integrations/biotrack/clear", {}), onSuccess: () => { setForm({ base_url: "", license_number: "", username: "", password: "", environment: "sandbox", login_path: "/v1/login", confirm_production: false }); onSaved(); } });
  const firstSaveMissing = !value.configured && (!form.username || !form.password);
  const productionUnconfirmed = form.environment === "production" && !form.confirm_production;
  return <IntegrationCard title="BioTrack" description="State-contract connector for BioTrack facilities. Sandbox/training and production are explicit and never inferred." value={value}>
    <div className="form-grid">
      <label className="span-2">BioTrack API Base URL<input value={form.base_url} placeholder="State-approved HTTPS API endpoint" onChange={event => setForm({ ...form, base_url: event.target.value })}/></label>
      <label>License / Facility<input value={form.license_number} onChange={event => setForm({ ...form, license_number: event.target.value })}/></label>
      <label>Environment<select value={form.environment} onChange={event => setForm({ ...form, environment: event.target.value, confirm_production: false })}><option value="sandbox">Sandbox / training</option><option value="production">Production</option></select></label>
      <label>Username<input autoComplete="off" placeholder={value.configured ? "Saved · leave blank to keep" : "Provider username"} value={form.username} onChange={event => setForm({ ...form, username: event.target.value })}/></label>
      <label>Password<input type="password" autoComplete="new-password" placeholder={value.configured ? "Saved · leave blank to keep" : "Provider password"} value={form.password} onChange={event => setForm({ ...form, password: event.target.value })}/></label>
      <label className="span-2">Login Path<input value={form.login_path} onChange={event => setForm({ ...form, login_path: event.target.value })}/></label>
      {form.environment === "production" ? <label className="span-2"><input type="checkbox" checked={form.confirm_production} onChange={event => setForm({ ...form, confirm_production: event.target.checked })}/> I confirm this facility has approved BioTrack production API access.</label> : null}
    </div>
    <Actions save={() => save.mutate()} test={() => test.mutate()} clear={() => clear.mutate()} disabled={!form.base_url || !form.license_number || firstSaveMissing || productionUnconfirmed} pending={save.isPending || test.isPending || clear.isPending}/>
    {save.isError || test.isError || clear.isError ? <div className="form-error">{save.error?.message || test.error?.message || clear.error?.message}</div> : null}
    {test.data ? <div className={test.data.result.ok ? "connection-result success" : "connection-result error"}>{test.data.result.message}</div> : null}
  </IntegrationCard>;
}

function QuickBooksCard({ value, onSaved }: { value: Integration; onSaved: () => void }) {
  const defaultTokenUrl = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer";
  const [form, setForm] = useState({ realm_id: "", environment: "sandbox", client_id: "", client_secret: "", refresh_token: "", api_base_url: "", token_url: defaultTokenUrl, confirm_production: false });
  useEffect(() => setForm(current => ({ ...current, realm_id: String(value.configuration.realm_id ?? ""), environment: String(value.configuration.environment ?? "sandbox"), api_base_url: String(value.configuration.api_base_url ?? ""), token_url: String(value.configuration.token_url ?? defaultTokenUrl), confirm_production: false })), [value]);
  const save = useMutation({ mutationFn: () => apiPost("/api/v1/native-integrations/quickbooks", { ...form, client_id: form.client_id || null, client_secret: form.client_secret || null, refresh_token: form.refresh_token || null }), onSuccess: () => { setForm(current => ({ ...current, client_id: "", client_secret: "", refresh_token: "", confirm_production: false })); onSaved(); } });
  const test = useMutation({ mutationFn: () => apiPost<Integration & { result: { ok: boolean; message: string; company?: { company_name?: string } } }>("/api/v1/native-integrations/quickbooks/test", {}), onSuccess: onSaved });
  const clear = useMutation({ mutationFn: () => apiPost("/api/v1/native-integrations/quickbooks/clear", {}), onSuccess: () => { setForm({ realm_id: "", environment: "sandbox", client_id: "", client_secret: "", refresh_token: "", api_base_url: "", token_url: defaultTokenUrl, confirm_production: false }); onSaved(); } });
  const firstSaveMissing = !value.configured && (!form.client_id || !form.client_secret || !form.refresh_token);
  const productionUnconfirmed = form.environment === "production" && !form.confirm_production;
  return <IntegrationCard title="QuickBooks Online" description="OAuth company connection for idempotent customer and invoice sync. Product lines require explicit QuickBooks Item mappings before invoice posting." value={value}>
    <div className="form-grid">
      <label>Company Realm ID<input value={form.realm_id} onChange={event => setForm({ ...form, realm_id: event.target.value })}/></label>
      <label>Environment<select value={form.environment} onChange={event => setForm({ ...form, environment: event.target.value, confirm_production: false })}><option value="sandbox">Sandbox</option><option value="production">Production</option></select></label>
      <label>Client ID<input autoComplete="off" placeholder={value.configured ? "Saved · leave blank to keep" : "Intuit client ID"} value={form.client_id} onChange={event => setForm({ ...form, client_id: event.target.value })}/></label>
      <label>Client Secret<input type="password" autoComplete="new-password" placeholder={value.configured ? "Saved · leave blank to keep" : "Intuit client secret"} value={form.client_secret} onChange={event => setForm({ ...form, client_secret: event.target.value })}/></label>
      <label className="span-2">Refresh Token<input type="password" autoComplete="new-password" placeholder={value.configured ? "Saved · leave blank to keep" : "OAuth refresh token"} value={form.refresh_token} onChange={event => setForm({ ...form, refresh_token: event.target.value })}/></label>
      <label className="span-2">API Base URL Override<input value={form.api_base_url} placeholder="Optional; normal sandbox/production endpoints are selected automatically" onChange={event => setForm({ ...form, api_base_url: event.target.value })}/></label>
      {form.environment === "production" ? <label className="span-2"><input type="checkbox" checked={form.confirm_production} onChange={event => setForm({ ...form, confirm_production: event.target.checked })}/> I confirm this is the production QuickBooks company connection.</label> : null}
    </div>
    <p className="source-caption">Refresh-token rotation stays encrypted server-side. Customer and invoice writes are blocked until this connection validates successfully.</p>
    <Actions save={() => save.mutate()} test={() => test.mutate()} clear={() => clear.mutate()} disabled={!form.realm_id || firstSaveMissing || productionUnconfirmed} pending={save.isPending || test.isPending || clear.isPending}/>
    {save.isError || test.isError || clear.isError ? <div className="form-error">{save.error?.message || test.error?.message || clear.error?.message}</div> : null}
    {test.data ? <div className={test.data.result.ok ? "connection-result success" : "connection-result error"}>{test.data.result.message}</div> : null}
  </IntegrationCard>;
}

function SpacemailCard({ value, onSaved }: { value: Integration; onSaved: () => void }) {
  const defaults = { smtp_username: "nelson@doobielogic.io", from_email: "support@doobielogic.io", from_name: "DoobieLogic Support", support_email: "support@doobielogic.io", help_email: "help@doobielogic.io", info_email: "info@doobielogic.io", welcome_email_enabled: true, mailbox_password: "" };
  const [form, setForm] = useState(defaults);
  useEffect(() => setForm(current => ({ ...current, smtp_username: String(value.configuration.smtp_username ?? defaults.smtp_username), from_email: String(value.configuration.from_email ?? defaults.from_email), from_name: String(value.configuration.from_name ?? defaults.from_name), support_email: String(value.configuration.support_email ?? defaults.support_email), help_email: String(value.configuration.help_email ?? defaults.help_email), info_email: String(value.configuration.info_email ?? defaults.info_email), welcome_email_enabled: value.configuration.welcome_email_enabled === undefined ? true : Boolean(value.configuration.welcome_email_enabled) })), [value]);
  const save = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/spacemail", { ...form, mailbox_password: form.mailbox_password || null }), onSuccess: () => { setForm(current => ({ ...current, mailbox_password: "" })); onSaved(); } });
  const test = useMutation({ mutationFn: () => apiPost<Integration & { result: { ok: boolean; message: string } }>("/api/v1/integrations/spacemail/test", {}), onSuccess: onSaved });
  const clear = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/spacemail/clear", {}), onSuccess: () => { setForm(defaults); onSaved(); } });
  const missing = !form.smtp_username || !form.from_email || !form.from_name || !form.support_email || !form.help_email || !form.info_email;
  return <IntegrationCard title="Spacemail Onboarding & Support" description="Secure SMTP for DoobieLogic welcome emails. The primary mailbox authenticates to Spacemail; outgoing onboarding mail uses the support alias. The mailbox password is encrypted and never returned to the browser." value={value}>
    <div className="form-grid"><label>Primary mailbox<input value={form.smtp_username} onChange={event => setForm({ ...form, smtp_username: event.target.value })}/></label><label>Mailbox password<input type="password" autoComplete="new-password" placeholder={value.configured ? `Saved ${value.secret_hint} · leave blank to keep` : "Enter the Spacemail mailbox password"} value={form.mailbox_password} onChange={event => setForm({ ...form, mailbox_password: event.target.value })}/></label><label>Welcome email sender<input value={form.from_email} onChange={event => setForm({ ...form, from_email: event.target.value })}/></label><label>Sender name<input value={form.from_name} onChange={event => setForm({ ...form, from_name: event.target.value })}/></label><label>Support alias<input value={form.support_email} onChange={event => setForm({ ...form, support_email: event.target.value })}/></label><label>Help alias<input value={form.help_email} onChange={event => setForm({ ...form, help_email: event.target.value })}/></label><label className="span-2">Info alias<input value={form.info_email} onChange={event => setForm({ ...form, info_email: event.target.value })}/></label><label className="span-2"><input type="checkbox" checked={form.welcome_email_enabled} onChange={event => setForm({ ...form, welcome_email_enabled: event.target.checked })}/> Send branded welcome emails when a new user has an email address</label></div>
    <p className="source-caption">Connection test authenticates to mail.spacemail.com over encrypted SMTP without sending a message.</p><Actions save={() => save.mutate()} test={() => test.mutate()} clear={() => clear.mutate()} disabled={missing || (!value.configured && !form.mailbox_password)} pending={save.isPending || test.isPending || clear.isPending}/>{save.isError || test.isError || clear.isError ? <div className="form-error">{save.error?.message || test.error?.message || clear.error?.message}</div> : null}{test.data ? <div className={test.data.result.ok ? "connection-result success" : "connection-result error"}>{test.data.result.message}</div> : null}
  </IntegrationCard>;
}

function AIRuntimeCard({ value, onSaved }: { value: Integration; onSaved: () => void }) {
  const [form, setForm] = useState({ local_llm_base_url: "", local_llm_model: "", local_embedding_base_url: "", local_embedding_model: "", provider_mode: "local_first", provider_order: "local,gemini,openai,doobie", allow_cloud_fallback: true, api_key: "" });
  useEffect(() => setForm(current => ({ ...current, local_llm_base_url: String(value.configuration.local_llm_base_url ?? ""), local_llm_model: String(value.configuration.local_llm_model ?? ""), local_embedding_base_url: String(value.configuration.local_embedding_base_url ?? ""), local_embedding_model: String(value.configuration.local_embedding_model ?? ""), provider_mode: String(value.configuration.provider_mode ?? "local_first"), provider_order: String(value.configuration.provider_order ?? "local,gemini,openai,doobie"), allow_cloud_fallback: value.configuration.allow_cloud_fallback === undefined ? true : Boolean(value.configuration.allow_cloud_fallback) })), [value]);
  const save = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/ai-runtime", { ...form, api_key: form.api_key || null }), onSuccess: () => { setForm(current => ({ ...current, api_key: "" })); onSaved(); } });
  const test = useMutation({ mutationFn: () => apiPost<Integration & { result: { ok: boolean; message: string; local?: Record<string, unknown>; embedding?: Record<string, unknown>; knowledge?: Record<string, unknown> } }>("/api/v1/integrations/ai-runtime/test", {}), onSuccess: onSaved });
  const clear = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/ai-runtime/clear", {}), onSuccess: () => { setForm({ local_llm_base_url: "", local_llm_model: "", local_embedding_base_url: "", local_embedding_model: "", provider_mode: "local_first", provider_order: "local,gemini,openai,doobie", allow_cloud_fallback: true, api_key: "" }); onSaved(); } });
  return <IntegrationCard title="DoobieLogic Local AI Runtime" description="Primary self-hosted OpenAI-compatible inference. Works with Ollama, vLLM, and future compatible model servers; secrets remain server-side." value={value}><div className="form-grid"><label className="span-2">Local AI Endpoint<input value={form.local_llm_base_url} placeholder="http://localhost:11434 or private vLLM endpoint" onChange={event => setForm({ ...form, local_llm_base_url: event.target.value })}/></label><label>Local AI Model<input value={form.local_llm_model} placeholder="Configured server model name" onChange={event => setForm({ ...form, local_llm_model: event.target.value })}/></label><label>Local Endpoint API Key<input type="password" autoComplete="off" placeholder={value.configured && value.secret_hint ? `Saved ${value.secret_hint} · leave blank to keep` : "Optional for Ollama; recommended in production"} value={form.api_key} onChange={event => setForm({ ...form, api_key: event.target.value })}/></label><label className="span-2">Embedding Endpoint<input value={form.local_embedding_base_url} placeholder="Leave blank to reuse local AI endpoint" onChange={event => setForm({ ...form, local_embedding_base_url: event.target.value })}/></label><label className="span-2">Embedding Model<input value={form.local_embedding_model} placeholder="e.g. nomic-embed-text / server model name" onChange={event => setForm({ ...form, local_embedding_model: event.target.value })}/></label><label>Provider Mode<select value={form.provider_mode} onChange={event => setForm({ ...form, provider_mode: event.target.value })}><option value="local_first">Local first</option><option value="local_only">Local only</option></select></label><label>Provider Order<input value={form.provider_order} onChange={event => setForm({ ...form, provider_order: event.target.value })}/></label><label className="span-2"><input type="checkbox" checked={form.allow_cloud_fallback} onChange={event => setForm({ ...form, allow_cloud_fallback: event.target.checked })}/> Allow cloud fallback when objective routing/validation requires it</label></div><Actions save={() => save.mutate()} test={() => test.mutate()} clear={() => clear.mutate()} disabled={!form.local_llm_base_url || !form.local_llm_model} pending={save.isPending || test.isPending || clear.isPending}/>{save.isError || test.isError || clear.isError ? <div className="form-error">{save.error?.message || test.error?.message || clear.error?.message}</div> : null}{test.data ? <div className={test.data.result.ok ? "connection-result success" : "connection-result error"}>{test.data.result.message}<br/>Embedding: {String(test.data.result.embedding?.reachable ? "reachable" : test.data.result.embedding?.configured ? "configured but unavailable" : "lexical fallback")} · Knowledge index: {String(test.data.result.knowledge?.document_count ?? 0)} document(s)</div> : null}</IntegrationCard>;
}

function DoobieCard({ value, onSaved }: { value: Integration; onSaved: () => void }) {
  const [form, setForm] = useState({ base_url: "", api_key: "" });
  useEffect(() => setForm(current => ({ ...current, base_url: String(value.configuration.base_url ?? "") })), [value]);
  const save = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/doobie", { base_url: form.base_url, api_key: form.api_key || null }), onSuccess: () => { setForm({ ...form, api_key: "" }); onSaved(); } });
  const test = useMutation({ mutationFn: () => apiPost<Integration & { result: { ok: boolean; message: string } }>("/api/v1/integrations/doobie/test", {}), onSuccess: onSaved });
  const clear = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/doobie/clear", {}), onSuccess: () => { setForm({ base_url: "", api_key: "" }); onSaved(); } });
  return <IntegrationCard title="Doobie" description="Optional Doobie cloud escalation provider. It is not required for local development or normal deterministic workflows." value={value}><div className="form-grid"><label className="span-2">Doobie Base URL<input value={form.base_url} onChange={event => setForm({ ...form, base_url: event.target.value })}/></label><label className="span-2">Doobie Service API Key<input type="password" autoComplete="off" placeholder={value.configured ? `Saved ${value.secret_hint} · leave blank to keep` : "Enter API key"} value={form.api_key} onChange={event => setForm({ ...form, api_key: event.target.value })}/></label></div><Actions save={() => save.mutate()} test={() => test.mutate()} clear={() => clear.mutate()} disabled={!form.base_url || (!value.configured && !form.api_key)} pending={save.isPending || test.isPending || clear.isPending}/>{save.isError || test.isError || clear.isError ? <div className="form-error">{save.error?.message || test.error?.message || clear.error?.message}</div> : null}{test.data ? <div className={test.data.result.ok ? "connection-result success" : "connection-result error"}>{test.data.result.message}</div> : null}</IntegrationCard>;
}

function IntegrationCard({ title, description, value, children }: PropsWithChildren<{ title: string; description: string; value: Integration }>) {
  return <section className="inventory-panel integration-card"><header><div><h2>{title}</h2><p>{description}</p></div><span className={`badge ${value.status === "connected" ? "production-ready" : value.status === "failed" ? "hold" : ""}`}>{value.status.replaceAll("_", " ")}</span></header>{children}<footer><span>Saved key: {value.secret_hint || "(not set)"}</span><span>Status: {value.status}</span><span>Last validated: {value.last_validated_at ? new Date(value.last_validated_at).toLocaleString() : "never"}</span>{value.last_error ? <span className="form-error">{value.last_error}</span> : null}</footer></section>;
}

function Actions({ save, test, clear, disabled, pending }: { save: () => void; test: () => void; clear: () => void; disabled: boolean; pending: boolean }) {
  return <div className="audit-actions"><button className="secondary" disabled={pending} onClick={test}>Test Connection</button><button className="primary" disabled={disabled || pending} onClick={save}>Save</button><button className="secondary" disabled={pending} onClick={clear}>Clear / Reset</button></div>;
}
