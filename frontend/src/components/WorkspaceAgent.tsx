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

type AgentDirectory = {
  active_agent: AgentProfile;
  agents: AgentProfile[];
  provider: {
    provider: string;
    configured: boolean;
    status: string;
    fallback_configured?: boolean;
    message?: string;
  };
  workspace: { app_mode: string; section: string };
};

type ChatMessage = { role: "user" | "assistant"; content: string };
type AgentRun = {
  answer: string;
  provider: string;
  agent: AgentProfile;
  datasets: string[];
  read_only: boolean;
  confidence?: string;
  sources?: unknown[];
};

type Props = {
  activePage: string;
  operation: "Retail Ops" | "Production Ops";
  onNavigate: (page: string) => void;
};

function readHistory(key: string): ChatMessage[] {
  try {
    const value = JSON.parse(sessionStorage.getItem(`workspace-agent-history-${key}`) ?? "[]");
    return Array.isArray(value) ? value.filter(item => item && (item.role === "user" || item.role === "assistant") && typeof item.content === "string").slice(-20) : [];
  } catch {
    return [];
  }
}

function saveHistory(key: string, history: ChatMessage[]) {
  try { sessionStorage.setItem(`workspace-agent-history-${key}`, JSON.stringify(history.slice(-20))); } catch { /* storage can be unavailable */ }
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
  const effectiveKey = agentKey || directory.data?.active_agent.key || "ops";
  const selected = directory.data?.agents.find(row => row.key === effectiveKey) ?? directory.data?.active_agent;

  useEffect(() => {
    if (!directory.data?.active_agent) return;
    setAgentKey(directory.data.active_agent.key);
  }, [directory.data?.active_agent.key, activePage, operation]);

  useEffect(() => {
    if (!effectiveKey) return;
    setHistory(readHistory(effectiveKey));
    setLastRun(null);
  }, [effectiveKey]);

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
      const next: ChatMessage[] = [...history, { role: "user", content: question.trim() }, { role: "assistant", content: result.answer }].slice(-20);
      setHistory(next);
      saveHistory(effectiveKey, next);
      setLastRun(result);
      setQuestion("");
    },
  });

  const clear = () => {
    setHistory([]);
    setLastRun(null);
    saveHistory(effectiveKey, []);
  };
  const provider = directory.data?.provider;

  return <>
    <button className="workspace-agent-launch" type="button" onClick={() => setOpen(true)} aria-label="Open DoobieLogic AI agents">
      <BrainCircuit size={18}/><span>{selected?.name ?? "AI Agents"}</span><i className={provider?.configured ? "is-connected" : ""}/>
    </button>
    {open ? <div className="workspace-agent-backdrop" onClick={() => setOpen(false)} aria-hidden="true"/> : null}
    <aside className={`workspace-agent-drawer ${open ? "open" : ""}`} aria-label="DoobieLogic AI agents" aria-hidden={!open}>
      <div className="workspace-agent-header">
        <div><div className="eyebrow"><Sparkles size={14}/> DoobieLogic Intelligence</div><h2>Workspace AI Agents</h2><p>Specialists restored from the original workspace. Analysis stays read-only.</p></div>
        <button className="icon-button" type="button" aria-label="Close AI agents" onClick={() => setOpen(false)}><X size={19}/></button>
      </div>

      {directory.isLoading ? <div className="state">Loading AI agent directory…</div> : null}
      {directory.isError ? <div className="state error">{directory.error.message}</div> : null}
      {directory.data && selected ? <>
        <section className="workspace-agent-control">
          <label>Specialist<select value={effectiveKey} onChange={event => { setAgentKey(event.target.value); setQuestion(""); }}>{directory.data.agents.map(agent => <option value={agent.key} key={agent.key}>{agent.name}</option>)}</select></label>
          <div className="agent-provider-line"><span className={provider?.configured ? "provider-dot connected" : "provider-dot"}/><strong>{provider?.provider}</strong><span>{provider?.configured ? provider.status : "AI provider not connected"}</span></div>
          {!provider?.configured ? <div className="warning-banner agent-provider-warning"><p>{provider?.message ?? "A platform AI connection is required before the agents can answer."}</p><button className="secondary" type="button" onClick={() => { onNavigate("Integrations"); setOpen(false); }}>Open AI integrations</button></div> : null}
        </section>

        <section className="workspace-agent-profile">
          <div className="agent-profile-mark"><BrainCircuit size={22}/></div>
          <div><h3>{selected.name}</h3><p>{selected.description}</p><div className="agent-focus-list">{selected.focus.slice(0, 7).map(item => <span key={item}>{item}</span>)}</div></div>
        </section>

        {history.length ? <section className="agent-conversation" aria-live="polite">{history.map((message, index) => <article className={`agent-message ${message.role}`} key={`${message.role}-${index}`}><span>{message.role === "user" ? "You" : selected.name}</span><p>{message.content}</p></article>)}</section> : <section className="agent-empty-state"><BrainCircuit size={28}/><strong>Ask from the workspace you are working in.</strong><p>{selected.name} receives only sanitized, read-only operational context for this organization and facility.</p></section>}

        <div className="agent-suggestions">{selected.suggested_questions.slice(0, 3).map(prompt => <button type="button" key={prompt} onClick={() => setQuestion(prompt)}>{prompt}</button>)}</div>

        <section className="agent-composer">
          <label htmlFor="workspace-agent-question">Ask {selected.name}</label>
          <textarea id="workspace-agent-question" value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask about the data and workflow on this page…" rows={4}/>
          <div className="agent-composer-footer"><div><span className="read-only-chip">Read-only</span>{lastRun?.datasets.length ? <span className="dataset-chip">{lastRun.datasets.length} dataset{lastRun.datasets.length === 1 ? "" : "s"} used</span> : null}</div><button className="primary" type="button" disabled={!question.trim() || run.isPending || !provider?.configured} onClick={() => run.mutate()}>{run.isPending ? "Analyzing…" : <><Send size={16}/> Run agent</>}</button></div>
          {run.isError ? <div className="form-error">{run.error.message}</div> : null}
        </section>

        <div className="agent-footer"><span>Provider: {lastRun?.provider ?? provider?.provider}</span><button className="link-button" type="button" disabled={!history.length} onClick={clear}>Clear conversation</button></div>
      </> : null}
    </aside>
  </>;
}
