import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import type { InventoryReceiptHistoryItem } from "../types/inventory";

export function ReceiveHistory({ operation, onClose }: { operation: "retail" | "production"; onClose: () => void }) {
  const history = useQuery({
    queryKey: ["receive-history", operation],
    queryFn: ({ signal }) => apiGet<InventoryReceiptHistoryItem[]>(`/api/v1/inventory/${operation}/receive-history`, signal),
  });
  return <div className="modal-backdrop" role="presentation"><section className="modal wide" role="dialog" aria-modal="true" aria-label="Receive history">
    <div className="modal-heading"><div><div className="eyebrow">{operation} inventory</div><h2>Receive history</h2></div><button className="secondary" onClick={onClose}>Close</button></div>
    {history.isLoading ? <div className="state">Loading receive history…</div> : null}
    {history.error ? <div className="state error">{history.error.message}</div> : null}
    {history.data ? <div className="table-wrap"><table><thead><tr><th>Received</th><th>Product</th><th>Package</th><th>Quantity</th><th>Source</th><th>Manifest</th><th>Actor</th></tr></thead><tbody>{history.data.map(item => <tr key={item.transaction_id}><td>{new Date(item.received_at).toLocaleString()}</td><td>{item.product_name}</td><td>{item.package_id}</td><td>{item.quantity.toLocaleString()} {item.unit}</td><td>{item.source_name || "—"}</td><td>{item.manifest_reference || "—"}</td><td>{item.actor}</td></tr>)}</tbody></table>{history.data.length === 0 ? <div className="empty">No receipts recorded for this facility.</div> : null}</div> : null}
  </section></div>;
}
