import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { apiGet, apiPost } from "../lib/api";

const root = "/api/v1/commercial/crm";
const stages = ["lead", "qualified", "quoted", "negotiating", "won", "lost"];
type Account = { owner_user_id: string | null; owner_name?: string; status: string; next_action: string; next_action_date: string | null };
type Customer = { id: string; name: string; contact_name: string; contact_email: string; contact_phone: string; payment_terms: string; license_or_registration: string; relationship: Account | null };
type Opportunity = { id: string; partner_id: string; customer_name?: string; title: string; stage: string; estimated_value: number; expected_close_date: string | null; owner_user_id: string | null; owner_name?: string; source: string; next_action: string; next_action_date: string | null };
type QuoteLine = { product_id: string; quantity: number; unit_price: number; description: string; unit: string };
type Quote = { id: string; title: string; status: string; commercial_order_id: string | null; lines_json: string };
type Product = { id: string; name: string; sku: string; base_unit: string };
type Detail = { customer: Customer; relationship: Account | null; sales_value: number; open_balance: number; opportunities: Opportunity[]; quotes: Quote[]; pricing: { id: string; product_id: string; price_usd: number; discount_pct: number }[]; timeline: { id: string; kind: string; at: string; text: string; status: string; actor: string; reference?: string }[] };
type Page<T> = { items: T[]; has_more: boolean };
const money = (n: number) => n.toLocaleString(undefined, { style: "currency", currency: "USD" });
const emptyAccount: Account = { owner_user_id: null, status: "prospect", next_action: "", next_action_date: null };

export function WholesaleCRMPanel({ pipeline = false }: { pipeline?: boolean }) {
  const [selected, setSelected] = useState(() => new URLSearchParams(window.location.search).get("customer") || "");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const customers = useQuery({ queryKey: ["commercial-crm", "customers", search, offset], queryFn: ({ signal }) => apiGet<Page<Customer>>(`${root}/customers?search=${encodeURIComponent(search)}&offset=${offset}`, signal), enabled: !pipeline && !selected });
  const opportunities = useQuery({ queryKey: ["commercial-crm", "pipeline", offset], queryFn: ({ signal }) => apiGet<Page<Opportunity>>(`${root}/pipeline?offset=${offset}`, signal), enabled: pipeline && !selected });
  if (selected) return <Customer360 partnerId={selected} onBack={() => setSelected("")} />;
  const query = pipeline ? opportunities : customers;
  return <section className="inventory-panel">
    <div className="eyebrow">WHOLESALE RELATIONSHIPS</div><h2>{pipeline ? "Pipeline" : "Customers"}</h2>
    <p>Open an account to record activity, plan the next action, or prepare a quote. Create new customer trade partners in Orders.</p>
    {!pipeline && <label>Find customer <input value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }} /></label>}
    {query.isLoading && <p role="status">Loading accounts...</p>}
    {query.error && <p role="alert">{query.error.message}</p>}
    {!query.isLoading && !query.error && !query.data?.items.length && <p>No {pipeline ? "opportunities" : "customers"} found.</p>}
    <div className="table-wrap"><table><thead><tr><th>Customer</th>{pipeline && <th>Opportunity</th>}<th>{pipeline ? "Stage / Value" : "Status / Terms"}</th><th>Assigned rep</th><th>Next action</th><th>Due</th></tr></thead><tbody>
      {pipeline ? opportunities.data?.items.map(o => <tr key={o.id}><td><button className="secondary" onClick={() => setSelected(o.partner_id)}>{o.customer_name}</button></td><td>{o.title}</td><td>{o.stage} / {money(o.estimated_value)}</td><td>{o.owner_name || o.owner_user_id || "Unassigned"}</td><td>{o.next_action || "Set next action"}</td><td>{o.next_action_date || "Not scheduled"}</td></tr>) : customers.data?.items.map(c => <tr key={c.id}><td><button className="secondary" onClick={() => setSelected(c.id)}>{c.name}</button></td><td>{c.relationship?.status || "prospect"} / {c.payment_terms}</td><td>{c.relationship?.owner_name || c.relationship?.owner_user_id || "Unassigned"}</td><td>{c.relationship?.next_action || "Set next action"}</td><td>{c.relationship?.next_action_date || "Not scheduled"}</td></tr>)}
    </tbody></table></div>
    <button className="secondary" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button>{" "}<button className="secondary" disabled={!query.data?.has_more} onClick={() => setOffset(offset + 50)}>Next</button>
  </section>;
}

