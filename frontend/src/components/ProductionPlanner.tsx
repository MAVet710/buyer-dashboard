import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

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

type Workspace = {
  machines: { id: string; machine_model_id: string; display_name: string }[];
  machine_models: { id: string; category: string; manufacturer: string; model: string }[];
  crew: { id: string; work_date: string; shift_name: string; available_people: number; shift_hours: number }[];
  products: { id: string; sku: string; name: string; item_type: string; base_unit: string }[];
  lots: { id: string; product_id: string; status: string; on_hand: number }[];
  reservations: { id: string; production_order_id: string; lot_id: string; quantity: number; unit: string; status: string }[];
};

type Requirement = {
  product_id: string;
  product_name: string;
  quantity: number;
  unit: string;
};

type ProductionDetail = {
  order: {
    id: string;
    order_number: string;
    product_name: string;
    requested_units: number;
    priority: string;
    status: string;
    due_at: string | null;
  };
  standard: null | {
    resource_category: string;
    qa_required: boolean;
    compliance_checkpoint: string;
  };
  variance: {
    expected_labor_hours: number;
    expected_machine_hours: number;
    expected_cycle_hours: number;
    resource_category: string;
    qa_required: boolean;
    qa_ready: boolean;
    compliance_checkpoint: string;
    standard_configured: boolean;
  };
  requirements: Requirement[];
};

type PlanData = {
  workspace: Workspace;
  queue: QueueRow[];
  details: ProductionDetail[];
};

type Decision = "CONTINUE" | "RUN NOW" | "RUN NEXT" | "AT RISK" | "BLOCKED";

type PlanRow = {
  orderId: string;
  order: string;
  product: string;
  status: string;
  priority: string;
  dueAt: string | null;
  daysToDue: number | null;
  decision: Decision;
  readiness: number;
  materialState: string;
  laborState: string;
  equipmentState: string;
  reason: string;
};

export function ProductionPlanner({ onOpenRun }: { onOpenRun: (orderId: string) => void }) {
  const plan = useQuery({
    queryKey: ["production-decision-plan"],
    queryFn: ({ signal }) => loadPlan(signal),
  });

  if (plan.isLoading) return <section className="inventory-panel"><div className="state">Building the production plan…</div></section>;
  if (plan.isError) return <section className="inventory-panel"><div className="state error">Production plan could not load: {plan.error.message}</div></section>;
  if (!plan.data) return null;

  const rows = buildPlanRows(plan.data);
  const ready = rows.filter((row) => ["CONTINUE", "RUN NOW", "RUN NEXT"].includes(row.decision)).length;
  const blocked = rows.filter((row) => row.decision === "BLOCKED").length;
  const crewHours = plan.data.workspace.crew.reduce((sum, row) => sum + Number(row.available_people || 0) * Number(row.shift_hours || 0), 0);

  return <section className="inventory-panel production-plan">
    <div className="section-heading">
      <div>
        <div className="eyebrow">Production Planning</div>
        <h3>What should we run next?</h3>
        <p className="source-caption">DoobieLogic ranks the durable production queue from due dates, BOM material coverage, reservations, labor, equipment, QA holds, and BOM standards. Purchasing remains human-controlled: shortages can be surfaced for Buyer review, but this planner never creates, submits, or approves a PO.</p>
      </div>
      <span className="badge">{rows.length} active</span>
    </div>

    <div className="metrics four">
      <Metric label="Ready / Next" value={String(ready)} />
      <Metric label="Blocked" value={String(blocked)} />
      <Metric label="Scheduled Crew Hrs" value={number(crewHours)} />
      <Metric label="Facility Machines" value={String(plan.data.workspace.machines.length)} />
    </div>

    {rows.length === 0 ? <div className="empty">No active production runs need planning right now.</div> : <div className="table-wrap">
      <table>
        <thead><tr><th>Decision</th><th>Run</th><th>Due</th><th>Ready</th><th>Materials</th><th>Labor</th><th>Equipment</th><th>Why</th></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.orderId} onClick={() => onOpenRun(row.orderId)}>
          <td><span className="badge">{row.decision}</span></td>
          <td><strong>{row.order}</strong><br/><small>{row.product} · {title(row.status)} · {title(row.priority)}</small></td>
          <td>{dueLabel(row)}</td>
          <td>{row.readiness}%</td>
          <td>{row.materialState}</td>
          <td>{row.laborState}</td>
          <td>{row.equipmentState}</td>
          <td>{row.reason}</td>
        </tr>)}</tbody>
      </table>
    </div>}
  </section>;
}

