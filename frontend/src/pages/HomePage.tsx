import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { apiGet } from "../lib/api";
import { StreamlitDialog, StreamlitMetric } from "../components/StreamlitPrimitives";

type Summary = { inventory_quantity: number; package_count: number; plant_count: number; open_production: number; open_orders: number; compliance_exceptions: number; active_data_sources: number };
type Result = { kind: string; id: string; title: string; subtitle: string; workspace: string };
type Inbox = { items: { id: string; severity: string; area: string; title: string; detail: string; workspace: string; entity_id: string }[]; summary: { critical: number; high: number; total: number } };
type AccountContext = { user: { display_name: string; email: string; role: string }; organization: { name: string } | null; facility_id: string; facilities: { id: string; name: string }[] };
type Product360 = { product: { id: string; sku: string; name: string; item_type: string; base_unit: string; unit_cost: number; retail_price: number; upc: string }; profile: { brand: string; category: string; strain: string; product_format: string; description: string } | null; inventory: { packages: { id: string; package_id: string; location: string; status: string; balance: number; unit: string }[]; on_hand: number; package_count: number }; sales_30d: { quantity: number; net_sales: number; daily_velocity: number }; open_orders: { id: string; order_number: string; order_type: string; status: string; quantity: number; fulfilled_quantity: number; unit: string }[]; production_orders: { id: string; order_number: string; status: string; requested_units: number; due_at: string | null; product_format: string }[]; aliases: { alias: string; source: string }[]; mappings: { system_name: string; external_id: string; external_name: string }[]; value_history: { value_type: string; amount: number; currency: string; effective_at: string }[] };
type HomeAction = { label: string; description: string; page: string; roles?: string[] };

const HOME_ACTIONS: HomeAction[] = [
  { label: "Review inventory", description: "Stock health, reorders, and aging risk.", page: "Buyer Operations", roles: ["dev","admin","buyer","read_only","trial"] },
  { label: "Start inventory audit", description: "Scan, pause, resume, and reconcile counts.", page: "Inventory Audits", roles: ["dev","admin","buyer","supervisor","operator","qa","trial"] },
  { label: "Traceability queue", description: "Review pending, rejected, and reconciliation-required state-system actions.", page: "Compliance", roles: ["dev","admin","buyer","supervisor","operator","qa","read_only","trial"] },
  { label: "Open Package Studio", description: "Break down, pack down, build, sample, correct, and trace packages.", page: "Package Studio", roles: ["dev","admin","buyer","planner","supervisor","operator","qa","trial"] },
  { label: "Build purchasing decisions", description: "Recommendations, budget, deliveries, and POs.", page: "Purchase Orders", roles: ["dev","admin","buyer","trial"] },
  { label: "Plan Co-Man production", description: "Balance orders, machines, crews, and hand labor.", page: "Production", roles: ["dev","admin","planner","supervisor","operator","qa","trial"] },
  { label: "Review extraction", description: "Inspect run performance, yields, QA, and production risks.", page: "Extraction", roles: ["dev","admin","planner","supervisor","operator","qa","trial"] },
  { label: "Manage orders", description: "Track customer orders and fulfillment readiness.", page: "Orders", roles: ["dev","admin","buyer","planner","supervisor","trial"] },
  { label: "Import operational data", description: "Load, map, review, and reuse operational sources.", page: "Data & Settings" },
];