function Customer360({ partnerId, onBack }: { partnerId: string; onBack: () => void }) {
  const client = useQueryClient();
  const [message, setMessage] = useState("");
  const [editing, setEditing] = useState<Opportunity | null | undefined>(undefined);
  const detail = useQuery({ queryKey: ["commercial-crm", "detail", partnerId], queryFn: ({ signal }) => apiGet<Detail>(`${root}/customers/${partnerId}`, signal) });
  const mutate = useMutation({ mutationFn: ({ path, payload }: { path: string; payload: unknown }) => apiPost<{ id?: string }>(root + path, payload), onSuccess: async (result, variables) => {
    setMessage(variables.path.endsWith("/follow-ups") ? `Doobie Work follow-up created: ${result.id}. Manage it in Work.` : variables.path.endsWith("/convert") ? `Draft sales order created or recovered: ${result.id}. Continue in Orders.` : "Saved.");
    await client.invalidateQueries({ queryKey: ["commercial-crm"] });
    if (variables.path.endsWith("/follow-ups")) await client.invalidateQueries({ queryKey: ["work"] });
    if (variables.path.endsWith("/convert")) {
      await client.invalidateQueries({ queryKey: ["commercial-workspace"] });
      await client.invalidateQueries({ queryKey: ["commercial-orders"] });
    }
  } });
  const save = (suffix: string, payload: unknown) => { setMessage(""); mutate.mutate({ path: `/customers/${partnerId}/${suffix}`, payload }); };
  if (detail.isLoading) return <p role="status">Loading Customer 360...</p>;
  if (!detail.data) return <section><button onClick={onBack}>Back</button><p role="alert">{detail.error?.message || "Customer unavailable."}</p></section>;
  const d = detail.data;
  const linkedOpportunity = new URLSearchParams(window.location.search).get("opportunity");
  const activeOpportunity = editing === undefined ? d.opportunities.find(o => o.id === linkedOpportunity) || null : editing;
  return <section className="inventory-panel crm-workspace">
    <button className="secondary" onClick={onBack}>Back to accounts</button><div className="eyebrow">CUSTOMER 360</div><h2>{d.customer.name}</h2>
    <p>{d.customer.license_or_registration} | {d.customer.contact_name} | {d.customer.contact_email} | {d.customer.contact_phone} | {d.customer.payment_terms}</p>
    <p>Sales order value: <strong>{money(d.sales_value)}</strong> | Open invoice balance: <strong>{money(d.open_balance)}</strong></p>
    {mutate.error && <p role="alert">{mutate.error.message}</p>}{message && <p role="status">{message}</p>}
    <AccountForm key={JSON.stringify(d.relationship)} account={d.relationship || emptyAccount} busy={mutate.isPending} onSave={v => save("account", v)} />
    <h3>Opportunities</h3><div className="table-wrap"><table><thead><tr><th>Opportunity</th><th>Stage</th><th>Value / Close</th><th>Owner</th><th>Next action</th></tr></thead><tbody>{d.opportunities.map(o => <tr key={o.id}><td><button className="secondary" onClick={() => setEditing(o)}>{o.title}</button></td><td>{o.stage}</td><td>{money(o.estimated_value)} / {o.expected_close_date || "Unscheduled"}</td><td>{o.owner_name || o.owner_user_id || "Unassigned"}</td><td>{o.next_action} {o.next_action_date}</td></tr>)}</tbody></table></div>
    <OpportunityForm key={activeOpportunity?.id || "new"} opportunity={activeOpportunity} busy={mutate.isPending} onCancel={() => setEditing(null)} onSave={v => save(`opportunities${activeOpportunity ? "/" + activeOpportunity.id : ""}`, v)} />
    <h3>Quotes</h3><QuoteForm partnerId={partnerId} opportunities={d.opportunities} busy={mutate.isPending} onSave={v => save("quotes", v)} />
    {d.quotes.map(q => <article key={q.id} className="inventory-panel"><h4>{q.title}</h4><ul>{(JSON.parse(q.lines_json) as QuoteLine[]).map((l, i) => <li key={i}>{l.description}: {l.quantity} {l.unit} at {money(l.unit_price)}</li>)}</ul><p>{q.status}{q.commercial_order_id ? ` | Sales order ${q.commercial_order_id}` : ""}</p>{!q.commercial_order_id && <button disabled={mutate.isPending} onClick={() => mutate.mutate({ path: `/quotes/${q.id}/convert`, payload: {} })}>Convert to draft sales order</button>}</article>)}
    <h3>Doobie Work follow-up</h3><FollowUpForm opportunities={d.opportunities} busy={mutate.isPending} onSave={v => save("follow-ups", v)} />
    <h3>Record activity</h3><ActivityForm busy={mutate.isPending} onSave={v => save("activities", v)} />
    <h3>Customer timeline</h3><p>Latest 50 entries across account activity and canonical commercial records. Quotes do not reserve inventory. Conversion creates a draft sales order for the existing order workflow.</p>
    {!d.timeline.length && <p>No activity yet.</p>}<ol>{d.timeline.map(e => <li key={`${e.kind}-${e.id}`}><strong>{e.kind.replaceAll("_", " ")}: {e.text}</strong>{e.reference && <a href={`/work?item=${encodeURIComponent(e.reference)}`}> Open Work item</a>}<p>{new Date(e.at).toLocaleString()} | {e.status} {e.actor && `| ${e.actor}`}</p></li>)}</ol>
  </section>;
}

