import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { apiGet } from "../lib/api";
import type { PackageLineage } from "../types/inventory";
import { StreamlitDialog } from "./StreamlitDialog";

type Product360Package = {
  id: string;
  package_id: string;
  lot_code: string;
  location: string;
  status: string;
  balance: number;
  reserved: number;
  unit: string;
  received_at: string | null;
  expiration_at: string | null;
  lab_status: string;
  coa_reference: string;
  source_name: string;
};

type Product360Snapshot = {
  product: { id: string; sku: string; name: string; item_type: string; base_unit: string; unit_cost: number; retail_price: number; upc: string; active: boolean };
  profile: null | { brand: string; category: string; subcategory: string; strain: string; manufacturer: string; product_format: string; description: string; retail_enabled: boolean; production_enabled: boolean };
  inventory: { packages: Product360Package[]; on_hand: number; reserved: number; available_after_reserved: number; package_count: number };
  sales: { windows: Record<string, { quantity: number; net_sales: number }>; daily_velocity: number; sales_trend_pct: number | null; source: string };
  decision: { signal: string; reason: string; target_days: number; target_units: number; days_on_hand: number | null; stockout_date: string | null };
  economics: {
    unit_cost: number; retail_price: number; margin_pct: number | null; inventory_value: number; retail_value: number; gross_profit_value: number;
    sell_through_pct: number; estimated_reorder_cost: number; estimated_reorder_retail_value: number; estimated_reorder_gross_profit: number;
  };
  age: { oldest_age_days: number | null; nearest_expiration_days: number | null; last_received_date: string | null };
  compliance: { status: string; lab_status: string };
  open_orders: { id: string; order_number: string; order_type: string; status: string; quantity: number; fulfilled_quantity: number; unit: string }[];
  production_orders: { id: string; order_number: string; status: string; requested_units: number; due_at: string | null; product_format: string }[];
  aliases: { alias: string; source: string }[];
  mappings: { system_name: string; external_id: string; external_name: string }[];
  value_history: { value_type: string; amount: number; currency: string; effective_at: string }[];
};

type Tab = "overview" | "inventory" | "sales" | "purchasing" | "packages" | "compliance" | "audits" | "master" | "lineage";