async function loadPlan(signal: AbortSignal): Promise<PlanData> {
  const [workspace, queue] = await Promise.all([
    apiGet<Workspace>("/api/v1/coman-parity/workspace", signal),
    apiGet<QueueRow[]>("/api/v1/production/orders", signal),
  ]);
  const activeQueue = queue.filter((row) => !["complete", "cancelled"].includes(row.Status.toLowerCase().replaceAll(" ", "_"))).slice(0, 40);
  const details = await Promise.all(activeQueue.map((row) => apiGet<ProductionDetail>(`/api/v1/production/orders/${encodeURIComponent(row.order_id)}`, signal)));
  return { workspace, queue: activeQueue, details };
}

function buildPlanRows(data: PlanData): PlanRow[] {
  const detailById = new Map(data.details.map((detail) => [detail.order.id, detail]));
  const lotById = new Map(data.workspace.lots.map((lot) => [lot.id, lot]));
  const machineModelById = new Map(data.workspace.machine_models.map((model) => [model.id, model]));
  const machineCategories = data.workspace.machines.map((machine) => machineModelById.get(machine.machine_model_id)?.category?.trim().toLowerCase()).filter(Boolean) as string[];
  const reservedByLot = new Map<string, number>();
  for (const reservation of data.workspace.reservations) {
    if (reservation.status !== "reserved") continue;
    reservedByLot.set(reservation.lot_id, (reservedByLot.get(reservation.lot_id) ?? 0) + Number(reservation.quantity || 0));
  }
  const crewHours = data.workspace.crew.reduce((sum, row) => sum + Number(row.available_people || 0) * Number(row.shift_hours || 0), 0);

  return data.queue.map((queueRow) => {
    const detail = detailById.get(queueRow.order_id);
    if (!detail) return fallbackRow(queueRow);

    const material = materialReadiness(detail, data.workspace, lotById, reservedByLot);
    const expectedLabor = Number(detail.variance.expected_labor_hours || 0);
    const laborConfigured = crewHours > 0;
    const laborShort = laborConfigured && expectedLabor > crewHours + 1e-9;
    const laborState = expectedLabor <= 0
      ? "No labor standard"
      : !laborConfigured
        ? `${number(expectedLabor)} hr needed · crew not scheduled`
        : laborShort
          ? `${number(expectedLabor)} hr needed · ${number(crewHours)} hr scheduled`
          : `${number(expectedLabor)} hr needed · capacity available`;

    const resource = (detail.variance.resource_category || detail.standard?.resource_category || "").trim();
    const resourceMatch = !resource || machineCategories.some((category) => category.includes(resource.toLowerCase()) || resource.toLowerCase().includes(category));
    const equipmentState = !resource ? "No equipment standard" : resourceMatch ? `${resource} available` : `${resource} not configured`;
    const onHold = queueRow.Status.toLowerCase().includes("hold") || queueRow.QA === "HOLD";
    const daysToDue = dayDifference(detail.order.due_at);
    const overdue = daysToDue !== null && daysToDue < 0;
    const urgent = overdue || (daysToDue !== null && daysToDue <= 2) || ["urgent", "high"].includes(detail.order.priority.toLowerCase());

    let readiness = 100;
    if (material.shortage) readiness -= 45;
    else if (material.needsReservation) readiness -= 10;
    if (!resourceMatch) readiness -= 30;
    if (onHold) readiness -= 35;
    if (laborShort) readiness -= 20;
    if (!detail.variance.standard_configured) readiness -= 10;
    if (overdue) readiness -= 5;
    readiness = Math.max(0, readiness);

    let decision: Decision;
    if (onHold || material.shortage || !resourceMatch) decision = "BLOCKED";
    else if (laborShort || overdue) decision = "AT RISK";
    else if (queueRow.Status.toLowerCase() === "in progress") decision = "CONTINUE";
    else if (urgent) decision = "RUN NOW";
    else decision = "RUN NEXT";

    const reasons: string[] = [];
    if (onHold) reasons.push(queueRow.QA === "HOLD" ? "QA hold requires review" : "run is on hold");
    if (material.shortage) reasons.push("true material shortage requires Buyer review");
    else if (material.needsReservation) reasons.push("available material still needs reservation");
    if (!resourceMatch) reasons.push(`required ${resource} resource is not configured`);
    if (laborShort) reasons.push("scheduled labor is below the BOM standard");
    if (overdue) reasons.push("due date has passed");
    else if (daysToDue !== null && daysToDue <= 2) reasons.push("due within 2 days");
    if (!detail.variance.standard_configured) reasons.push("production standard is not configured yet");
    if (detail.variance.qa_required && queueRow.QA !== "HOLD") reasons.push("QA release will be required before finished output release");
    if (detail.variance.compliance_checkpoint) reasons.push(`checkpoint: ${detail.variance.compliance_checkpoint}`);
    if (reasons.length === 0) reasons.push("BOM materials, capacity, and current run state are clear");

    return {
      orderId: queueRow.order_id,
      order: queueRow.Order,
      product: queueRow.Product,
      status: detail.order.status,
      priority: detail.order.priority,
      dueAt: detail.order.due_at,
      daysToDue,
      decision,
      readiness,
      materialState: material.label,
      laborState,
      equipmentState,
      reason: reasons.join("; "),
    };
  }).sort(comparePlanRows);
}

