import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Product360Drawer } from "../components/Product360Drawer";
import { apiGet } from "../lib/api";

type Product = {
  id: string;
  sku: string;
  name: string;
  item_type: string;
  base_unit: string;
  unit_cost: number;
  retail_price: number;
  upc: string;
  active: boolean;
  brand: string;
  category: string;
  product_format: string;
};

export function RetailProduct360Page({ onNavigate }: { onNavigate: (page: string) => void }) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  const products = useQuery({
    queryKey: ["retail-product-360-list", search],
    queryFn: ({ signal }) => apiGet<Product[]>(`/api/v1/product-master?operation=retail&status=active&search=${encodeURIComponent(search)}`, signal),
  });
  const rows = useMemo(() => products.data ?? [], [products.data]);
  const missingClassification = rows.filter(row => !row.category).length;
  const withPricing = rows.filter(row => Number(row.retail_price || 0) > 0).length;

  return <div className="page">
    <div className="page-heading">
      <div>
        <div className="eyebrow">Retail Ops · operational intelligence</div>
        <h1>Product 360</h1>
        <p>Open the same product-level operating picture from Buyer Dash: inventory, velocity, sales windows, purchasing, packages, compliance, audit actions, economics and durable catalog identity.</p>
      </div>
    </div>
    <div className="metrics">
      <div className="metric"><span>Active products</span><strong>{rows.length}</strong></div>
      <div className="metric"><span>Priced</span><strong>{withPricing}</strong></div>
      <div className="metric"><span>Needs classification</span><strong>{missingClassification}</strong></div>
      <div className="metric"><span>Workspace</span><strong>Retail 360</strong></div>
    </div>
    <section className="inventory-panel">
      <div className="filters">
        <label className="search"><input aria-label="Search Retail Product 360" placeholder="Search product, SKU, UPC, brand or category" value={search} onChange={event => setSearch(event.target.value)} /></label>
      </div>
      {products.isLoading ? <div className="state">Loading retail products…</div> : null}
      {products.isError ? <div className="state error">{products.error.message}</div> : null}
      <div className="table-wrap"><table><thead><tr><th>Product</th><th>SKU / UPC</th><th>Brand</th><th>Category</th><th>Format</th><th>Retail / cost</th><th>360</th></tr></thead><tbody>
        {rows.map(row => <tr key={row.id} className="selectable-row" onClick={() => setSelected(row.id)}>
          <td><strong>{row.name}</strong><br/><small>{row.item_type.replaceAll("_", " ")}</small></td>
          <td>{row.sku || "—"}<br/><small>{row.upc || "No UPC"}</small></td>
          <td>{row.brand || "—"}</td>
          <td>{row.category || "Needs setup"}</td>
          <td>{row.product_format || "—"}</td>
          <td>${Number(row.retail_price || 0).toFixed(2)} / ${Number(row.unit_cost || 0).toFixed(2)}</td>
          <td><button className="secondary" type="button" onClick={event => { event.stopPropagation(); setSelected(row.id); }}>Open 360</button></td>
        </tr>)}
      </tbody></table>{!products.isLoading && !rows.length ? <div className="empty">No active retail products match this search.</div> : null}</div>
    </section>
    <Product360Drawer productId={selected} open={Boolean(selected)} onClose={() => setSelected("")} onNavigate={onNavigate} />
  </div>;
}
