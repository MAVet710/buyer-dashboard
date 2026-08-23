import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { apiGet } from "../lib/api";
import { Product360Drawer } from "./Product360Drawer";

type SearchResult = { kind: string; id: string; title: string; subtitle: string; workspace: string };

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
