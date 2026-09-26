import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPostIdempotent } from "../lib/api";
import "./adoption.css";

type Subscription = { id: string; report_type: string; recipients: string[]; cadence: string; active: boolean; next_run: string; last_run: string | null };
type Delivery = { id: string; report_type: string; status: string; detail: string; created_at: string; recipients: string[] };
const displayDate = (value: string | null) => value ? new Date(value).toLocaleString() : "Never";

export function ScheduledReportsPage() {
  const client = useQueryClient();
  const [report, setReport] = useState("production");
  const [recipients, setRecipients] = useState("");
  const [cadence, setCadence] = useState("weekly");
  const [offset, setOffset] = useState(0);
  const [subscriptionOffset, setSubscriptionOffset] = useState(0);
  const [result, setResult] = useState("");
  // Keep the same key after a network error so an explicit retry cannot resend.
  const pendingRun = useRef<{ action: string; key: string } | null>(null);
  const subscriptions = useQuery({ queryKey: ["report-subscriptions", subscriptionOffset], queryFn: ({ signal }) => apiGet<{ items: Subscription[] }>(`/api/v1/report-subscriptions?offset=${subscriptionOffset}`, signal) });
  const history = useQuery({ queryKey: ["report-delivery-history", offset], queryFn: ({ signal }) => apiGet<{ items: Delivery[] }>(`/api/v1/report-subscriptions/history?offset=${offset}`, signal) });
  const catalog = useQuery({ queryKey: ["executive-report-catalog"], queryFn: ({ signal }) => apiGet<{ items: { key: string; label: string }[] }>("/api/v1/executive-reports/catalog", signal) });
  const action = useMutation({
    mutationFn: async ({ kind, subscription }: { kind: string; subscription?: Subscription }) => {
      setResult("");
      if (kind === "create") return apiPost("/api/v1/report-subscriptions", { report_type: report, recipients: recipients.split(",").map(value => value.trim()), cadence });
      if (kind === "due") return apiPost("/api/v1/report-subscriptions/process-due", {});
      if (!subscription) return;
      if (kind === "active") return apiPost(`/api/v1/report-subscriptions/${subscription.id}/active`, { active: !subscription.active });
      const identity = `${subscription.id}:${kind}`;
      if (pendingRun.current && pendingRun.current.action !== identity) throw new Error("Retry the previous report action first to resolve its delivery status.");
      if (!pendingRun.current) pendingRun.current = { action: identity, key: crypto.randomUUID() };
      const delivery = await apiPostIdempotent<Delivery>(`/api/v1/report-subscriptions/${subscription.id}/run`, { test: kind === "test" }, pendingRun.current.key);
      pendingRun.current = null;
      setResult(`${delivery.status}: ${delivery.detail}`);
      return delivery;
    },
    onSuccess: async () => {
      await Promise.all([client.invalidateQueries({ queryKey: ["report-subscriptions"] }), client.invalidateQueries({ queryKey: ["report-delivery-history"] })]);
    },
  });
  return <div className="page adoption-page"><h1>Scheduled Reports</h1>
    <p>Facility administrators can send Executive Reports to approved recipients. Daily and weekly schedules use elapsed UTC days; monthly schedules use the next month, clamped to its last day. First delivery is one cadence from creation.</p>
    <p>Delivery requires a live Spacemail validation. Test sends the current report to the subscription recipients. Processing or uncertain deliveries must be reviewed before another send.</p>
    <p>Delivery runs when an administrator processes due reports or an authorized scheduler invokes scheduled processing.</p>
    {[subscriptions.error, history.error, catalog.error, action.error].filter(Boolean).map((error, index) => <p role="alert" key={index}>{error?.message}</p>)}
    {result && <p role="status">{result}</p>}
    {subscriptions.isPending && <p role="status">Loading subscriptions...</p>}
    {subscriptions.isSuccess && <>
      <form className="inventory-panel" onSubmit={event => { event.preventDefault(); action.mutate({ kind: "create" }); }}>
        <h2>Create subscription</h2>
        <label>Report<select value={report} onChange={event => setReport(event.target.value)}>{catalog.data?.items.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
        <label>Recipients, separated by commas<input required value={recipients} onChange={event => setRecipients(event.target.value)} /></label>
        <label>Cadence<select value={cadence} onChange={event => setCadence(event.target.value)}>{["daily", "weekly", "monthly"].map(value => <option key={value}>{value}</option>)}</select></label>
        <button className="primary" disabled={action.isPending}>Create subscription</button>
      </form>
      <button className="secondary" disabled={action.isPending} onClick={() => action.mutate({ kind: "due" })}>Process due subscriptions</button>
      <div className="report-card-grid">{subscriptions.data.items.map(subscription => <article className="inventory-panel" key={subscription.id}>
        <h2>{subscription.report_type}</h2><p>{subscription.recipients.join(", ")}</p><p>{subscription.cadence}, {subscription.active ? "Active" : "Paused"}</p>
        <p>Next: {displayDate(subscription.next_run)}. Last attempt: {displayDate(subscription.last_run)}</p>
        <button className="secondary" disabled={action.isPending} onClick={() => action.mutate({ kind: "active", subscription })}>{subscription.active ? "Pause" : "Resume"}</button>
        <button className="secondary" disabled={action.isPending} onClick={() => action.mutate({ kind: "test", subscription })}>Test delivery</button>
        <button className="secondary" disabled={action.isPending} onClick={() => action.mutate({ kind: "run", subscription })}>Run now</button>
      </article>)}</div>
      {subscriptions.data.items.length === 0 && <p>No subscriptions on this page.</p>}
      <button className="secondary" disabled={subscriptionOffset === 0} onClick={() => setSubscriptionOffset(Math.max(0, subscriptionOffset - 100))}>Previous subscriptions</button>
      <button className="secondary" disabled={subscriptions.data.items.length < 100} onClick={() => setSubscriptionOffset(subscriptionOffset + 100)}>More subscriptions</button>
    </>}
    <section className="inventory-panel"><h2>Delivery history</h2>
      {history.isPending && <p>Loading history...</p>}
      {history.data?.items.length === 0 && <p>No delivery attempts recorded.</p>}
      {history.data?.items.map(delivery => <article key={delivery.id}><h3>{delivery.report_type}: {delivery.status}</h3><p>{displayDate(delivery.created_at)} | {delivery.recipients.join(", ")}</p><p>{delivery.detail}</p></article>)}
      <button className="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Newer</button>
      <button className="secondary" disabled={(history.data?.items.length ?? 0) < 50} onClick={() => setOffset(offset + 50)}>Older</button>
    </section>
  </div>;
}
