import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { AuditDetail, AuditSummary } from "../types/inventory";
import { StreamlitDialog } from "./StreamlitPrimitives";

export function InventoryAudits({ operation, onClose }: { operation: "retail" | "production"; onClose: () => void }) {
  const client = useQueryClient();
  const [selectedId, setSelectedId] = useState("");
  const [number, setNumber] = useState(`${operation === "retail" ? "RTL" : "PRD"}-${new Date().toISOString().slice(0,10).replaceAll("-", "")}`);
  const [counts, setCounts] = useState<Record<string, string>>({});
  const audits = useQuery({ queryKey: ["audits", operation], queryFn: ({ signal }) => apiGet<AuditSummary[]>(`/api/v1/inventory/${operation}/audits`, signal) });
  const detail = useQuery({ queryKey: ["audit", operation, selectedId], enabled: !!selectedId, queryFn: ({ signal }) => apiGet<AuditDetail>(`/api/v1/inventory/${operation}/audits/${selectedId}`, signal) });
  const refresh = async () => { await client.invalidateQueries({ queryKey: ["audits", operation] }); await client.invalidateQueries({ queryKey: ["audit", operation, selectedId] }); };
  const create = useMutation({ mutationFn: () => apiPost<AuditSummary>(`/api/v1/inventory/${operation}/audits`, { audit_number: number, blind_count: true, recount_tolerance: 0, scope_label: "Full facility" }), onSuccess: async audit => { setSelectedId(audit.id); await refresh(); } });
  const save = useMutation({ mutationFn: () => apiPost(`/api/v1/inventory/${operation}/audits/${selectedId}/counts`, { counts: Object.entries(counts).filter(([, value]) => value !== "").map(([line_id, value]) => ({ line_id, counted_quantity: Number(value), reason: "Physical count" })) }), onSuccess: refresh });
  const transition = useMutation({ mutationFn: (status: string) => apiPost(`/api/v1/inventory/${operation}/audits/${selectedId}/status`, { status }), onSuccess: refresh });
  const complete = useMutation({ mutationFn: (post_adjustments: boolean) => apiPost(`/api/v1/inventory/${operation}/audits/${selectedId}/complete`, { post_adjustments }), onSuccess: refresh });
  const current = detail.data;
  return <StreamlitDialog title="Inventory audits" subtitle={`${operation} inventory control`} onClose={onClose} size="wide">
    <div className="audit-layout"><aside className="audit-list">
      <div className="new-audit"><input value={number} onChange={e => setNumber(e.target.value)} /><button className="primary" disabled={!number || create.isPending} onClick={() => create.mutate()}>Start audit</button></div>
      {audits.data?.map(audit => <button key={audit.id} className={selectedId === audit.id ? "audit-card active" : "audit-card"} onClick={() => { setSelectedId(audit.id); setCounts({}); }}><strong>{audit.audit_number}</strong><span>{audit.scope_label}</span><small>{audit.status.replaceAll("_", " ")}</small></button>)}
    </aside><div className="audit-detail">
      {!selectedId ? <div className="state">Select an audit or start a new one.</div> : null}
      {current ? <><div className="audit-toolbar"><div><strong>{current.audit.audit_number}</strong><span>{current.audit.status.replaceAll("_", " ")} · {current.lines.length} packages</span></div><div>{["draft", "paused", "stopped"].includes(current.audit.status) ? <button className="secondary" onClick={() => transition.mutate("in_progress")}>Resume</button> : null}{current.audit.status === "in_progress" ? <><button className="secondary" onClick={() => transition.mutate("paused")}>Pause</button><button className="secondary" onClick={() => transition.mutate("stopped")}>Stop</button></> : null}</div></div>
        <div className="table-wrap audit-table"><table><thead><tr><th>Product</th><th>Package</th><th>Location</th><th>Expected</th><th>Physical count</th><th>Variance</th></tr></thead><tbody>{current.lines.map(line => <tr key={line.id}><td>{line.product_name}</td><td>{line.package_id}</td><td>{line.location}</td><td>{line.expected_quantity == null ? "Blind" : `${line.expected_quantity} ${line.unit}`}</td><td><input type="number" min="0" value={counts[line.id] ?? line.counted_quantity ?? ""} disabled={["completed", "cancelled"].includes(current.audit.status)} onChange={e => setCounts({ ...counts, [line.id]: e.target.value })} /></td><td className={line.recount_required ? "variance-alert" : ""}>{line.counted_quantity == null ? "—" : `${line.variance_quantity > 0 ? "+" : ""}${line.variance_quantity}`}</td></tr>)}</tbody></table></div>
        {!(["completed", "cancelled"].includes(current.audit.status)) ? <div className="audit-actions"><button className="secondary" disabled={!Object.keys(counts).length || save.isPending} onClick={() => save.mutate()}>Save counts</button><button className="secondary" onClick={() => complete.mutate(false)}>Complete without adjustments</button><button className="primary" onClick={() => complete.mutate(true)}>Complete & reconcile</button></div> : null}
      </> : null}
    </div></div>
  </StreamlitDialog>;
}