const money = (value: number | null | undefined) => `$${Number(value ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const number = (value: number | null | undefined, digits = 1) => value == null ? "—" : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
const date = (value: string | null | undefined) => value ? new Date(value).toLocaleDateString() : "—";

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{note ? <small>{note}</small> : null}</div>;
}

function Tabs({ active, onChange, showLineage }: { active: Tab; onChange: (tab: Tab) => void; showLineage: boolean }) {
  const tabs: { key: Tab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "inventory", label: "Inventory" },
    { key: "sales", label: "Sales" },
    { key: "purchasing", label: "Purchasing" },
    { key: "packages", label: "Packages" },
    { key: "compliance", label: "Compliance" },
    { key: "audits", label: "Audits" },
    { key: "master", label: "Product Master" },
  ];
  if (showLineage) tabs.push({ key: "lineage", label: "Lineage" });
  return <div className="operation-switch">{tabs.map(tab => <button type="button" key={tab.key} className={active === tab.key ? "active" : ""} onClick={() => onChange(tab.key)}>{tab.label}</button>)}</div>;
}

function fallbackNavigate(page: string) {
  sessionStorage.setItem("buyer-dash-pending-page", page);
  window.location.reload();
}

export function Product360Workspace({ data, initialTab = "overview", focusPackageId, lineage, onNavigate }: { data: Product360Snapshot; initialTab?: Tab; focusPackageId?: string; lineage?: PackageLineage | null; onNavigate?: (page: string) => void }) {
  const [tab, setTab] = useState<Tab>(initialTab);
  const packages = useMemo(() => {
    if (!focusPackageId) return data.inventory.packages;
    return [...data.inventory.packages].sort((a, b) => Number(b.id === focusPackageId) - Number(a.id === focusPackageId));
  }, [data.inventory.packages, focusPackageId]);
  const focused = focusPackageId ? data.inventory.packages.find(row => row.id === focusPackageId) : undefined;
  const profile = data.profile;
  const days = data.decision.days_on_hand;
  const trend = data.sales.sales_trend_pct;
  const navigate = (page: string) => onNavigate ? onNavigate(page) : fallbackNavigate(page);
  const stagePo = () => {
    sessionStorage.setItem("buyer-dash-po-inventory-selection", JSON.stringify([{ product_id: data.product.id, sku: data.product.sku, description: data.product.name, quantity: Math.max(1, data.decision.target_units), price: data.economics.unit_cost }]));
    navigate("Purchase Orders");
  };
  const audit = () => {
    sessionStorage.setItem("buyer-dash-audit-product-focus", JSON.stringify({ operation: profile?.production_enabled && !profile?.retail_enabled ? "production" : "retail", selections: [{ product_id: data.product.id, sku: data.product.sku, product_name: data.product.name, lot_id: focusPackageId || undefined }] }));
    navigate("Inventory Audits");
  };

  return <div className="product-360-workspace">
    <section className="inventory-panel">
      <div className="page-heading"><div><div className="eyebrow">Decision signal</div><h3>{data.decision.signal}</h3><p>{data.decision.reason}</p></div><span className="badge">{data.product.active ? "active" : "archived"}</span></div>
      <div className="metrics">
        <Metric label="On hand" value={`${number(data.inventory.on_hand)} ${data.product.base_unit}`} note={`${data.inventory.package_count} package${data.inventory.package_count === 1 ? "" : "s"}`} />
        <Metric label="Days on hand" value={days == null ? "No velocity" : `${number(days)} days`} note={data.decision.stockout_date ? `Stockout ${data.decision.stockout_date}` : undefined} />
        <Metric label="30-day velocity" value={`${number(data.sales.windows["30"]?.quantity, 0)} units`} note={`${number(data.sales.daily_velocity, 2)}/day`} />
        <Metric label="Target reorder" value={`${number(data.decision.target_units, 0)} units`} note={`${data.decision.target_days}-day target`} />
      </div>
    </section>

    <Tabs active={tab} onChange={setTab} showLineage={Boolean(lineage)} />

    {tab === "overview" ? <div>
      <div className="metrics">
        <Metric label="Inventory cost" value={money(data.economics.inventory_value)} />
        <Metric label="Retail value" value={money(data.economics.retail_value)} />
        <Metric label="Gross profit value" value={money(data.economics.gross_profit_value)} />
        <Metric label="Margin" value={data.economics.margin_pct == null ? "—" : `${number(data.economics.margin_pct)}%`} />
        <Metric label="Sell-through" value={`${number(data.economics.sell_through_pct)}%`} />
        <Metric label="7d vs 30d pace" value={trend == null ? "—" : `${trend >= 0 ? "+" : ""}${number(trend)}%`} />
        <Metric label="Oldest inventory" value={data.age.oldest_age_days == null ? "—" : `${data.age.oldest_age_days} days`} />
        <Metric label="Nearest expiry" value={data.age.nearest_expiration_days == null ? "—" : `${data.age.nearest_expiration_days} days`} />
      </div>
      <section className="inventory-panel"><h3>Product identity</h3><div className="catalog-row"><strong>{data.product.name}</strong><span>{data.product.sku || "No SKU"} · {data.product.upc || "No UPC"}</span><small>{[profile?.brand, profile?.category, profile?.subcategory, profile?.strain, profile?.product_format].filter(Boolean).join(" · ") || data.product.item_type}</small></div>{profile?.description ? <p>{profile.description}</p> : null}</section>
    </div> : null}

    {tab === "inventory" ? <div>
      <div className="metrics">
        <Metric label="On hand" value={`${number(data.inventory.on_hand)} ${data.product.base_unit}`} />
        <Metric label="Reserved" value={`${number(data.inventory.reserved)} ${data.product.base_unit}`} />
        <Metric label="Available" value={`${number(data.inventory.available_after_reserved)} ${data.product.base_unit}`} />
        <Metric label="Last received" value={data.age.last_received_date || "—"} />
      </div>
      <div className="table-wrap"><table><thead><tr><th>Package</th><th>Location</th><th>Balance</th><th>Reserved</th><th>Available</th><th>Received</th><th>Expiry</th><th>Status</th></tr></thead><tbody>{packages.map(row => <tr key={row.id} className={row.id === focusPackageId ? "selected-row" : ""}><td><strong>{row.package_id || row.lot_code}</strong><br/><small>{row.source_name || row.lot_code}</small></td><td>{row.location || "—"}</td><td>{number(row.balance)} {row.unit}</td><td>{number(row.reserved)} {row.unit}</td><td>{number(Math.max(0, row.balance - row.reserved))} {row.unit}</td><td>{date(row.received_at)}</td><td>{date(row.expiration_at)}</td><td><span className="badge">{row.status || "—"}</span></td></tr>)}</tbody></table></div>
    </div> : null}

    {tab === "sales" ? <div>
      <div className="metrics">{[7, 30, 60, 90].map(daysWindow => { const window = data.sales.windows[String(daysWindow)] ?? { quantity: 0, net_sales: 0 }; return <Metric key={daysWindow} label={`${daysWindow}-day sales`} value={`${number(window.quantity, 0)} units`} note={money(window.net_sales)} />; })}</div>
      <section className="inventory-panel"><h3>Velocity & trend</h3><div className="catalog-row"><strong>{number(data.sales.daily_velocity, 2)} units/day</strong><span>{trend == null ? "Trend unavailable" : `${trend >= 0 ? "+" : ""}${number(trend)}% vs 30-day pace`}</span><small>{data.sales.source}</small></div></section>
    </div> : null}

    {tab === "purchasing" ? <div>
      <div className="metrics">
        <Metric label="Recommended units" value={number(data.decision.target_units, 0)} />
        <Metric label="Reorder cost" value={money(data.economics.estimated_reorder_cost)} />
        <Metric label="Reorder retail" value={money(data.economics.estimated_reorder_retail_value)} />
        <Metric label="Projected GP" value={money(data.economics.estimated_reorder_gross_profit)} />
      </div>
      <section className="inventory-panel"><h3>Open orders</h3>{data.open_orders.length ? <div className="table-wrap"><table><thead><tr><th>Order</th><th>Type</th><th>Status</th><th>Ordered</th><th>Fulfilled</th></tr></thead><tbody>{data.open_orders.map(row => <tr key={row.id}><td>{row.order_number}</td><td>{row.order_type}</td><td><span className="badge">{row.status}</span></td><td>{number(row.quantity)} {row.unit}</td><td>{number(row.fulfilled_quantity)} {row.unit}</td></tr>)}</tbody></table></div> : <div className="empty">No open commercial orders for this product.</div>}</section>
      {data.production_orders.length ? <section className="inventory-panel"><h3>Production demand</h3>{data.production_orders.map(row => <div className="catalog-row" key={row.id}><strong>{row.order_number}</strong><span>{row.status} · {number(row.requested_units, 0)} units</span><small>{row.product_format || "Production order"} · due {date(row.due_at)}</small></div>)}</section> : null}
      <button className="primary submit" type="button" onClick={stagePo}>{data.decision.target_units > 0 ? "Add / update in PO" : "Open PO Builder"}</button>
    </div> : null}

    {tab === "packages" ? <div>
      {focused ? <div className="metrics"><Metric label="Focused package" value={focused.package_id || focused.lot_code} /><Metric label="Balance" value={`${number(focused.balance)} ${focused.unit}`} /><Metric label="Available" value={`${number(Math.max(0, focused.balance - focused.reserved))} ${focused.unit}`} /><Metric label="Location" value={focused.location || "—"} /></div> : null}
      <div className="table-wrap"><table><thead><tr><th>Package / lot</th><th>Balance</th><th>Location</th><th>Lab</th><th>COA</th><th>Age / expiry</th></tr></thead><tbody>{packages.map(row => <tr key={row.id} className={row.id === focusPackageId ? "selected-row" : ""}><td><strong>{row.package_id || row.lot_code}</strong><br/><small>{row.lot_code}</small></td><td>{number(row.balance)} {row.unit}</td><td>{row.location || "—"}</td><td>{row.lab_status || "—"}</td><td>{row.coa_reference || "—"}</td><td>{date(row.received_at)} → {date(row.expiration_at)}</td></tr>)}</tbody></table></div>
    </div> : null}

    {tab === "compliance" ? <div>
      <div className="metrics"><Metric label="Inventory status" value={data.compliance.status || "—"} /><Metric label="Lab status" value={data.compliance.lab_status || "—"} /><Metric label="External mappings" value={number(data.mappings.length, 0)} /><Metric label="Aliases" value={number(data.aliases.length, 0)} /></div>
      <section className="inventory-panel"><h3>External mappings</h3>{data.mappings.length ? data.mappings.map((row, index) => <div className="catalog-row" key={`${row.system_name}-${row.external_id}-${index}`}><strong>{row.system_name}</strong><span>{row.external_id}</span><small>{row.external_name || "—"}</small></div>) : <div className="empty">No external mappings recorded.</div>}</section>
      <section className="inventory-panel"><h3>Aliases</h3><div className="chip-list">{data.aliases.length ? data.aliases.map((row, index) => <span className="badge" key={`${row.alias}-${index}`}>{row.alias} · {row.source}</span>) : <span>No aliases recorded.</span>}</div></section>
      <button className="secondary submit" type="button" onClick={() => navigate("Integrations")}>Open traceability</button>
    </div> : null}

    {tab === "audits" ? <div>
      <section className="inventory-panel"><h3>Audit this SKU</h3><p>Keep the current Product 360 / Package 360 context and open the durable scan-audit workflow.</p><div className="catalog-row"><strong>{data.product.name}</strong><span>{data.product.sku || "No SKU"}</span><small>{focusPackageId ? `Focused package ${focused?.package_id || focused?.lot_code || focusPackageId}` : `${data.inventory.package_count} package(s) in this facility`}</small></div><button className="primary submit" type="button" onClick={audit}>Audit this SKU</button></section>
    </div> : null}

    {tab === "master" ? <div>
      <div className="metrics"><Metric label="Unit cost" value={money(data.economics.unit_cost)} /><Metric label="Retail price" value={money(data.economics.retail_price)} /><Metric label="Manufacturer" value={profile?.manufacturer || "—"} /><Metric label="Format" value={profile?.product_format || data.product.item_type} /></div>
      <section className="inventory-panel"><h3>Cost / price history</h3>{data.value_history.length ? <div className="table-wrap"><table><thead><tr><th>Type</th><th>Amount</th><th>Effective</th></tr></thead><tbody>{data.value_history.map((row, index) => <tr key={`${row.value_type}-${row.effective_at}-${index}`}><td>{row.value_type.replaceAll("_", " ")}</td><td>{row.currency} {number(row.amount, 2)}</td><td>{date(row.effective_at)}</td></tr>)}</tbody></table></div> : <div className="empty">No value history recorded.</div>}</section>
    </div> : null}

    {tab === "lineage" && lineage ? <div className="lineage">
      <section><h3>Created from</h3>{lineage.created_by ? <><div className="run-chip">{lineage.created_by.run_number} · {lineage.created_by.action_type}</div>{lineage.created_by.parents.map(parent => <article key={parent.lot_id}><strong>{parent.product_name || parent.lot_code}</strong><span>{parent.lot_code} · {parent.quantity} {parent.unit}</span></article>)}</> : <p>Opening or received package—no parent transformation.</p>}</section>
      <div className="lineage-current"><strong>{lineage.lot.product_name}</strong><span>{lineage.lot.compliance_package_id || lineage.lot.lot_code}</span><b>{lineage.lot.balance} {lineage.lot.unit}</b></div>
      <section><h3>Used by</h3>{lineage.used_by.map(run => <article key={`${run.run_number}-${run.quantity_consumed}`}><strong>{run.run_number} · {run.action_type}</strong><span>Consumed {run.quantity_consumed} {run.unit}</span>{run.outputs.map(output => <small key={`${output.lot_code}-${output.purpose}`}>→ {output.lot_code} · {output.inventory_quantity} {output.inventory_unit} {output.purpose ? `· ${output.purpose}` : ""}</small>)}</article>)}{lineage.used_by.length === 0 ? <p>Not consumed by a later transformation.</p> : null}</section>
    </div> : null}
  </div>;
}

export function Product360Dialog({ productId, onClose }: { productId: string; onClose: () => void }) {
  const snapshot = useQuery({ queryKey: ["product-360", productId], queryFn: ({ signal }) => apiGet<Product360Snapshot>(`/api/v1/product-360/${productId}`, signal), enabled: Boolean(productId) });
  return <StreamlitDialog open onClose={onClose} eyebrow="Retail Product 360" title={snapshot.data?.product.name || "Product 360"} subtitle={snapshot.data ? `${snapshot.data.product.sku || "No SKU"} · ${snapshot.data.profile?.brand || snapshot.data.profile?.category || snapshot.data.product.item_type}` : "Loading the complete operating picture…"}>
    {snapshot.isLoading ? <div className="state">Loading Product 360…</div> : null}
    {snapshot.error ? <div className="state error">{snapshot.error.message}</div> : null}
    {snapshot.data ? <Product360Workspace data={snapshot.data} /> : null}
  </StreamlitDialog>;
}

export type { Product360Snapshot };
