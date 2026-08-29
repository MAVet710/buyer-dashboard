import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import "../production-planning.css";

type Workspace = {
  orders: { id: string; order_number: string; product_name: string; status: string; due_at: string | null; priority: string }[];
  machines: { id: string; display_name: string; machine_model_id: string }[];
  machine_models: { id: string; category: string; manufacturer: string; model: string }[];
};

type Placement = {
  id: string;
  production_order_id: string;
  order_number: string;
  product_name: string;
  due_at: string | null;
  priority: string;
  status: string;
  version: number;
  scheduled_start_at: string;
  scheduled_end_at: string;
  machine_id: string | null;
  planned_people: number;
  reason: string;
};

type OrderDetail = {
  variance: {
    expected_cycle_hours: number;
    expected_labor_hours: number;
    resource_category: string;
  };
};

type Warning = { code: string; category: string; message: string; severity: "info" | "warning" | "blocker" };
type Preview = {
  order: { id: string; order_number: string; product_name: string; due_at: string | null; priority: string; status: string };
  current: Placement | null;
  proposed: {
    scheduled_start_at: string;
    scheduled_end_at: string;
    machine_id: string | null;
    machine_name: string;
    planned_people: number;
    window_hours: number;
    reason: string;
  };
  warnings: Warning[];
  blocker_count: number;
  warning_count: number;
  preview_key: string;
};

type ScheduleInput = {
  scheduled_start_at: string;
  scheduled_end_at: string;
  machine_id: string | null;
  planned_people: number;
  reason: string;
};

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;

