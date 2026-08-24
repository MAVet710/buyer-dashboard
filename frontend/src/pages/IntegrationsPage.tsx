import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type PropsWithChildren } from "react";
import { KnowledgeLibraryCard } from "../components/KnowledgeLibraryCard";
import { apiGet, apiPost } from "../lib/api";

type Configuration = Record<string, string | boolean>;
type Integration = { configured: boolean; status: string; secret_hint: string; configuration: Configuration; last_validated_at: string | null; last_error: string };
type Payload = { metrc: Integration; doobie: Integration | null; ai_runtime?: Integration | null };

export function IntegrationsPage() {
  const client = useQueryClient();
  const data = useQuery({ queryKey: ["integrations"], queryFn: ({ signal }) => apiGet<Payload>("/api/v1/integrations", signal), retry: false });
  const refresh = () => client.invalidateQueries({ queryKey: ["integrations"] });
  const devMode = Boolean(data.data?.doobie || data.data?.ai_runtime);
  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">Secure connections</div><h1>{devMode ? "AI & METRC Integrations" : "METRC Integrations"}</h1><p>{devMode ? "Level DEV platform AI runtime, grounded knowledge, cloud fallback, and METRC connection settings." : "Connect the METRC account and licensed facility used by your workflows. These settings are stored for your app account and active facility only."}</p></div></div>
    {data.isError ? <div className="state error">{data.error.message}</div> : null}
    {data.data ? <div className="integration-grid">{data.data.ai_runtime ? <AIRuntimeCard value={data.data.ai_runtime} onSaved={refresh}/> : null}{devMode ? <KnowledgeLibraryCard canSeedApproved={true}/> : null}{data.data.doobie ? <DoobieCard value={data.data.doobie} onSaved={refresh}/> : null}<MetrcCard value={data.data.metrc} onSaved={refresh}/></div> : null}
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

function AIRuntimeCard({ value, onSaved }: { value: Integration; onSaved: () => void }) {
  const [form, setForm] = useState({ local_llm_base_url: "", local_llm_model: "", local_embedding_base_url: "", local_embedding_model: "", provider_mode: "local_first", provider_order: "local,gemini,openai,doobie", allow_cloud_fallback: true, api_key: "" });
  useEffect(() => setForm(current => ({
    ...current,
    local_llm_base_url: String(value.configuration.local_llm_base_url ?? ""),
    local_llm_model: String(value.configuration.local_llm_model ?? ""),
    local_embedding_base_url: String(value.configuration.local_embedding_base_url ?? ""),
    local_embedding_model: String(value.configuration.local_embedding_model ?? ""),
    provider_mode: String(value.configuration.provider_mode ?? "local_first"),
    provider_order: String(value.configuration.provider_order ?? "local,gemini,openai,doobie"),
    allow_cloud_fallback: value.configuration.allow_cloud_fallback === undefined ? true : Boolean(value.configuration.allow_cloud_fallback),
  })), [value]);
  const save = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/ai-runtime", { ...form, api_key: form.api_key || null }), onSuccess: () => { setForm(current => ({ ...current, api_key: "" })); onSaved(); } });
  const test = useMutation({ mutationFn: () => apiPost<Integration & { result: { ok: boolean; message: string; local?: Record<string, unknown>; embedding?: Record<string, unknown>; knowledge?: Record<string, unknown> } }>("/api/v1/integrations/ai-runtime/test", {}), onSuccess: onSaved });
  const clear = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/ai-runtime/clear", {}), onSuccess: () => { setForm({ local_llm_base_url: "", local_llm_model: "", local_embedding_base_url: "", local_embedding_model: "", provider_mode: "local_first", provider_order: "local,gemini,openai,doobie", allow_cloud_fallback: true, api_key: "" }); onSaved(); } });
  return <IntegrationCard title="DoobieLogic Local AI Runtime" description="Primary self-hosted OpenAI-compatible inference. Works with Ollama, vLLM, and future compatible model servers; secrets remain server-side." value={value}>
    <div className="form-grid">
      <label className="span-2">Local AI Endpoint<input value={form.local_llm_base_url} placeholder="http://localhost:11434 or private vLLM endpoint" onChange={event => setForm({ ...form, local_llm_base_url: event.target.value })}/></label>
      <label>Local AI Model<input value={form.local_llm_model} placeholder="Configured server model name" onChange={event => setForm({ ...form, local_llm_model: event.target.value })}/></label>
      <label>Local Endpoint API Key<input type="password" autoComplete="off" placeholder={value.configured && value.secret_hint ? `Saved ${value.secret_hint} · leave blank to keep` : "Optional for Ollama; recommended in production"} value={form.api_key} onChange={event => setForm({ ...form, api_key: event.target.value })}/></label>
      <label className="span-2">Embedding Endpoint<input value={form.local_embedding_base_url} placeholder="Leave blank to reuse local AI endpoint" onChange={event => setForm({ ...form, local_embedding_base_url: event.target.value })}/></label>
      <label className="span-2">Embedding Model<input value={form.local_embedding_model} placeholder="e.g. nomic-embed-text / server model name" onChange={event => setForm({ ...form, local_embedding_model: event.target.value })}/></label>
      <label>Provider Mode<select value={form.provider_mode} onChange={event => setForm({ ...form, provider_mode: event.target.value })}><option value="local_first">Local first</option><option value="local_only">Local only</option></select></label>
      <label>Provider Order<input value={form.provider_order} onChange={event => setForm({ ...form, provider_order: event.target.value })}/></label>
      <label className="span-2"><input type="checkbox" checked={form.allow_cloud_fallback} onChange={event => setForm({ ...form, allow_cloud_fallback: event.target.checked })}/> Allow cloud fallback when objective routing/validation requires it</label>
    </div>
    <Actions save={() => save.mutate()} test={() => test.mutate()} clear={() => clear.mutate()} disabled={!form.local_llm_base_url || !form.local_llm_model} pending={save.isPending || test.isPending || clear.isPending}/>
    {save.isError || test.isError || clear.isError ? <div className="form-error">{save.error?.message || test.error?.message || clear.error?.message}</div> : null}
    {test.data ? <div className={test.data.result.ok ? "connection-result success" : "connection-result error"}>{test.data.result.message}<br/>Embedding: {String(test.data.result.embedding?.reachable ? "reachable" : test.data.result.embedding?.configured ? "configured but unavailable" : "lexical fallback")} · Knowledge index: {String(test.data.result.knowledge?.document_count ?? 0)} document(s)</div> : null}
  </IntegrationCard>;
}

function DoobieCard({ value, onSaved }: { value: Integration; onSaved: () => void }) {
  const [form, setForm] = useState({ base_url: "", api_key: "" });
  useEffect(() => setForm(current => ({ ...current, base_url: String(value.configuration.base_url ?? "") })), [value]);
  const save = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/doobie", { base_url: form.base_url, api_key: form.api_key || null }), onSuccess: () => { setForm({ ...form, api_key: "" }); onSaved(); } });
  const test = useMutation({ mutationFn: () => apiPost<Integration & { result: { ok: boolean; message: string } }>("/api/v1/integrations/doobie/test", {}), onSuccess: onSaved });
  const clear = useMutation({ mutationFn: () => apiPost("/api/v1/integrations/doobie/clear", {}), onSuccess: () => { setForm({ base_url: "", api_key: "" }); onSaved(); } });
  return <IntegrationCard title="Doobie" description="Optional Doobie cloud escalation provider. It is not required for local development or normal deterministic workflows." value={value}>
    <div className="form-grid">
      <label className="span-2">Doobie Base URL<input value={form.base_url} onChange={event => setForm({ ...form, base_url: event.target.value })}/></label>
      <label className="span-2">Doobie Service API Key<input type="password" autoComplete="off" placeholder={value.configured ? `Saved ${value.secret_hint} · leave blank to keep` : "Enter API key"} value={form.api_key} onChange={event => setForm({ ...form, api_key: event.target.value })}/></label>
    </div>
    <Actions save={() => save.mutate()} test={() => test.mutate()} clear={() => clear.mutate()} disabled={!form.base_url || (!value.configured && !form.api_key)} pending={save.isPending || test.isPending || clear.isPending}/>
    {save.isError || test.isError || clear.isError ? <div className="form-error">{save.error?.message || test.error?.message || clear.error?.message}</div> : null}
    {test.data ? <div className={test.data.result.ok ? "connection-result success" : "connection-result error"}>{test.data.result.message}</div> : null}
  </IntegrationCard>;
}

function IntegrationCard({ title, description, value, children }: PropsWithChildren<{ title: string; description: string; value: Integration }>) {
  return <section className="inventory-panel integration-card"><header><div><h2>{title}</h2><p>{description}</p></div><span className={`badge ${value.status === "connected" ? "production-ready" : value.status === "failed" ? "hold" : ""}`}>{value.status.replaceAll("_", " ")}</span></header>{children}<footer><span>Saved key: {value.secret_hint || "(not set)"}</span><span>Status: {value.status}</span><span>Last validated: {value.last_validated_at ? new Date(value.last_validated_at).toLocaleString() : "never"}</span>{value.last_error ? <span className="form-error">{value.last_error}</span> : null}</footer></section>;
}

function Actions({ save, test, clear, disabled, pending }: { save: () => void; test: () => void; clear: () => void; disabled: boolean; pending: boolean }) {
  return <div className="audit-actions"><button className="secondary" disabled={pending} onClick={test}>Test Connection</button><button className="primary" disabled={disabled || pending} onClick={save}>Save</button><button className="secondary" disabled={pending} onClick={clear}>Clear / Reset</button></div>;
}
