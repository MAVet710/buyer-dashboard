import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import type { InventoryPackage, PackageLineage as Lineage } from "../types/inventory";
import { Product360Workspace, type Product360Snapshot } from "./Product360Workspace";
import { StreamlitDialog } from "./StreamlitDialog";

export function PackageLineage({ operation, item, onClose }: { operation: "retail" | "production"; item: InventoryPackage; onClose: () => void }) {
  const trail = useQuery({
    queryKey: ["package-lineage", operation, item.id],
    queryFn: ({ signal }) => apiGet<Lineage>(`/api/v1/inventory/${operation}/packages/${item.id}/lineage`, signal),
  });
  const product = useQuery({
    queryKey: ["package-360-product", operation, item.id],
    queryFn: ({ signal }) => apiGet<Product360Snapshot>(`/api/v1/product-360/by-lot/${item.id}`, signal),
  });
  const loading = trail.isLoading || product.isLoading;
  const error = trail.error || product.error;

  return <StreamlitDialog open onClose={onClose} eyebrow="PACKAGE 360 · inventory + product + lineage" title={item.product_name} subtitle={`${item.package_id} · ${item.available.toLocaleString()} ${item.unit} · ${item.location || "No location"}`}>
    {loading ? <div className="state">Loading full Package 360 context…</div> : null}
    {error ? <div className="state error">{error.message}</div> : null}
    {product.data ? <Product360Workspace data={product.data} initialTab="packages" focusPackageId={item.id} lineage={trail.data ?? null} /> : null}
  </StreamlitDialog>;
}
