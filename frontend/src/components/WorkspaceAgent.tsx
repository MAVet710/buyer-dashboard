import { BrainCircuit, Send, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";
import "./workspace-agent.css";

type AgentProfile = {
  key: string;
  name: string;
  role: string;
  description: string;
  focus: string[];
  suggested_questions: string[];
  compliance_grounded_only: boolean;
};

type ProviderStatus = {
  provider: string;
  model?: string;
  configured: boolean;
  status: string;
  local?: boolean;
  fallback_configured?: boolean;
  cloud_fallback_enabled?: boolean;
  message?: string;
};

type LearningHealth = { ok?: boolean; active_learnings?: number; agents_with_learnings?: number };
type AgentDirectory = {
  active_agent?: AgentProfile;
  agents?: AgentProfile[];
  provider?: ProviderStatus;
  learning?: LearningHealth;
  workspace?: { app_mode: string; section: string; organization_id?: string; facility_id?: string };
};

type ChatMessage = { role: "user" | "assistant"; content: string };
type AgentSource = {
  title?: string;
  source?: string;
  source_type?: string;
  authority_level?: number;
  page_or_section?: string;
  effective_date?: string;
  updated_at?: string;
  url?: string;
  score?: number;
  precedence_score?: number;
  precedence_status?: string;
};
type LearnedPattern = { type?: string; source?: string; summary?: string; sample_size?: number; confidence?: number; last_observed_at?: string };
type LearningContext = {
  enabled?: boolean;
  pattern_count?: number;
  approved_correction_count?: number;
  patterns?: LearnedPattern[];
  mode?: string;
};
type AgentRun = {
  answer: string;
  summary?: string;
  priority?: string;
  confidence?: number;
  grounding?: string;
  provider: string;
  model?: string;
  local?: boolean;
  fallback_used?: boolean;
  fallback_reason?: string;
  agent: AgentProfile;
  datasets: string[];
  tool_calls?: string[];
  data_freshness?: Record<string, string>;
  learning?: LearningContext;
  read_only: boolean;
  sources?: AgentSource[];
  recommendations?: string[];
  warnings?: string[];
  missing_data?: string[];
  request_id?: string;
};

type Props = {
  activePage: string;
  operation: "Retail Ops" | "Production Ops";
  onNavigate: (page: string) => void;
};

function storageKey(scope: string) { return `workspace-agent-history-${scope}`; }
function readHistory(scope: string): ChatMessage[] {
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey(scope)) ?? "[]");
    return Array.isArray(value) ? value.filter(item => item && (item.role === "user" || item.role === "assistant") && typeof item.content === "string").slice(-20) : [];
  } catch {
    return [];
  }
}
function saveHistory(scope: string, history: ChatMessage[]) {
  try { sessionStorage.setItem(storageKey(scope), JSON.stringify(history.slice(-20))); } catch { /* storage can be unavailable */ }
}
function precedenceLabel(value?: string) {
  if (!value || value === "normal") return "";
  return value.replaceAll("_", " ");
}

