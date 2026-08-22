import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import type { InventoryPackage, PackageLineage as Lineage } from "../types/inventory";
import { StreamlitDialog } from "./StreamlitPrimitives";

export function PackageLineage({ operation, item, onClose }: { operation: "retail" | "production"; item: InventoryPackage; onClose: () => void }) {
  const trail = useQuery({ queryKey: ["package-lineage", item.id], queryFn: ({ signal }) => apiGet<Lineage>(`/api/v1/inventory/${operation}/packages/${item.id}/lineage`, signal) });
  return <StreamlitDialog title={item.product_name} subtitle="Package 360" onClose={onClose}>
    <p className="dialog-context">{item.package_id} · {item.available.toLocaleString()} {item.unit}</p>
    {trail.isLoading ? <div className="state">Loading source trail…</div> : null}{trail.error ? <div className="state error">{trail.error.message}</div> : null}
    {trail.data ? <div className="lineage"><section><h3>Created from</h3>{trail.data.created_by ? <><div className="run-chip">{trail.data.created_by.run_number} · {trail.data.created_by.action_type}</div>{trail.data.created_by.parents.map(parent => <article key={parent.lot_id}><strong>{parent.product_name || parent.lot_code}</strong><span>{parent.lot_code} · {parent.quantity} {parent.unit}</span></article>)}</> : <p>Opening or received package—no parent transformation.</p>}</section><div className="lineage-current"><strong>{trail.data.lot.product_name}</strong><span>{trail.data.lot.lot_code}</span><b>{trail.data.lot.balance} {trail.data.lot.unit}</b></div><section><h3>Used by</h3>{trail.data.used_by.map(run => <article key={`${run.run_number}-${run.quantity_consumed}`}><strong>{run.run_number} · {run.action_type}</strong><span>Consumed {run.quantity_consumed} {run.unit}</span>{run.outputs.map(output => <small key={output.lot_code}>→ {output.lot_code} · {output.inventory_quantity} {output.inventory_unit}</small>)}</article>)}{trail.data.used_by.length === 0 ? <p>Not consumed by a later transformation.</p> : null}</section></div> : null}
  </StreamlitDialog>;
}