function materialReadiness(detail: ProductionDetail, workspace: Workspace, lotById: Map<string, Workspace["lots"][number]>, reservedByLot: Map<string, number>) {
  if (detail.requirements.length === 0) return { shortage: false, needsReservation: false, label: "No BOM material requirement" };
  let shortage = false;
  let needsReservation = false;
  const shortageLabels: string[] = [];

  for (const requirement of detail.requirements) {
    const currentReserved = workspace.reservations
      .filter((reservation) => reservation.production_order_id === detail.order.id && reservation.status === "reserved" && lotById.get(reservation.lot_id)?.product_id === requirement.product_id)
      .reduce((sum, reservation) => sum + Number(reservation.quantity || 0), 0);
    const productLots = workspace.lots.filter((lot) => lot.product_id === requirement.product_id && ["available", "released"].includes(lot.status));
    const unreserved = productLots.reduce((sum, lot) => sum + Math.max(0, Number(lot.on_hand || 0) - (reservedByLot.get(lot.id) ?? 0)), 0);
    const potential = currentReserved + unreserved;
    if (potential + 1e-9 < Number(requirement.quantity || 0)) {
      shortage = true;
      shortageLabels.push(`${requirement.product_name}: ${number(Number(requirement.quantity || 0) - potential)} ${requirement.unit} short`);
    } else if (currentReserved + 1e-9 < Number(requirement.quantity || 0)) {
      needsReservation = true;
    }
  }

  if (shortage) return { shortage: true, needsReservation, label: `${shortageLabels.join("; ")} · Buyer review` };
  if (needsReservation) return { shortage: false, needsReservation: true, label: "Available · reserve to run" };
  return { shortage: false, needsReservation: false, label: "Reserved / ready" };
}

function fallbackRow(row: QueueRow): PlanRow {
  return {
    orderId: row.order_id,
    order: row.Order,
    product: row.Product,
    status: row.Status,
    priority: "normal",
    dueAt: null,
    daysToDue: null,
    decision: row.Attention === "Normal" ? "RUN NEXT" : "AT RISK",
    readiness: row.Attention === "Normal" ? 80 : 50,
    materialState: row.Attention === "Material shortage" ? "Needs review" : "Unknown",
    laborState: "Open Run 360",
    equipmentState: "Open Run 360",
    reason: row.Attention === "Normal" ? "Detailed planning data is not available yet." : row.Attention,
  };
}

function comparePlanRows(a: PlanRow, b: PlanRow) {
  const decisionRank: Record<Decision, number> = { CONTINUE: 0, "RUN NOW": 1, "AT RISK": 2, BLOCKED: 3, "RUN NEXT": 4 };
  const decisionDelta = decisionRank[a.decision] - decisionRank[b.decision];
  if (decisionDelta !== 0) return decisionDelta;
  const dueA = a.daysToDue ?? Number.POSITIVE_INFINITY;
  const dueB = b.daysToDue ?? Number.POSITIVE_INFINITY;
  if (dueA !== dueB) return dueA - dueB;
  return b.readiness - a.readiness;
}

function dayDifference(value: string | null) {
  if (!value) return null;
  const due = new Date(value);
  if (Number.isNaN(due.getTime())) return null;
  const now = new Date();
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const dueDay = Date.UTC(due.getFullYear(), due.getMonth(), due.getDate());
  return Math.round((dueDay - today) / 86_400_000);
}

function dueLabel(row: PlanRow) {
  if (!row.dueAt || row.daysToDue === null) return "No due date";
  const date = new Date(row.dueAt).toLocaleDateString();
  if (row.daysToDue < 0) return `${date} · ${Math.abs(row.daysToDue)}d overdue`;
  if (row.daysToDue === 0) return `${date} · today`;
  return `${date} · ${row.daysToDue}d`;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function title(value: string) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function number(value: number) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
}
