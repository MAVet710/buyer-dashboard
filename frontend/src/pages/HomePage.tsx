import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../lib/api";
import { Product360Drawer } from "../components/Product360Drawer";

type Summary = {
  inventory_quantity: number;
  package_count: number;
  plant_count: number;
  open_production: number;
  open_orders: number;
  compliance_exceptions: number;
  active_data_sources: number;
  data_sources_total: number;
  low_stock: number;
  open_purchase_orders: number;
  open_purchase_order_value: number;
};
type InboxItem = { id: string; severity: string; area: string; title: string; detail: string; workspace: string; entity_id: string; product_id?: string; action_label?: string; evidence?: string[] };
type Inbox = { items: InboxItem[]; summary: { critical: number; high: number; total: number } };
type Context = { user: { display_name: string; email: string; role: string }; organization: { id: string; name: string } | null; facility_id: string; facility?: { id: string; name: string } | null; facilities: { id: string; name: string }[] };
type HomeAction = { label: string; description: string; page: string; roles?: string[] };

const HOME_ACTIONS: HomeAction[] = [
  { label: "Review inventory", description: "Stock health, reorders, and aging risk.", page: "Buyer Operations", roles: ["dev", "admin", "buyer", "read_only"] },
  { label: "Start inventory audit", description: "Scan, pause, resume, and reconcile counts.", page: "Inventory Audits", roles: ["dev", "admin", "buyer", "supervisor", "operator", "qa"] },
  { label: "Traceability queue", description: "Review pending, rejected, and reconciliation-required state-system actions.", page: "Compliance", roles: ["dev", "admin", "buyer", "supervisor", "operator", "qa", "read_only"] },
  { label: "Open Package Studio", description: "Break down, pack down, build, sample, correct, and trace packages.", page: "Package Studio", roles: ["dev", "admin", "buyer", "planner", "supervisor", "operator", "qa"] },
  { label: "Build purchasing decisions", description: "Recommendations, budget, deliveries, and POs.", page: "Purchase Orders", roles: ["dev", "admin", "buyer"] },
  { label: "Plan Co-Man production", description: "Balance orders, machines, crews, and hand labor.", page: "Production", roles: ["dev", "admin", "planner", "supervisor", "operator", "qa"] },
  { label: "Review extraction", description: "Inspect run performance, yields, QA, and production risks.", page: "Extraction", roles: ["dev", "admin", "planner", "supervisor", "operator", "qa"] },
  { label: "Manage orders", description: "Track customer orders and fulfillment readiness.", page: "Orders", roles: ["dev", "admin", "buyer", "planner", "supervisor"] },
  { label: "Import operational data", description: "Load, map, review, and reuse operational sources.", page: "Data & Settings" },
];

export function HomePage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const [productId, setProductId] = useState("");
  const [productLotId, setProductLotId] = useState("");
  const summary = useQuery({ queryKey: ["home-summary"], queryFn: ({ signal }) => apiGet<Summary>("/api/v1/home/summary", signal) });
  const inbox = useQuery({ queryKey: ["operations-inbox"], queryFn: ({ signal }) => apiGet<Inbox>("/api/v1/home/inbox", signal) });
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<Context>("/api/v1/account/context", signal) });
  const role = context.data?.user.role ?? "trial";
  const actions = HOME_ACTIONS.filter(action => !action.roles || action.roles.includes(role));
  const data = summary.data;
  const facility = context.data?.facility ?? context.data?.facilities.find(row => row.id === context.data?.facility_id);
  const highPriority = inbox.data ? inbox.data.summary.critical + inbox.data.summary.high : 0;
  const openInboxItem = (item: InboxItem) => {
    if (item.product_id && item.id.startsWith("hold:")) {
      setProductId("");
      setProductLotId(item.entity_id);
    } else if (item.product_id) {
      setProductLotId("");
      setProductId(item.product_id);
    } else onNavigate(item.workspace);
  };
  const closeProduct360 = () => { setProductId(""); setProductLotId(""); };

  return <div className="page role-home-page">
    <section className="role-home-hero">
      <div className="eyebrow">Operations Home</div>
      <h1>Good to see you, {context.data?.user.display_name || context.data?.user.email || "Operator"}.</h1>
      <p>Your {roleLabel(role)} workspace is organized around what needs attention now.</p>
      <span className="role-home-context">{context.data?.organization?.name ?? "Organization"} · {facility?.name ?? "Facility"}</span>
    </section>

    <section className="role-home-metrics">
      <HomeMetric label="Needs attention" value={inbox.data?.summary.total ?? "—"} caption={`${highPriority} high-priority item(s)`}/>
      <HomeMetric label="Low stock" value={data?.low_stock ?? "—"} caption="Critical cover signal"/>
      <HomeMetric label="Open POs" value={data?.open_purchase_orders ?? "—"} caption={`${money(data?.open_purchase_order_value ?? 0)} represented`}/>
      <HomeMetric label="Data sources ready" value={data ? `${data.active_data_sources}/${data.data_sources_total}` : "—"} caption="Sources available to workspaces"/>
    </section>

    <section className="role-home-section">
      <div className="role-home-section-label">Needs attention · Operations Inbox</div>
      {inbox.isLoading ? <div className="state">Building the current facility decision queue…</div> : null}
      {inbox.isError ? <div className="state error">{inbox.error.message}</div> : null}
      {inbox.data?.items.length ? <div className="role-home-inbox">{inbox.data.items.slice(0, 8).map(item => <article className="role-home-alert" key={item.id}>
        <div className="role-home-alert-area"><span>{item.area.toUpperCase()}</span><em className={`severity ${item.severity}`}>{item.severity}</em></div>
        <div className="role-home-alert-body"><strong>{item.title}</strong><p>{item.detail}</p>{item.evidence?.length ? <small>{item.evidence.join(" · ")}</small> : null}</div>
        <button className={item.severity === "critical" ? "primary" : "secondary"} type="button" onClick={() => openInboxItem(item)}>{item.action_label || actionLabel(item.area)}</button>
      </article>)}</div> : !inbox.isLoading && !inbox.isError ? <div className="success-banner"><strong>No high-priority operational exceptions are visible from the loaded facility data.</strong><br/><span>Start from a task below or use global search.</span></div> : null}
    </section>

    <section className="role-home-section">
      <div className="role-home-section-label">Start a Task</div>
      <div className="role-home-task-grid">{actions.map((action, index) => <article className="role-home-task" key={action.label}>
        <h3>{action.label}</h3><p>{action.description}</p><button className={index === 0 ? "primary" : "secondary"} type="button" onClick={() => onNavigate(action.page)}>Open</button>
      </article>)}</div>
    </section>
    <Product360Drawer productId={productId} lotId={productLotId} open={Boolean(productId || productLotId)} onClose={closeProduct360} onNavigate={onNavigate}/>
  </div>;
}

function HomeMetric({ label, value, caption }: { label: string; value: string | number; caption: string }) {
  return <article className="role-home-metric"><span>{label}</span><strong>{typeof value === "number" ? value.toLocaleString() : value}</strong><small>{caption}</small></article>;
}
function roleLabel(role: string) { return role.replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase()); }
function money(value: number) { return Number(value || 0).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }); }
function actionLabel(area: string) { const value = area.toLowerCase(); if (value === "inventory") return "Review"; if (value === "compliance") return "Open queue"; if (value === "production") return "Open"; if (value === "orders") return "Open"; if (value === "integrations") return "Review"; return "Open"; }