import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { apiGet } from "../lib/api";
import { StreamlitDialog } from "./StreamlitDialog";

type SearchResult = { kind: string; id: string; title: string; subtitle: string; workspace: string };
type Product360 = {
  product: { id: string; sku: string; name: string; item_type: string; base_unit: string; unit_cost: number; retail_price: number; upc: string };
  profile: { brand: string; category: string; subcategory?: string; strain: string; product_format: string; description: string } | null;
  inventory: { packages: { id: string; package_id: string; location: string; status: string; balance: number; unit: string; received_at?: string; expiration_at?: string }[]; on_hand: number; package_count: number };
  sales_30d: { quantity: number; net_sales: number; daily_velocity: number };
  open_orders: { id: string; order_number: string; order_type: string; status: string; quantity: number; fulfilled_quantity: number; unit: string }[];
  production_orders: { id: string; order_number: string; status: string; requested_units: number; due_at: string | null; product_format: string }[];
  aliases: { alias: string; source: string }[];
  mappings: { system_name: string; external_id: string; external_name: string }[];
  value_history: { value_type: string; amount: number; currency: string; effective_at: string }[];
};

const tools: SearchResult[] = [
  { kind: "tool", id: "inventory", title: "Inventory", subtitle: "Stock health, reorder risk, and aging", workspace: "Inventory" },
  { kind: "tool", id: "retail-product-master", title: "Retail Product Master", subtitle: "Retail catalog identity, vendors, mappings, aliases, and values", workspace: "Retail Product Master" },
  { kind: "tool", id: "production-product-master", title: "Production Product Master", subtitle: "Bulk material, WIP, and production catalog identity", workspace: "Production Product Master" },
  { kind: "tool", id: "inventory-audits", title: "Inventory Audits", subtitle: "Scan, pause, resume, and reconcile counts", workspace: "Inventory Audits" },
  { kind: "tool", id: "buying-recommendations", title: "Buying Recommendations", subtitle: "Buyer Intelligence recommendations and risks", workspace: "Buying Recommendations" },
  { kind: "tool", id: "purchase-orders", title: "Purchase Orders", subtitle: "Build and review purchase orders", workspace: "Purchase Orders" },
  { kind: "tool", id: "buying-budget", title: "Buying Budget", subtitle: "Purchasing budget and committed spend", workspace: "Buying Budget" },
  { kind: "tool", id: "orders", title: "Orders", subtitle: "Customer orders and fulfillment", workspace: "Orders" },
  { kind: "tool", id: "extraction", title: "Extraction", subtitle: "Extraction runs, yield, QA, and economics", workspace: "Extraction" },
  { kind: "tool", id: "compliance-qa", title: "Compliance Q&A", subtitle: "Reviewed compliance source workflow", workspace: "Compliance Q&A" },
  { kind: "tool", id: "metrc", title: "METRC", subtitle: "Traceability connections and reconciliation", workspace: "Integrations" },
  { kind: "tool", id: "name-mapper", title: "Product Name Mapper", subtitle: "Map METRC items to facility nomenclature", workspace: "Product Name Mapper" },
  { kind: "tool", id: "data", title: "Imports & Data", subtitle: "Upload, map, review, and publish operational files", workspace: "Data & Settings" },
  { kind: "tool", id: "home", title: "Home", subtitle: "Role-aware operations command center", workspace: "Home" },
];