export function ProductionCalendar({ onOpenRun }: { onOpenRun: (orderId: string) => void }) {
  const client = useQueryClient();
  const workspace = useQuery({ queryKey: ["production-calendar-workspace"], queryFn: ({ signal }) => apiGet<Workspace>("/api/v1/coman-parity/workspace", signal) });
  const schedule = useQuery({ queryKey: ["production-calendar"], queryFn: ({ signal }) => apiGet<Placement[]>("/api/v1/production/schedule", signal) });
  const [cursor, setCursor] = useState(() => startOfMonth(new Date()));
  const [schedulerOpen, setSchedulerOpen] = useState(false);
  const [orderId, setOrderId] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [machineId, setMachineId] = useState("");
  const [plannedPeople, setPlannedPeople] = useState(0);
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);

  const detail = useQuery({
    queryKey: ["production-calendar-order", orderId],
    enabled: Boolean(orderId),
    queryFn: ({ signal }) => apiGet<OrderDetail>(`/api/v1/production/orders/${encodeURIComponent(orderId)}`, signal),
  });

  const input = useMemo<ScheduleInput | null>(() => {
    if (!start || !end) return null;
    return {
      scheduled_start_at: new Date(start).toISOString(),
      scheduled_end_at: new Date(end).toISOString(),
      machine_id: machineId || null,
      planned_people: Number(plannedPeople || 0),
      reason,
    };
  }, [start, end, machineId, plannedPeople, reason]);

  useEffect(() => {
    setPreview(null);
    setAcknowledged(false);
  }, [orderId, start, end, machineId, plannedPeople, reason]);

  useEffect(() => {
    if (!start || !detail.data?.variance.expected_cycle_hours) return;
    const startDate = new Date(start);
    if (Number.isNaN(startDate.getTime())) return;
    const proposedEnd = new Date(startDate.getTime() + detail.data.variance.expected_cycle_hours * 3_600_000);
    setEnd(toLocalInput(proposedEnd));
  }, [start, detail.data?.variance.expected_cycle_hours]);

  const previewMutation = useMutation({
    mutationFn: async () => {
      if (!orderId || !input) throw new Error("Choose a run and schedule window first.");
      return apiPost<Preview>(`/api/v1/production/orders/${encodeURIComponent(orderId)}/schedule/preview`, input);
    },
    onSuccess: (data) => { setPreview(data); setAcknowledged(false); },
  });

  const commitMutation = useMutation({
    mutationFn: async () => {
      if (!orderId || !input || !preview) throw new Error("Preview this schedule change before committing it.");
      return apiPost<Placement>(`/api/v1/production/orders/${encodeURIComponent(orderId)}/schedule`, {
        ...input,
        preview_key: preview.preview_key,
        accept_warnings: acknowledged,
      });
    },
    onSuccess: async (placement) => {
      setPreview(null);
      setAcknowledged(false);
      setReason("");
      setCursor(startOfMonth(new Date(placement.scheduled_start_at)));
      await client.invalidateQueries({ queryKey: ["production-calendar"] });
    },
  });

  if (workspace.isLoading || schedule.isLoading) return <section className="inventory-panel"><div className="state">Loading production calendar…</div></section>;
  if (workspace.isError) return <section className="inventory-panel"><div className="state error">Production calendar could not load: {workspace.error.message}</div></section>;
  if (schedule.isError) return <section className="inventory-panel"><div className="state error">Production schedule could not load: {schedule.error.message}</div></section>;
  if (!workspace.data || !schedule.data) return null;

  const machineName = new Map(workspace.data.machines.map((row) => [row.id, row.display_name]));
  const activeOrders = workspace.data.orders.filter((row) => !["complete", "cancelled"].includes(row.status));
  const scheduledOrderIds = new Set(schedule.data.map((row) => row.production_order_id));
  const unscheduled = activeOrders.filter((row) => !scheduledOrderIds.has(row.id));
  const scheduleByDay = groupByDay([...schedule.data].sort((a, b) => new Date(a.scheduled_start_at).getTime() - new Date(b.scheduled_start_at).getTime()));
  const days = monthGrid(cursor);
  const monthRows = schedule.data.filter((row) => isSameMonth(new Date(row.scheduled_start_at), cursor));
  const needsAck = Boolean(preview?.warnings.some((warning) => warning.severity !== "info"));
  const todayKey = dateKey(new Date());

  const openSchedulerForDay = (day: Date) => {
    const value = new Date(day.getFullYear(), day.getMonth(), day.getDate(), 8, 0, 0, 0);
    setStart(toLocalInput(value));
    setEnd("");
    setSchedulerOpen(true);
  };

  return <section className="inventory-panel production-calendar">
    <div className="section-heading">
      <div>
        <div className="eyebrow">Production Calendar</div>
        <h3>See the production plan by date</h3>
        <p className="source-caption">Runs stay easy to scan on the surface. Before a schedule change is committed, DoobieLogic still checks BOM cycle standards, material readiness, crew capacity, machine conflicts, QA, compliance checkpoints, and due dates underneath.</p>
      </div>
      <span className="badge">{unscheduled.length} unscheduled</span>
    </div>

    <div className="metrics four">
      <Metric label="This Month" value={`${monthRows.length} runs`} />
      <Metric label="Active Unscheduled" value={String(unscheduled.length)} />
      <Metric label="Facility Machines" value={String(workspace.data.machines.length)} />
      <Metric label="Active Runs" value={String(activeOrders.length)} />
    </div>

    <div className="production-calendar-toolbar">
      <div className="production-calendar-toolbar-nav">
        <button className="secondary" type="button" onClick={() => setCursor(addMonths(cursor, -1))}>Previous</button>
        <button className="secondary" type="button" onClick={() => setCursor(startOfMonth(new Date()))}>Today</button>
        <button className="secondary" type="button" onClick={() => setCursor(addMonths(cursor, 1))}>Next</button>
        <span className="production-calendar-month-title">{cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</span>
      </div>
      <div className="production-calendar-toolbar-actions">
        <button className="primary" type="button" onClick={() => setSchedulerOpen((value) => !value)}>{schedulerOpen ? "Close Scheduler" : "Schedule Run"}</button>
      </div>
    </div>

    <div className="production-calendar-scroll">
      <div className="production-calendar-grid" role="grid" aria-label={`${cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })} production calendar`}>
        {WEEKDAYS.map((day) => <div className="production-calendar-weekday" role="columnheader" key={day}>{day}</div>)}
        {days.map((day) => {
          const key = dateKey(day);
          const rows = scheduleByDay[key] ?? [];
          const outsideMonth = day.getMonth() !== cursor.getMonth();
          return <div className={`production-calendar-day${outsideMonth ? " outside-month" : ""}${key === todayKey ? " today" : ""}`} role="gridcell" key={key}>
            <div className="production-calendar-day-head">
              <strong>{day.getDate()}</strong>
              <button className="production-calendar-add-day" type="button" onClick={() => openSchedulerForDay(day)} aria-label={`Schedule a run on ${day.toLocaleDateString()}`}>+</button>
            </div>
            <div className="production-calendar-events">
              {rows.slice(0, 4).map((row) => <button className="production-calendar-event" type="button" key={row.id} onClick={() => onOpenRun(row.production_order_id)} title={`${row.order_number} · ${row.product_name}`}>
                <strong>{time(row.scheduled_start_at)} · {row.order_number}</strong>
                <span>{row.product_name}</span>
                <small>{row.machine_id ? machineName.get(row.machine_id) ?? "Assigned machine" : "No machine"} · {row.planned_people || 0} people</small>
              </button>)}
              {rows.length > 4 ? <span className="production-calendar-more">+{rows.length - 4} more run{rows.length - 4 === 1 ? "" : "s"}</span> : null}
            </div>
          </div>;
        })}
      </div>
    </div>

    {schedulerOpen ? <div className="inventory-panel nested production-calendar-scheduler">
      <div className="section-heading compact">
        <div><div className="eyebrow">Schedule Run</div><h3>Preview before commit</h3></div>
        <span className="badge">Conflict-aware</span>
      </div>
      <div className="form-grid">
        <label>Production run<select value={orderId} onChange={(event) => setOrderId(event.target.value)}><option value="">Select run</option>{activeOrders.map((row) => <option value={row.id} key={row.id}>{row.order_number} · {row.product_name}</option>)}</select></label>
        <label>Start<input type="datetime-local" value={start} onChange={(event) => setStart(event.target.value)} /></label>
        <label>End<input type="datetime-local" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
        <label>Machine<select value={machineId} onChange={(event) => setMachineId(event.target.value)}><option value="">No machine assigned</option>{workspace.data.machines.map((row) => <option key={row.id} value={row.id}>{row.display_name}</option>)}</select></label>
        <label>People<input type="number" min={0} value={plannedPeople} onChange={(event) => setPlannedPeople(Number(event.target.value || 0))} /></label>
        <label>Reason / scheduling note<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why this window?" /></label>
      </div>
      {orderId && detail.data ? <p className="source-caption">BOM standard: {number(detail.data.variance.expected_cycle_hours)} cycle hr · {number(detail.data.variance.expected_labor_hours)} labor hr{detail.data.variance.resource_category ? ` · ${detail.data.variance.resource_category}` : ""}. Start time automatically proposes the standard cycle duration.</p> : null}
      <div className="button-row">
        <button className="secondary" type="button" disabled={!orderId || !input || previewMutation.isPending} onClick={() => previewMutation.mutate()}>{previewMutation.isPending ? "Checking capacity…" : "Preview Schedule"}</button>
      </div>
      {previewMutation.isError ? <div className="state error">{previewMutation.error.message}</div> : null}

      {preview ? <div className="inventory-panel nested">
        <div className="section-heading compact">
          <div><div className="eyebrow">Exact Change Preview</div><h3>{preview.order.order_number}</h3></div>
          <span className="badge">{preview.blocker_count ? `${preview.blocker_count} blockers` : preview.warning_count ? `${preview.warning_count} warnings` : "Clear"}</span>
        </div>
        <div className="metrics four">
          <Metric label="Start" value={dateTime(preview.proposed.scheduled_start_at)} />
          <Metric label="End" value={dateTime(preview.proposed.scheduled_end_at)} />
          <Metric label="Window" value={`${number(preview.proposed.window_hours)} hr`} />
          <Metric label="Crew" value={`${preview.proposed.planned_people} people`} />
        </div>
        {preview.warnings.length === 0 ? <div className="state success">No material, labor, machine, QA, compliance, or due-date conflicts were detected.</div> : <div className="attention-stack">
          {preview.warnings.map((warning, index) => <div className={`attention-item ${warning.severity === "blocker" ? "urgent" : ""}`} key={`${warning.code}-${index}`}>
            <strong>{warning.category} · {warning.severity.toUpperCase()}</strong><span>{warning.message}</span>
          </div>)}
        </div>}
        {needsAck ? <label className="check-row"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} /> I reviewed these conflicts and still want to commit this schedule placement.</label> : null}
        <div className="button-row">
          <button className="primary" type="button" disabled={commitMutation.isPending || (needsAck && !acknowledged)} onClick={() => commitMutation.mutate()}>{commitMutation.isPending ? "Committing…" : preview.current ? "Commit Reschedule" : "Commit Schedule"}</button>
        </div>
        {commitMutation.isError ? <div className="state error">{commitMutation.error.message}</div> : null}
      </div> : null}
    </div> : null}
  </section>;
}

function groupByDay(rows: Placement[]) {
  return rows.reduce<Record<string, Placement[]>>((groups, row) => {
    const key = dateKey(row.scheduled_start_at);
    (groups[key] ??= []).push(row);
    return groups;
  }, {});
}

function startOfMonth(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

function addMonths(value: Date, amount: number) {
  return new Date(value.getFullYear(), value.getMonth() + amount, 1);
}

function monthGrid(value: Date) {
  const first = startOfMonth(value);
  const gridStart = new Date(first.getFullYear(), first.getMonth(), 1 - first.getDay());
  return Array.from({ length: 42 }, (_, index) => new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + index));
}

function isSameMonth(value: Date, month: Date) {
  return value.getFullYear() === month.getFullYear() && value.getMonth() === month.getMonth();
}

function dateKey(value: Date | string) {
  const date = typeof value === "string" ? new Date(value) : value;
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function toLocalInput(value: Date) {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function time(value: string) { return new Date(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }
function dateTime(value: string) { return new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); }
function number(value: number) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 }); }
function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }
