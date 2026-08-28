import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import { ProductionRegulatoryHealth } from "./ProductionRegulatoryHealth";

type QueueRow = {
  order_id: string;
  Order: string;
  Product: string;
  Status: string;
  Planned: number;
  Actual: number;
  "Attainment %": number;
  COGS: number;
  "Cost / Unit": number;
  Reservations: number;
  QA: string;
  Attention: string;
};

type Action = {
  key: string;
  priority: "high" | "medium" | "low";
  label: string;
  reason: string;
  row: QueueRow;
};

export function ProductionNextActions({ onOpenRun }: { onOpenRun: (orderId: string) => void }) {
  const queue = useQuery({ queryKey: ["production-run-queue"], queryFn: ({ signal }) => apiGet<QueueRow[]>("/api/v1/production/orders", signal) });
  const actions = (queue.data ?? []).flatMap<Action>((row) => {
    const items: Action[] = [];
    if (row.QA === "HOLD" || row.Attention === "QA HOLD") items.push({ key: `qa-${row.order_id}`, priority: "high", label: "Review QA hold", reason: "This run is blocked from release by QA.", row });
    if (row.Attention === "Material shortage") items.push({ key: `materials-${row.order_id}`, priority: "high", label: "Resolve material blocker", reason: "Required BOM material is not reserved for this run.", row });
    if (row.Status.toLowerCase() === "on hold") items.push({ key: `hold-${row.order_id}`, priority: "medium", label: "Review held run", reason: "The run is on hold and needs an operator decision before it can continue.", row });
    if (row.Status.toLowerCase() === "in progress" && row.Planned > 0 && row.Actual < row.Planned) items.push({ key: `progress-${row.order_id}`, priority: "low", label: "Continue run execution", reason: `${number(row.Actual)} of ${number(row.Planned)} planned output has been recorded.`, row });
    return items;
  }).sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority) || a.row.Order.localeCompare(b.row.Order)).slice(0, 8);

  return <>
    <section className="inventory-panel production-next-actions">
      <div className="section-heading"><div><div className="eyebrow">Production Today</div><h3>Next Actions</h3><p className="source-caption">Generated from Run 360 state. Select an action to work the exact production run.</p></div><span className="badge">{actions.length}</span></div>
      {queue.isLoading ? <div className="state">Checking production run state…</div> : null}
      {queue.isError ? <div className="state error">Production next actions could not load: {queue.error.message}</div> : null}
      {!queue.isLoading && !queue.isError && actions.length === 0 ? <div className="empty">No production exceptions need attention right now.</div> : null}
      {actions.length ? <div className="table-wrap"><table><thead><tr><th>Priority</th><th>Run</th><th>Action</th><th>Why</th></tr></thead><tbody>{actions.map((action) => <tr key={action.key} onClick={() => onOpenRun(action.row.order_id)}><td><span className="badge">{action.priority}</span></td><td><strong>{action.row.Order}</strong><br/><small>{action.row.Product} · {action.row.Status}</small></td><td>{action.label}</td><td>{action.reason}</td></tr>)}</tbody></table></div> : null}
    </section>
    <ProductionRegulatoryHealth />
  </>;
}

function priorityRank(value: Action["priority"]) { return value === "high" ? 0 : value === "medium" ? 1 : 2; }
function number(value: number) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 }); }