import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiGet, apiPatch, apiPost } from "../lib/api";
import { pageForPath } from "../lib/workspaceRoutes";
import "./work-queue.css";

type Work = { id: string; title: string; description: string; priority: string; status: string; assignee_id: string | null; due_at: string | null; version: number; blocked_reason: string; notes: string; evidence: string; workspace: string; route: string; entity_type: string; entity_id: string; created_by: string; completed_by: string | null; completed_at: string | null };
type Template = Work & { active: boolean; frequency: string; starts_at: string; ends_at: string | null; next_occurrence: number };
type Assignee = { id: string; name: string };
type Page<T> = { items: T[]; has_more: boolean };
const WRITERS = ["dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"];
const time = (value: string | null) => value ? new Date(value).toLocaleString() : "Not set";
const localInput = (value: string | null) => value ? new Date(new Date(value).getTime() - new Date(value).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "";
const iso = (value: FormDataEntryValue | null) => value ? new Date(String(value)).toISOString() : null;

export function WorkQueuePage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const selected = params.get("item") || "";
  const [view, setView] = useState("mine");
  const [status, setStatus] = useState("");
  const [priority, setPriority] = useState("");
  const [assignee, setAssignee] = useState("");
  const [offset, setOffset] = useState(0);
  const [templateOffset, setTemplateOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [notice, setNotice] = useState("");
  const account = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<{ user: { role: string } }>("/api/v1/account/context", signal) });
  const writable = WRITERS.includes(account.data?.user.role || "");
  const users = useQuery({ queryKey: ["work-assignees"], queryFn: ({ signal }) => apiGet<Page<Assignee>>("/api/v1/work/assignees", signal) });
  const query = new URLSearchParams({ view, offset: String(offset) });
  if (status) query.set("status", status);
  if (priority) query.set("priority", priority);
  if (assignee) query.set("assignee_id", assignee);
  const queue = useQuery({ queryKey: ["work", query.toString()], queryFn: ({ signal }) => apiGet<Page<Work>>(`/api/v1/work?${query}`, signal) });
  const detail = useQuery({ queryKey: ["work-detail", selected], queryFn: ({ signal }) => apiGet<Work>(`/api/v1/work/${selected}`, signal), enabled: Boolean(selected) });
  const templates = useQuery({ queryKey: ["work-templates", templateOffset], queryFn: ({ signal }) => apiGet<Page<Template>>(`/api/v1/work/templates?offset=${templateOffset}`, signal), enabled: showTemplates });
  const refresh = async () => { await Promise.all(["work", "work-detail", "work-templates", "operations-inbox"].map(key => client.invalidateQueries({ queryKey: [key] }))); };
  const mutation = useMutation({ mutationFn: async ({ path, body, patch = false }: { path: string; body: unknown; patch?: boolean }) => patch ? apiPatch(path, body) : apiPost(path, body),
    onSuccess: async () => { setNotice("Saved."); setCreating(false); await refresh(); }, onError: () => { void refresh(); } });
  const generation = useMutation({ mutationFn: () => apiPost<{ generated: number; may_have_more: boolean }>("/api/v1/work/templates/generate", {}),
    onSuccess: async result => { setNotice(`Generated ${result.generated} work item(s).${result.may_have_more ? " More may be due. Run generation again to continue." : ""}`); await refresh(); } });
  const inspect = (id: string) => setParams(id ? { item: id } : {});
  const changeFilter = (setter: (value: string) => void, value: string) => { setter(value); setOffset(0); };
  const openLinked = (item: Work) => {
    if (item.route && pageForPath(item.route)) onNavigate(item.route);
    else if (item.workspace) onNavigate(item.workspace);
    else inspect(item.id);
  };
  const busy = mutation.isPending || generation.isPending;
  return <div className="work-queue">
    <header className="work-header"><div><h1>Work Queue</h1><p>Operational work for the active facility. Due times display in your local time.</p></div>
      <div className="work-actions"><button onClick={() => setShowTemplates(!showTemplates)}>Recurring templates</button>{writable && <><button disabled={busy} onClick={() => generation.mutate()}>Generate due work</button><button className="primary" onClick={() => setCreating(!creating)}>Create work</button></>}</div>
    </header>
    <p>Recurring work is generated on request from durable UTC schedules. Use Generate due work daily or call the same API from an approved internal process.</p>
    {notice && <p role="status">{notice}</p>}
    {[account.error, queue.error, detail.error, users.error, templates.error, mutation.error, generation.error].filter(Boolean).map((error, index) => <p role="alert" className="state error" key={index}>{error?.message}</p>)}
    {creating && writable && <CreateWork users={users.data?.items || []} busy={busy} onSubmit={body => mutation.mutate({ path: body.frequency ? "/api/v1/work/templates" : "/api/v1/work", body })} />}
    <section className="work-filters" aria-label="Work filters">
      <label>View<select value={view} onChange={e => changeFilter(setView, e.target.value)}><option value="mine">My work</option><option value="all">All work</option><option value="due">Due in 24 hours</option><option value="overdue">Overdue</option><option value="attention">My priority work</option></select></label>
      <label>Status<select value={status} onChange={e => changeFilter(setStatus, e.target.value)}><option value="">Any status</option>{["open", "in_progress", "blocked", "completed"].map(s => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</select></label>
      <label>Priority<select value={priority} onChange={e => changeFilter(setPriority, e.target.value)}><option value="">Any priority</option>{["critical", "high", "medium", "low"].map(s => <option key={s}>{s}</option>)}</select></label>
      <label>Assignee<select value={assignee} onChange={e => changeFilter(setAssignee, e.target.value)}><option value="">Anyone</option>{users.data?.items.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
    </section>
    {users.data?.has_more && <p>Showing the first 500 eligible assignees.</p>}
    {queue.isLoading && <p role="status">Loading work...</p>}
    {queue.data?.items.length === 0 && <p>No work matches these filters.</p>}
    <section className="work-cards" aria-label="Work items">{queue.data?.items.map(item => <article key={item.id} className="work-card">
      <span>{item.priority} / {item.status.replaceAll("_", " ")}</span><h2><button className="work-title" onClick={() => openLinked(item)}>{item.title}</button></h2>
      <p>{users.data?.items.find(u => u.id === item.assignee_id)?.name || (item.assignee_id ? "Assigned user" : "Unassigned")}</p><p>Due: {time(item.due_at)}</p>
      {item.status !== "completed" && item.due_at && new Date(item.due_at).getTime() < Date.now() && <strong>Overdue</strong>}
      <button onClick={() => inspect(item.id)}>Inspect work{writable ? " / update" : ""}</button>
    </article>)}</section>
    <div className="work-actions"><button disabled={offset === 0} onClick={() => setOffset(offset - 50)}>Previous</button><span>Page {offset / 50 + 1}</span><button disabled={!queue.data?.has_more} onClick={() => setOffset(offset + 50)}>Next</button></div>
    {selected && <section className="work-detail" aria-label="Work details"><button onClick={() => inspect("")}>Close details</button>{detail.isLoading && <p>Loading details...</p>}{detail.data && <WorkDetail key={`${detail.data.id}-${detail.data.version}`} item={detail.data} users={users.data?.items || []} writable={writable} busy={busy} onLinked={() => openLinked(detail.data!)} onSave={body => mutation.mutate({ path: `/api/v1/work/${selected}`, body, patch: true })}/>}</section>}
    {showTemplates && <section><h2>Recurring templates</h2><p>Daily and weekly schedules retain UTC time. Monthly work uses the anchor day, clamped to month end. Pause a template to stop future generation.</p>
      {templates.isLoading && <p>Loading templates...</p>}{templates.data?.items.length === 0 && <p>No recurring templates yet. Create work and choose a recurrence.</p>}
      {templates.data?.items.map(t => <article className="work-card" key={t.id}><h3>{t.title}</h3><p>{t.frequency} from {time(t.starts_at)} / {t.active ? "Active" : "Paused or ended"}</p>{writable && <>
        <button disabled={busy} onClick={() => mutation.mutate({ path: `/api/v1/work/templates/${t.id}`, body: { version: t.version, active: !t.active }, patch: true })}>{t.active ? "Pause" : "Resume"}</button>
        <form key={t.version} onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); mutation.mutate({ path: `/api/v1/work/templates/${t.id}`, body: { version: t.version, assignee_id: data.get("assignee_id") || null }, patch: true }); }}>
          <AssigneeField users={users.data?.items || []} value={t.assignee_id}/><button type="submit" disabled={busy}>Update future assignee</button>
        </form>
      </>}</article>)}
      <div className="work-actions"><button disabled={!templateOffset} onClick={() => setTemplateOffset(templateOffset - 50)}>Previous templates</button><button disabled={!templates.data?.has_more} onClick={() => setTemplateOffset(templateOffset + 50)}>Next templates</button></div>
    </section>}
  </div>;
}