function AccountForm({ account, busy, onSave }: { account: Account; busy: boolean; onSave: (v: Account) => void }) {
  const [v, set] = useState(account);
  return <form className="crm-form" onSubmit={e => { e.preventDefault(); onSave({ owner_user_id: v.owner_user_id, status: v.status, next_action: v.next_action, next_action_date: v.next_action_date }); }}><h3>Account next action</h3><label>Assigned rep <OwnerSelect value={v.owner_user_id} onChange={owner_user_id => set({ ...v, owner_user_id })} /></label><label>Status <select value={v.status} onChange={e => set({ ...v, status: e.target.value })}>{["prospect", "active", "on_hold", "inactive"].map(s => <option key={s}>{s}</option>)}</select></label><label>Next action <input maxLength={1000} value={v.next_action} onChange={e => set({ ...v, next_action: e.target.value })} /></label><label>Next action date <input type="date" value={v.next_action_date || ""} onChange={e => set({ ...v, next_action_date: e.target.value || null })} /></label><button disabled={busy}>Save account</button></form>;
}

function OpportunityForm({ opportunity, busy, onSave, onCancel }: { opportunity: Opportunity | null; busy: boolean; onSave: (v: unknown) => void; onCancel: () => void }) {
  const [v, set] = useState<Omit<Opportunity, "id" | "partner_id">>(opportunity || { title: "", stage: "lead", estimated_value: 0, expected_close_date: null, owner_user_id: null, source: "", next_action: "", next_action_date: null });
  function submit(e: FormEvent) { e.preventDefault(); const { title, stage, estimated_value, expected_close_date, owner_user_id, source, next_action, next_action_date } = v; onSave({ title, stage, estimated_value, expected_close_date, owner_user_id, source, next_action, next_action_date }); }
  return <form className="crm-form" onSubmit={submit}><h4>{opportunity ? "Edit opportunity" : "New opportunity"}</h4>
    <label>Title <input required maxLength={255} value={v.title} onChange={e => set({ ...v, title: e.target.value })} /></label><label>Stage <select value={v.stage} onChange={e => set({ ...v, stage: e.target.value })}>{stages.map(s => <option key={s}>{s}</option>)}</select></label>
    <label>Estimated value (USD) <input required type="number" min="0" step="0.01" value={v.estimated_value} onChange={e => set({ ...v, estimated_value: Number(e.target.value) })} /></label><label>Expected close date <input type="date" value={v.expected_close_date || ""} onChange={e => set({ ...v, expected_close_date: e.target.value || null })} /></label>
    <label>Owner <OwnerSelect value={v.owner_user_id} onChange={owner_user_id => set({ ...v, owner_user_id })} /></label><label>Source <input maxLength={255} value={v.source} onChange={e => set({ ...v, source: e.target.value })} /></label><label>Next action <input maxLength={1000} value={v.next_action} onChange={e => set({ ...v, next_action: e.target.value })} /></label><label>Next action date <input type="date" value={v.next_action_date || ""} onChange={e => set({ ...v, next_action_date: e.target.value || null })} /></label><button disabled={busy}>Save opportunity</button>{opportunity && <button type="button" className="secondary" onClick={onCancel}>New opportunity</button>}
  </form>;
}

function ActivityForm({ busy, onSave }: { busy: boolean; onSave: (v: unknown) => void }) {
  const [kind, setKind] = useState("note"), [body, setBody] = useState(""), [reference, setReference] = useState("");
  return <form className="crm-form" onSubmit={e => { e.preventDefault(); onSave({ kind, body, reference }); }}><label>Activity type <select value={kind} onChange={e => setKind(e.target.value)}>{["call", "email", "meeting", "note", "task_reference"].map(k => <option key={k}>{k}</option>)}</select></label><label>Notes <textarea required maxLength={10000} value={body} onChange={e => setBody(e.target.value)} /></label><label>Task or activity reference <input maxLength={255} value={reference} onChange={e => setReference(e.target.value)} /></label><button disabled={busy}>Record activity</button></form>;
}

