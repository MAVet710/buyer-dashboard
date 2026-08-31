import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import type { InventoryReceiptHistoryItem } from "../types/inventory";
import { InventoryTransferManager } from "./InventoryTransferManager";
import { StreamlitDialog } from "./StreamlitDialog";

export function ReceiveHistory({ operation, onClose }: { operation: "retail" | "production"; onClose: () => void }) {
  const [transfers,setTransfers]=useState(false);
  const [flash,setFlash]=useState("");
  const history = useQuery({
    queryKey: ["inventory-receive-history", operation],
    queryFn: ({ signal }) => apiGet<InventoryReceiptHistoryItem[]>(`/api/v1/inventory/${operation}/receive-history`, signal),
  });
  if(transfers)return <InventoryTransferManager operation={operation} packages={[]} onClose={()=>setTransfers(false)} onSaved={message=>{setFlash(message);void history.refetch();}}/>;
  return <StreamlitDialog open onClose={onClose} eyebrow={`${operation === "production" ? "Production" : "Retail"} inventory`} title="Receive history" subtitle="Facility-scoped durable receipts and cross-license transfer journal">
    {flash?<div className="success-banner">{flash}</div>:null}
    <div className="audit-actions"><button className="primary" onClick={()=>setTransfers(true)}>License transfers</button></div>
    <div className="info-banner"><strong>Cross-license inventory moves have their own durable genealogy.</strong> Open License transfers to dispatch, receive, cancel before receipt, or review state-system-confirmed movements between facilities.</div>
    {history.isLoading ? <div className="state">Loading receive history…</div> : null}
    {history.error ? <div className="state error">{history.error.message}</div> : null}
    {history.data ? <div className="table-wrap"><table><thead><tr><th>Received</th><th>Product</th><th>Package</th><th>Quantity</th><th>Source</th><th>Manifest</th><th>Actor</th></tr></thead><tbody>{history.data.map(item => <tr key={item.transaction_id}><td>{new Date(item.received_at).toLocaleString()}</td><td>{item.product_name}</td><td>{item.package_id}</td><td>{item.quantity.toLocaleString()} {item.unit}</td><td>{item.source_name || "—"}</td><td>{item.manifest_reference || "—"}</td><td>{item.actor}</td></tr>)}</tbody></table>{history.data.length === 0 ? <div className="empty">No {operation} receipts recorded for this facility.</div> : null}</div> : null}
  </StreamlitDialog>;
}