function AssigneeField({ users, value }: { users: Assignee[]; value?: string | null }) {
  return <label>Assignee<select name="assignee_id" defaultValue={value || ""}><option value="">Unassigned</option>{value && !users.some(u => u.id === value) && <option value={value}>Previous assignee (unavailable)</option>}{users.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>;
}

function CreateWork({ users, busy, onSubmit }: { users: Assignee[]; busy: boolean; onSubmit: (body: Record<string, unknown>) => void }) {
  const [frequency, setFrequency] = useState("");
  return <form className="work-form" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const body: Record<string, unknown> = Object.fromEntries(form); body.assignee_id = form.get("assignee_id") || null;
    delete body.when; delete body.ends; if (frequency) { body.frequency = frequency; body.starts_at = iso(form.get("when")); body.ends_at = iso(form.get("ends")); } else body.due_at = iso(form.get("when")); onSubmit(body); }}>
    <h2>Create {frequency ? "recurring template" : "work"}</h2><label>Title<input name="title" required maxLength={240}/></label><label>Description<textarea name="description" maxLength={20000}/></label>
    <label>Priority<select name="priority" defaultValue="medium">{["low", "medium", "high", "critical"].map(s => <option key={s}>{s}</option>)}</select></label><AssigneeField users={users}/>
    <label>Recurrence<select value={frequency} onChange={e => setFrequency(e.target.value)}><option value="">One time</option>{["daily", "weekly", "monthly"].map(s => <option key={s}>{s}</option>)}</select></label>
    <label>{frequency ? "First due time" : "Due time"}<input name="when" type="datetime-local" required={Boolean(frequency)}/></label>{frequency && <label>Last due time (optional)<input name="ends" type="datetime-local"/></label>}
    <label>Linked workspace<input name="workspace" maxLength={120} placeholder="Inventory"/></label><label>Linked route<input name="route" maxLength={1000} placeholder="/inventory"/></label>
    <label>Entity type<input name="entity_type" maxLength={80}/></label><label>Entity ID<input name="entity_id" maxLength={255}/></label>
    <button className="primary" disabled={busy} type="submit">Save {frequency ? "template" : "work"}</button>
  </form>;
}