function QuoteForm({ partnerId, opportunities, busy, onSave }: { partnerId: string; opportunities: Opportunity[]; busy: boolean; onSave: (v: unknown) => void }) {
  const [title, setTitle] = useState(""), [search, setSearch] = useState(""), [opportunity, setOpportunity] = useState("");
  const [lines, setLines] = useState<{ product_id: string; name: string; quantity: number; price: string }[]>([]);
  const products = useQuery({ queryKey: ["commercial-crm", "products", search, partnerId], queryFn: ({ signal }) => apiGet<Product[]>(`${root}/products?search=${encodeURIComponent(search)}`, signal) });
  return <form className="crm-form" onSubmit={e => { e.preventDefault(); onSave({ title, opportunity_id: opportunity || null, lines: lines.map(l => ({ product_id: l.product_id, quantity: l.quantity, unit_price: l.price === "" ? null : Number(l.price) })) }); }}>
    <label>Quote title <input required maxLength={255} value={title} onChange={e => setTitle(e.target.value)} /></label><label>Opportunity <select value={opportunity} onChange={e => setOpportunity(e.target.value)}><option value="">No linked opportunity</option>{opportunities.map(o => <option key={o.id} value={o.id}>{o.title}</option>)}</select></label>
    <label>Find product <input value={search} onChange={e => setSearch(e.target.value)} /></label>{products.error && <p role="alert">{products.error.message}</p>}
    <label>Add product <select value="" disabled={lines.length >= 100} onChange={e => { const p = products.data?.find(p => p.id === e.target.value); if (p) setLines([...lines, { product_id: p.id, name: `${p.name} (${p.base_unit})`, quantity: 1, price: "" }]); }}><option value="">Select product</option>{products.data?.map(p => <option key={p.id} value={p.id}>{p.name} | {p.sku}</option>)}</select></label>
    <p>Leave price blank to use customer pricing, then facility wholesale pricing. If neither is available, enter an explicit unit price. Review saved quote prices before conversion.</p>
    {lines.map((l, i) => <div className="crm-line" key={i}><strong>{l.name}</strong><label>Quantity <input required type="number" min="0.000001" step="any" value={l.quantity} onChange={e => setLines(lines.map((x, j) => j === i ? { ...x, quantity: Number(e.target.value) } : x))} /></label><label>Unit price (USD) <input type="number" min="0" step="0.01" placeholder="Customer pricing" value={l.price} onChange={e => setLines(lines.map((x, j) => j === i ? { ...x, price: e.target.value } : x))} /></label><button type="button" className="secondary" onClick={() => setLines(lines.filter((_, j) => j !== i))}>Remove</button></div>)}
    <button disabled={busy || !lines.length}>Save quote</button>
  </form>;
}


function OwnerSelect({ value, onChange }: { value: string | null; onChange: (id: string | null) => void }) {
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const owners = useQuery({ queryKey: ["commercial-crm", "owners", search, offset], queryFn: ({ signal }) => apiGet<Page<{ id: string; name: string }>>(`${root}/owners?search=${encodeURIComponent(search)}&offset=${offset}`, signal) });
  return <span><input aria-label="Find assigned user" value={search} onChange={e => { setSearch(e.target.value); setOffset(0); }} placeholder="Find user" />
    <select aria-label="Assigned user" value={value || ""} onChange={e => onChange(e.target.value || null)}><option value="">Unassigned</option>{value && !owners.data?.items.some(u => u.id === value) && <option value={value}>{value} (current)</option>}{owners.data?.items.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}</select>
    {owners.error && <span role="alert">{owners.error.message}</span>}
    <button type="button" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous users</button><button type="button" disabled={!owners.data?.has_more} onClick={() => setOffset(offset + 50)}>More users</button>
  </span>;
}

function FollowUpForm({ opportunities, busy, onSave }: { opportunities: Opportunity[]; busy: boolean; onSave: (v: unknown) => void }) {
  const [title, setTitle] = useState(""), [opportunity, setOpportunity] = useState(""), [due, setDue] = useState("");
  const [assignee, setAssignee] = useState<string | null>(null);
  return <form className="crm-form" onSubmit={e => { e.preventDefault(); onSave({ title, opportunity_id: opportunity || null, assignee_id: assignee, due_at: due ? new Date(due).toISOString() : null }); }}>
    <label>Follow-up title <input required maxLength={240} value={title} onChange={e => setTitle(e.target.value)} /></label>
    <label>Follow-up opportunity <select value={opportunity} onChange={e => setOpportunity(e.target.value)}><option value="">Customer account</option>{opportunities.map(o => <option key={o.id} value={o.id}>{o.title}</option>)}</select></label>
    <label>Follow-up assignee <OwnerSelect value={assignee} onChange={setAssignee} /></label>
    <label>Follow-up due <input type="datetime-local" value={due} onChange={e => setDue(e.target.value)} /></label>
    <button disabled={busy}>Create Work follow-up</button><a href="/work">Open Doobie Work</a>
  </form>;
}