export function GlobalSearch({ onNavigate }: { onNavigate: (page: string) => void }) {
  const [query, setQuery] = useState("");
  const [productId, setProductId] = useState("");
  const remote = useQuery({
    queryKey: ["global-search", query],
    enabled: query.trim().length >= 2,
    queryFn: ({ signal }) => apiGet<SearchResult[]>(`/api/v1/home/search?q=${encodeURIComponent(query.trim())}`, signal),
  });
  const product = useQuery({
    queryKey: ["global-product-360", productId],
    enabled: Boolean(productId),
    queryFn: ({ signal }) => apiGet<Product360>(`/api/v1/home/products/${productId}`, signal),
  });
  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle.length < 2) return [];
    const local = tools.filter(row => `${row.title} ${row.subtitle}`.toLowerCase().includes(needle));
    return [...(remote.data ?? []), ...local].slice(0, 12);
  }, [query, remote.data]);
  const choose = (row: SearchResult) => {
    if (row.kind === "product") setProductId(row.id);
    else onNavigate(row.workspace);
    setQuery("");
  };

  return <>
    <div className="global-search-shell">
      <label className="home-search"><Search size={19}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search products, packages, plants, orders, partners, or tools…" aria-label="Search Buyer Dash"/></label>
      {query.trim().length >= 2 ? <div className="global-search-results">
        {remote.isLoading ? <div className="state">Searching active facility…</div> : null}
        {results.map(row => <button key={`${row.kind}-${row.id}`} type="button" onClick={() => choose(row)}><span className="badge">{row.kind}</span><strong>{row.title}</strong><em>{row.kind === "product" ? "Product 360 →" : `${row.workspace} →`}</em><small>{row.subtitle}</small></button>)}
        {!remote.isLoading && results.length === 0 ? <div className="empty">No matching records or tools.</div> : null}
      </div> : null}
    </div>
    <StreamlitDialog open={Boolean(productId)} onClose={() => setProductId("")} eyebrow="Product 360" title={product.data?.product.name ?? "Loading product…"} subtitle={product.data ? `${product.data.product.sku} · ${product.data.profile?.brand || "No brand"} · ${product.data.profile?.category || product.data.product.item_type}` : "Cross-workspace context"} footer={product.data ? <><button className="secondary" type="button" onClick={() => { setProductId(""); onNavigate("Inventory"); }}>Open inventory</button><button className="primary" type="button" onClick={() => { setProductId(""); onNavigate("Retail Product Master"); }}>Open Product Master</button></> : null}>
      {product.isLoading ? <div className="state">Loading durable product context…</div> : null}
      {product.isError ? <div className="state error">{product.error.message}</div> : null}
      {product.data ? <ProductSnapshot data={product.data}/> : null}
    </StreamlitDialog>
  </>;
}

function ProductSnapshot({ data }: { data: Product360 }) {
  return <>
    <section className="quantity-summary"><span>On hand<strong>{data.inventory.on_hand.toLocaleString()} {data.product.base_unit}</strong></span><span>30d sold<strong>{data.sales_30d.quantity.toLocaleString()}</strong></span><span>30d net sales<strong>{money(data.sales_30d.net_sales)}</strong></span></section>
    <h3>Inventory packages</h3>{data.inventory.packages.map(row => <article className="catalog-row" key={row.id}><strong>{row.package_id}</strong><span>{row.balance} {row.unit}</span><small>{row.location} · {row.status}</small></article>)}{!data.inventory.packages.length ? <div className="empty">No packages in this facility.</div> : null}
    <h3>Open demand</h3>{data.open_orders.map(row => <article className="catalog-row" key={row.id}><strong>{row.order_number}</strong><span>{row.quantity - row.fulfilled_quantity} {row.unit}</span><small>{row.order_type} · {row.status}</small></article>)}{data.production_orders.map(row => <article className="catalog-row" key={row.id}><strong>{row.order_number}</strong><span>{row.requested_units} units</span><small>production · {row.status}</small></article>)}{!data.open_orders.length && !data.production_orders.length ? <div className="empty">No open demand.</div> : null}
    <h3>Catalog identity</h3><div className="catalog-row"><strong>UPC</strong><span>{data.product.upc || "—"}</span></div>{data.aliases.map(row => <div className="catalog-row" key={`${row.source}-${row.alias}`}><strong>Alias</strong><span>{row.alias}</span><small>{row.source}</small></div>)}{data.mappings.map(row => <div className="catalog-row" key={`${row.system_name}-${row.external_id}`}><strong>{row.system_name}</strong><span>{row.external_id}</span><small>{row.external_name}</small></div>)}
    <h3>Value history</h3>{data.value_history.slice(0,8).map(row => <div className="catalog-row" key={`${row.value_type}-${row.effective_at}`}><strong>{row.value_type.replaceAll("_"," ")}</strong><span>{money(row.amount)}</span><small>{new Date(row.effective_at).toLocaleString()}</small></div>)}
  </>;
}
function money(value:number){return value.toLocaleString(undefined,{style:"currency",currency:"USD",maximumFractionDigits:2})}