export function WorkspaceAgent({ activePage, operation, onNavigate }: Props) {
  const [open, setOpen] = useState(false);
  const [agentKey, setAgentKey] = useState("");
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [lastRun, setLastRun] = useState<AgentRun | null>(null);

  const params = useMemo(() => new URLSearchParams({ app_mode: operation, section: activePage }), [activePage, operation]);
  const directory = useQuery({
    queryKey: ["workspace-ai-agents", operation, activePage],
    queryFn: ({ signal }) => apiGet<AgentDirectory>(`/api/v1/ai-agents?${params}`, signal),
    staleTime: 60_000,
  });
  const agents = directory.data?.agents ?? [];
  const activeAgentKey = directory.data?.active_agent?.key ?? "";
  const effectiveKey = agentKey || activeAgentKey || "ops";
  const selected = agents.find(row => row.key === effectiveKey) ?? directory.data?.active_agent;
  const organizationId = directory.data?.workspace?.organization_id ?? "unknown-org";
  const facilityId = directory.data?.workspace?.facility_id ?? "unknown-facility";
  const historyScope = `${organizationId}|${facilityId}|${effectiveKey}`;

  useEffect(() => {
    if (!activeAgentKey) return;
    setAgentKey(activeAgentKey);
  }, [activeAgentKey, activePage, operation]);

  useEffect(() => {
    if (!effectiveKey || organizationId === "unknown-org" || facilityId === "unknown-facility") return;
    setHistory(readHistory(historyScope));
    setLastRun(null);
  }, [effectiveKey, organizationId, facilityId, historyScope]);

  useEffect(() => {
    if (!selected || question) return;
    setQuestion(selected.suggested_questions[0] ?? "What needs my attention in this workspace?");
  }, [question, selected]);

  const run = useMutation({
    mutationFn: () => apiPost<AgentRun>("/api/v1/ai-agents/run", {
      agent_key: effectiveKey,
      app_mode: operation,
      section: activePage,
      question: question.trim(),
      history,
    }),
    onSuccess: result => {
      const next: ChatMessage[] = [
        ...history,
        { role: "user" as const, content: question.trim() },
        { role: "assistant" as const, content: result.answer },
      ].slice(-20);
      setHistory(next);
      saveHistory(historyScope, next);
      setLastRun(result);
      setQuestion("");
    },
  });

  const clear = () => {
    setHistory([]);
    setLastRun(null);
    saveHistory(historyScope, []);
  };
  const provider = directory.data?.provider;
  const sourceList = lastRun?.sources ?? [];
  const freshness = Object.entries(lastRun?.data_freshness ?? {});
  const learnedPatterns = lastRun?.learning?.patterns ?? [];
  const learningHealth = directory.data?.learning;

  return <>
    <button className="workspace-agent-launch" type="button" onClick={() => setOpen(true)} aria-label="Open DoobieLogic AI agents">
      <BrainCircuit size={18}/><span>{selected?.name ?? "AI Agents"}</span><i className={provider?.configured ? "is-connected" : ""}/>
    </button>
    {open ? <div className="workspace-agent-backdrop" onClick={() => setOpen(false)} aria-hidden="true"/> : null}
    <aside className={`workspace-agent-drawer ${open ? "open" : ""}`} aria-label="DoobieLogic AI agents" aria-hidden={!open}>
      <div className="workspace-agent-header">
        <div><div className="eyebrow"><Sparkles size={14}/> DoobieLogic Intelligence</div><h2>Workspace AI Agents</h2><p>Provider-neutral specialists. Deterministic analytics run before model reasoning, facility learning is auditable, and all operational tools stay read-only.</p></div>
        <button className="icon-button" type="button" aria-label="Close AI agents" onClick={() => setOpen(false)}><X size={19}/></button>
      </div>

      {directory.isLoading ? <div className="state">Loading AI agent directory…</div> : null}
      {directory.isError ? <div className="state error">{directory.error.message}</div> : null}
      {directory.data && selected ? <>
        <section className="workspace-agent-control">
          <label>Specialist<select value={effectiveKey} onChange={event => { setAgentKey(event.target.value); setQuestion(""); }}>{agents.map(agent => <option value={agent.key} key={agent.key}>{agent.name}</option>)}</select></label>
          <div className="agent-provider-line"><span className={provider?.configured ? "provider-dot connected" : "provider-dot"}/><strong>{provider?.provider ?? "AI runtime"}</strong><span>{provider?.model ? `${provider.model} · ` : ""}{provider?.local === false ? "cloud" : "local"} · {provider?.status?.replaceAll("_", " ")}</span></div>
          {learningHealth?.ok ? <div className="agent-provider-line"><span className="provider-dot connected"/><strong>Facility learning</strong><span>{learningHealth.active_learnings ?? 0} active pattern{learningHealth.active_learnings === 1 ? "" : "s"} across {learningHealth.agents_with_learnings ?? 0} agent{learningHealth.agents_with_learnings === 1 ? "" : "s"}</span></div> : null}
          {provider?.status === "deterministic_only" ? <div className="warning-banner agent-provider-warning"><p>{provider.message}</p><button className="secondary" type="button" onClick={() => { onNavigate("Integrations"); setOpen(false); }}>Open AI integrations</button></div> : null}
        </section>

        <section className="workspace-agent-profile">
          <div className="agent-profile-mark"><BrainCircuit size={22}/></div>
          <div><h3>{selected.name}</h3><p>{selected.description}</p><div className="agent-focus-list">{selected.focus.slice(0, 7).map(item => <span key={item}>{item}</span>)}</div></div>
        </section>

        {history.length ? <section className="agent-conversation" aria-live="polite">{history.map((message, index) => <article className={`agent-message ${message.role}`} key={`${message.role}-${index}`}><span>{message.role === "user" ? "You" : selected.name}</span><p>{message.content}</p></article>)}</section> : <section className="agent-empty-state"><BrainCircuit size={28}/><strong>Ask from the workspace you are working in.</strong><p>{selected.name} receives only sanitized, read-only operational context for this organization and facility.</p></section>}

        {lastRun?.fallback_used ? <div className="warning-banner agent-provider-warning"><p>Local validation required fallback to {lastRun.provider}. {lastRun.fallback_reason || "The fallback reason is recorded in AI telemetry."}</p></div> : null}
        {lastRun?.missing_data?.length ? <div className="warning-banner agent-provider-warning"><p><strong>Missing data:</strong> {lastRun.missing_data.slice(0, 4).join(" · ")}</p></div> : null}
        {lastRun?.warnings?.length ? <div className="warning-banner agent-provider-warning"><p><strong>Warnings:</strong> {lastRun.warnings.slice(0, 4).join(" · ")}</p></div> : null}

        {learnedPatterns.length ? <section className="workspace-agent-profile"><div><h3>Facility learning used</h3><p>Historical associations are advisory, not causal proof, and never override current data, SOPs, safety limits, or regulations.</p>{learnedPatterns.slice(0, 5).map((pattern, index) => <p key={`${pattern.type}-${index}`}><strong>{Math.round((pattern.confidence ?? 0) * 100)}% confidence · n={pattern.sample_size ?? 0}</strong> · {pattern.summary}</p>)}</div></section> : null}
        {sourceList.length ? <section className="workspace-agent-profile"><div><h3>Sources</h3>{sourceList.slice(0, 6).map((source, index) => <p key={`${source.title}-${index}`}><strong>{source.title || source.source || "Retrieved source"}</strong>{source.page_or_section ? ` · ${source.page_or_section}` : ""}{source.source_type ? ` · ${source.source_type}` : ""}{source.authority_level ? ` · authority ${source.authority_level}` : ""}{source.effective_date ? ` · effective ${source.effective_date}` : ""}{precedenceLabel(source.precedence_status) ? ` · ${precedenceLabel(source.precedence_status)}` : ""}</p>)}</div></section> : null}
        {freshness.length ? <section className="workspace-agent-profile"><div><h3>Data freshness</h3><p>{freshness.slice(0, 8).map(([name, value]) => `${name}: ${value}`).join(" · ")}</p></div></section> : null}

        <div className="agent-suggestions">{selected.suggested_questions.slice(0, 3).map(prompt => <button type="button" key={prompt} onClick={() => setQuestion(prompt)}>{prompt}</button>)}</div>

        <section className="agent-composer">
          <label htmlFor="workspace-agent-question">Ask {selected.name}</label>
          <textarea id="workspace-agent-question" value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask about the data and workflow on this page…" rows={4}/>
          <div className="agent-composer-footer"><div><span className="read-only-chip">Read-only</span>{lastRun?.datasets.length ? <span className="dataset-chip">{lastRun.datasets.length} dataset{lastRun.datasets.length === 1 ? "" : "s"} used</span> : null}{lastRun?.learning?.pattern_count ? <span className="dataset-chip">{lastRun.learning.pattern_count} learned pattern{lastRun.learning.pattern_count === 1 ? "" : "s"}</span> : null}{lastRun?.grounding ? <span className="dataset-chip">{lastRun.grounding}</span> : null}</div><button className="primary" type="button" disabled={!question.trim() || run.isPending || !provider?.configured} onClick={() => run.mutate()}>{run.isPending ? "Analyzing…" : <><Send size={16}/> Run agent</>}</button></div>
          {run.isError ? <div className="form-error">{run.error.message}</div> : null}
        </section>

        <div className="agent-footer"><span>Provider: {lastRun?.provider ?? provider?.provider ?? "Not connected"}{lastRun?.model ? ` · ${lastRun.model}` : ""}</span><button className="link-button" type="button" disabled={!history.length} onClick={clear}>Clear conversation</button></div>
      </> : null}
    </aside>
  </>;
}