export function HomePage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const [search, setSearch] = useState(""); const [productId, setProductId] = useState("");
  const account = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<AccountContext>("/api/v1/account/context", signal) });
  const summary = useQuery({ queryKey: ["home-summary"], queryFn: ({ signal }) => apiGet<Summary>("/api/v1/home/summary", signal) });
  const inbox = useQuery({ queryKey: ["operations-inbox"], queryFn: ({ signal }) => apiGet<Inbox>("/api/v1/home/inbox", signal) });
  const results = useQuery({ queryKey: ["universal-search", search], enabled: search.trim().length >= 2, queryFn: ({ signal }) => apiGet<Result[]>(`/api/v1/home/search?q=${encodeURIComponent(search)}`, signal) });
  const product = useQuery({ queryKey: ["product-360", productId], enabled: Boolean(productId), queryFn: ({ signal }) => apiGet<Product360>(`/api/v1/home/products/${productId}`, signal) });
  const data = summary.data; const role = account.data?.user.role ?? "trial";
  const facility = account.data?.facilities.find(row => row.id === account.data?.facility_id)?.name ?? "";
  const actions = useMemo(() => HOME_ACTIONS.filter(action => !action.roles || action.roles.includes(role)), [role]);
  const highPriority = (inbox.data?.summary.critical ?? 0) + (inbox.data?.summary.high ?? 0);
  const lowStock = inbox.data?.items.filter(item => item.area.toLowerCase().includes("inventory") && ["critical","high"].includes(item.severity.toLowerCase())).length ?? 0;

  return <div className="page">
    <section className="role-home-hero"><div className="eyebrow">Operations Home</div><h1>Good to see you, {account.data?.user.display_name || account.data?.user.email || "Operator"}.</h1><p>Your {role.replaceAll("_", " ")} workspace is organized around what needs attention now.</p><span>{[account.data?.organization?.name, facility].filter(Boolean).join(" · ") || "Choose an organization and facility"}</span></section>
    <section className="metrics home-role-metrics"><StreamlitMetric label="Needs attention" value={inbox.data?.summary.total ?? "—"} help={`${highPriority} high-priority item(s)`}/><StreamlitMetric label="Low stock" value={lowStock} help="Critical cover signal" tone={lowStock ? "yellow" : "copper"}/><StreamlitMetric label="Open POs / orders" value={data?.open_orders ?? "—"} help="Open operational demand"/><StreamlitMetric label="Data sources ready" value={data?.active_data_sources ?? "—"} help="Sources available to workspaces" tone="green"/></section>

    <label className="home-search"><Search size={20}/><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search products, packages, plants, orders, partners…" /></label>
    {search.length >= 2 ? <section className="search-results">{results.data?.map(row => <button key={`${row.kind}-${row.id}`} onClick={() => row.kind === "product" ? setProductId(row.id) : onNavigate(row.workspace)}><span className="badge">{row.kind}</span><strong>{row.title}</strong><small>{row.subtitle}</small><em>{row.kind === "product" ? "Product 360 →" : `${row.workspace} →`}</em></button>)}{results.data?.length === 0 ? <div className="empty">No matching records in this facility.</div> : null}</section> : null}

    <div className="inbox-heading"><div><div className="eyebrow">Needs Attention · Operations Inbox</div><h2>Operations Inbox</h2></div><span>{inbox.data?.summary.total ?? 0} items · {highPriority} high priority</span></div>
    <section className="inbox-list">{inbox.data?.items.map(row => <button key={row.id} onClick={() => onNavigate(row.workspace)}><span className={`severity ${row.severity}`}>{row.severity}</span><span><strong>{row.title}</strong><small>{row.area} · {row.detail}</small></span><em>{row.workspace} →</em></button>)}{inbox.data?.items.length === 0 ? <div className="empty">No high-priority operational exceptions are visible from the loaded facility data.</div> : null}</section>

    <div className="inbox-heading task-heading"><div><div className="eyebrow">Start a Task</div><h2>What do you need to do?</h2></div></div>
    <section className="role-task-grid">{actions.map((action,index)=><article className="role-task-card" key={action.label}><div className="task-index">{String(index+1).padStart(2,"0")}</div><h3>{action.label}</h3><p>{action.description}</p><button className={index===0?"primary":"secondary"} onClick={()=>onNavigate(action.page)}>Open</button></article>)}</section>

    {productId ? <Product360Modal data={product.data} loading={product.isLoading} onClose={() => setProductId("")} onNavigate={onNavigate}/> : null}
  </div>;
}

function Product360Modal({ data, loading, onClose, onNavigate }: { data?: Product360; loading: boolean; onClose: () => void; onNavigate: (page: string) => void }) {
  return <StreamlitDialog title={data?.product.name ?? "Loading product…"} subtitle="Product 360" onClose={onClose} size="wide">
    <p className="dialog-context">{data ? `${data.product.sku} · ${data.profile?.brand || "No brand"} · ${data.profile?.category || data.product.item_type}` : "Cross-workspace context"}</p>
    {loading ? <div className="state">Loading durable product context…</div> : data ? <><section className="quantity-summary"><span>On hand<strong>{data.inventory.on_hand.toLocaleString()} {data.product.base_unit}</strong></span><span>30d sold<strong>{data.sales_30d.quantity.toLocaleString()}</strong></span><span>30d net sales<strong>{money(data.sales_30d.net_sales)}</strong></span></section><div className="product360-grid"><section><h3>Packages</h3>{data.inventory.packages.map(row => <article className="catalog-row" key={row.id}><strong>{row.package_id}</strong><span>{row.balance} {row.unit}</span><small>{row.location} · {row.status}</small></article>)}{data.inventory.packages.length === 0 ? <div className="empty">No packages in this facility.</div> : null}</section><section><h3>Open demand</h3>{data.open_orders.map(row => <article className="catalog-row" key={row.id}><strong>{row.order_number}</strong><span>{row.quantity - row.fulfilled_quantity} {row.unit}</span><small>{row.order_type} · {row.status}</small></article>)}{data.production_orders.map(row => <article className="catalog-row" key={row.id}><strong>{row.order_number}</strong><span>{row.requested_units} units</span><small>production · {row.status}</small></article>)}{!data.open_orders.length && !data.production_orders.length ? <div className="empty">No open demand.</div> : null}</section><section><h3>Catalog identity</h3><div className="catalog-row"><strong>UPC</strong><span>{data.product.upc || "—"}</span></div>{data.aliases.map(row => <div className="catalog-row" key={row.alias}><strong>Alias</strong><span>{row.alias}</span><small>{row.source}</small></div>)}{data.mappings.map(row => <div className="catalog-row" key={`${row.system_name}-${row.external_id}`}><strong>{row.system_name}</strong><span>{row.external_id}</span><small>{row.external_name}</small></div>)}</section><section><h3>Value history</h3>{data.value_history.slice(0,8).map(row => <div className="catalog-row" key={`${row.value_type}-${row.effective_at}`}><strong>{row.value_type.replaceAll("_"," ")}</strong><span>{money(row.amount)}</span><small>{new Date(row.effective_at).toLocaleString()}</small></div>)}</section></div><div className="audit-actions"><button className="secondary" onClick={() => { onClose(); onNavigate("Inventory"); }}>Open inventory</button><button className="primary" onClick={() => { onClose(); onNavigate("Retail Product Master"); }}>Open Product Master</button></div></> : null}
  </StreamlitDialog>;
}
function money(value:number){return value.toLocaleString(undefined,{style:"currency",currency:"USD",maximumFractionDigits:2});}