function WorkDetail({ item, users, writable, busy, onSave, onLinked }: { item: Work; users: Assignee[]; writable: boolean; busy: boolean; onSave: (body: unknown) => void; onLinked: () => void }) {
  const [status, setStatus] = useState(item.status);
  return <><h2>{item.title}</h2><p>{item.description}</p><p>Created by {item.created_by}</p>{item.completed_at && <p>Completed by {item.completed_by} at {time(item.completed_at)}</p>}
    {(item.workspace || item.route) && <button onClick={onLinked}>Open linked workspace</button>}{item.entity_id && <p>Linked {item.entity_type}: {item.entity_id}</p>}
    <form className="work-form" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); onSave({ ...Object.fromEntries(form), version: item.version, assignee_id: form.get("assignee_id") || null, due_at: iso(form.get("due_at")) }); }}>
      <fieldset disabled={!writable || busy}><legend>Assignment and progress</legend>
        <AssigneeField users={users} value={item.assignee_id}/><label>Due time<input name="due_at" type="datetime-local" defaultValue={localInput(item.due_at)}/></label>
        <label>Priority<select name="priority" defaultValue={item.priority}>{["low", "medium", "high", "critical"].map(s => <option key={s}>{s}</option>)}</select></label>
        <label>Status<select name="status" value={status} onChange={e => setStatus(e.target.value)}><option value="open">Open / reopen</option><option value="in_progress">Start work</option><option value="blocked">Block work</option><option value="completed">Complete work</option></select></label>
        <label>Blocked reason<textarea name="blocked_reason" maxLength={2000} required={status === "blocked"} defaultValue={item.blocked_reason}/></label>
        <label>Notes<textarea name="notes" maxLength={20000} defaultValue={item.notes}/></label><label>Evidence / references<textarea name="evidence" maxLength={20000} defaultValue={item.evidence}/></label>
        {writable && <button className="primary" type="submit">Save changes</button>}
      </fieldset>
    </form></>;
}
