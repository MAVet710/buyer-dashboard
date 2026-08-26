import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { apiGet } from "../lib/api";
import { Product360Drawer } from "./Product360Drawer";

type SearchResult = { kind: string; id: string; title: string; subtitle: string; workspace: string };

const tools: SearchResult[] = [
  { kind: "tool", id: "enterprise-control-tower", title: "Enterprise Control Tower", subtitle: "Rank every facility by inventory, order, production, traceability, compliance, and A/R risk", workspace: "Enterprise Control Tower" },
  { kind: "tool", id: "control-tower", title: "Operations Control Tower", subtitle: "Doobie actions, traceability, LabelGuard, SOP controls, profitability, cultivation, machines, and commerce", workspace: "Operations Control Tower" },
  { kind: "tool", id: "package-360", title: "Package 360", subtitle: "Scan a package or lot and follow inventory, lineage, audits, orders, production, and traceability in one timeline", workspace: "Package 360" },
  { kind: "tool", id: "warehouse-pick-pack", title: "Warehouse Pick Pack", subtitle: "Mobile FEFO pick queue with package scan verification, reservation, and shipment posting", workspace: "Warehouse Pick Pack" },
  { kind: "tool", id: "production-run-360", title: "Production Run 360", subtitle: "BOM reservations, actual outputs, yield, waste, QA release, execution evidence, and true run COGS", workspace: "Production Run 360" },
  { kind: "tool", id: "traceability-actions", title: "Traceability Actions", subtitle: "Validate and queue typed Metrc, BioTrack, package, transfer, production, plant, lab, sales, and waste intents", workspace: "Traceability Actions" },
  { kind: "tool", id: "inventory", title: "Inventory", subtitle: "Stock health, reorder risk, aging, package 360, and audit actions", workspace: "Inventory" },
  { kind: "tool", id: "retail-product-360", title: "Retail Product 360", subtitle: "Inventory, sales, velocity, purchasing, packages, compliance, audits, and economics", workspace: "Retail Product 360" },
  { kind: "tool", id: "retail-product-master", title: "Retail Product Master", subtitle: "Open the operational Product 360 workspace; catalog administration remains available inside it", workspace: "Retail Product Master" },
  { kind: "tool", id: "retail-catalog-admin", title: "Retail Catalog Administration", subtitle: "Retail catalog identity, vendors, mappings, aliases, and values", workspace: "Retail Catalog Admin" },
  { kind: "tool", id: "production-product-master", title: "Production Product Master", subtitle: "Bulk material, WIP, and production catalog identity", workspace: "Production Product Master" },
  { kind: "tool", id: "inventory-audits", title: "Inventory Audits", subtitle: "Camera scan, Bluetooth/USB, pause, resume, stop, partial reports, and reconciliation", workspace: "Inventory Audits" },
  { kind: "tool", id: "buyer-operations", title: "Purchasing / Buyer Command Center", subtitle: "Buyer Dashboard KPIs, forecasts, SKU intelligence, recommendations, and purchasing decisions", workspace: "Buyer Operations" },
  { kind: "tool", id: "buying-recommendations", title: "Buying Recommendations", subtitle: "Buyer Intelligence recommendations and risks", workspace: "Buying Recommendations" },
  { kind: "tool", id: "purchase-orders", title: "Purchase Orders", subtitle: "Build and review purchase orders", workspace: "Purchase Orders" },
  { kind: "tool", id: "buying-budget", title: "Buying Budget", subtitle: "Purchasing budget and committed spend", workspace: "Buying Budget" },
  { kind: "tool", id: "orders", title: "Orders", subtitle: "Customer orders and fulfillment", workspace: "Orders" },
  { kind: "tool", id: "extraction", title: "Extraction Command Center", subtitle: "Run 360, process tracking, inputs, outputs, QA, COGS, traceability, toll processing, and analytics", workspace: "Extraction" },
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
      <label className="home-search"><Search size={19}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search products, packages, plants, orders, partners, or tools…" aria-label="Search DoobieLogic"/></label>
      {query.trim().length >= 2 ? <div className="global-search-results">
        {remote.isLoading ? <div className="state">Searching active facility…</div> : null}
        {results.map(row => <button key={`${row.kind}-${row.id}`} type="button" onClick={() => choose(row)}><span className="badge">{row.kind}</span><strong>{row.title}</strong><em>{row.kind === "product" ? "Product 360 →" : `${row.workspace} →`}</em><small>{row.subtitle}</small></button>)}
        {!remote.isLoading && results.length === 0 ? <div className="empty">No matching records or tools.</div> : null}
      </div> : null}
    </div>
    <Product360Drawer productId={productId} open={Boolean(productId)} onClose={() => setProductId("")} onNavigate={onNavigate}/>
  </>;
}
