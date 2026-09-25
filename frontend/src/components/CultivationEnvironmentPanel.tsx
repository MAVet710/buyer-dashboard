import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

const base = "/api/v1/inventory/production/plants";
const metrics = {
  temperature: ["Temperature", "C"], relative_humidity: ["Relative humidity", "%"],
  vpd: ["VPD", "kPa"], co2: ["CO2", "ppm"], substrate_ec: ["Substrate EC", "mS/cm"],
  substrate_vwc: ["Substrate VWC / moisture", "%"], irrigation_volume: ["Irrigation volume", "L"],
  irrigation_event: ["Irrigation event", "count"],
} as const;
type Metric = keyof typeof metrics;
type Target = { minimum: number | null; maximum: number | null; stale_minutes: number };
export type EnvironmentReading = {
  metric: Metric; source: string; device_id: string; value: number | null; unit: string;
  quality: string | null; observed_at: string | null; states: string[]; target: Target | null;
  trend_24h: { count: number; min: number; max: number; average: number; total: number } | null;
};
type Snapshot = { readings: EnvironmentReading[]; exceptions: EnvironmentReading[]; truncated: boolean; as_of: string };
type Room = { id: string; room_code: string; display_name: string; active: boolean };
const number = (value: number) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);

export function CultivationEnvironmentPanel() {
  const [selected, setSelected] = useState("");
  const rooms = useQuery({ queryKey: ["cultivation-rooms"], queryFn: ({ signal }) => apiGet<{ items: Room[] }>(`${base}/rooms`, signal) });
  const account = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<{ user: { role: string } }>("/api/v1/account/context", signal) });
  const roomId = rooms.data?.items.some(room => room.id === selected) ? selected : rooms.data?.items[0]?.id ?? "";
  const canWrite = ["dev", "admin", "supervisor", "operator", "qa"].includes(account.data?.user.role ?? "");
  return <section className="inventory-panel">
    <div className="section-heading"><div><h3>Room environment</h3><p>Decision support only. No equipment control or vendor adapter is connected by this feature.</p></div></div>
    {rooms.isError ? <div className="state error">{rooms.error.message}</div> : rooms.isPending ? <div className="state">Loading rooms...</div> : <>
      <label>Environment room<select value={roomId} onChange={event => setSelected(event.target.value)}>
        {rooms.data.items.map(room => <option key={room.id} value={room.id}>{room.display_name || room.room_code}{room.active ? "" : " (inactive)"}</option>)}
      </select></label>
      {roomId ? <RoomEnvironment key={roomId} roomId={roomId} canWrite={canWrite} /> : <p className="empty">Configure a cultivation room to record environmental observations.</p>}
    </>}
  </section>;
}

function RoomEnvironment({ roomId, canWrite }: { roomId: string; canWrite: boolean }) {
  const client = useQueryClient();
  const path = `${base}/telemetry/rooms/${encodeURIComponent(roomId)}`;
  const query = useQuery({ queryKey: ["cultivation-environment", roomId], queryFn: ({ signal }) => apiGet<Snapshot>(path, signal), refetchInterval: 60_000 });
  const refresh = () => { void client.invalidateQueries({ queryKey: ["cultivation-environment", roomId] }); };
  return <>
    {query.isError ? <div className="state error">Environment data could not load: {query.error.message}</div> : query.isPending ? <div className="state">Loading conditions...</div> : <>
      <p className="source-caption">As of {new Date(query.data.as_of).toLocaleString()}. Trends cover valid readings in the past 24 hours. Unconfigured continuous sensors become stale after 60 minutes.</p>
      {query.data.truncated && <div className="warning-banner">Showing the first 200 sensor streams. Additional streams are not included in this summary.</div>}
      {query.data.exceptions.length > 0 && <div className="warning-banner" role="status">{query.data.exceptions.length} environmental exceptions need review. Check flagged readings below.</div>}
      <EnvironmentTable readings={query.data.readings} />
      {canWrite && <details><summary>Record an observation or configure targets</summary><div className="two-col">
        <ObservationForm path={path} onSaved={refresh} />
        <TargetForm path={path} readings={query.data.readings} onSaved={refresh} />
      </div></details>}
    </>}
  </>;
}

export function EnvironmentTable({ readings }: { readings: EnvironmentReading[] }) {
  return <div className="table-wrap"><table><thead><tr><th>Measurement / source</th><th>Latest observation</th><th>State</th><th>Past 24 hours</th><th>Target</th></tr></thead><tbody>
    {readings.map(row => <tr key={`${row.metric}-${row.source}-${row.device_id}`}>
      <td>{metrics[row.metric][0]}<br /><small>{row.source || "No source"}{row.device_id ? ` / ${row.device_id}` : ""}</small></td>
      <td>{row.value === null ? "No observation" : `${number(row.value)} ${row.unit}`}<br /><small>{row.observed_at ? new Date(row.observed_at).toLocaleString() : ""}</small></td>
      <td className={row.states.includes("current") ? "" : "warning-text"}>{row.states.map(state => state.replaceAll("_", " ")).join(", ")}</td>
      <td>{row.trend_24h ? <>{row.trend_24h.count} valid readings<br />Min {number(row.trend_24h.min)}, max {number(row.trend_24h.max)}, avg {number(row.trend_24h.average)} {row.unit}
        {row.metric.startsWith("irrigation_") && <><br />Total {number(row.trend_24h.total)} {row.unit}</>}</> : "No valid readings"}</td>
      <td>{row.target ? <>{row.target.minimum ?? "No minimum"} to {row.target.maximum ?? "no maximum"} {row.unit}<br /><small>Stale after {row.target.stale_minutes} minutes</small></> : "Not configured"}</td>
    </tr>)}
  </tbody></table></div>;
}

function MetricSelect({ value, onChange }: { value: Metric; onChange: (metric: Metric) => void }) {
  return <label>Measurement<select value={value} onChange={event => onChange(event.target.value as Metric)}>{Object.entries(metrics).map(([key, [label, unit]]) => <option key={key} value={key}>{label} ({unit})</option>)}</select></label>;
}

function ObservationForm({ path, onSaved }: { path: string; onSaved: () => void }) {
  const [metric, setMetric] = useState<Metric>("temperature");
  const [eventId, setEventId] = useState(() => crypto.randomUUID());
  const [observedAt, setObservedAt] = useState(() => new Date().toISOString());
  const mutation = useMutation({ mutationFn: (body: unknown) => apiPost<{ inserted: number; duplicates: number }>(`${path}/observations`, body),
    onSuccess: () => { setEventId(crypto.randomUUID()); setObservedAt(new Date().toISOString()); onSaved(); } });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    mutation.mutate({ observations: [{ source: "manual", event_id: eventId, metric, value: Number(data.get("value")), unit: metrics[metric][1],
      observed_at: observedAt, quality: data.get("quality"), device_id: String(data.get("device") || "") }] });
  }
  return <form onSubmit={submit}><h4>Manual observation</h4><fieldset disabled={mutation.isPending}><div className="form-grid">
    <MetricSelect value={metric} onChange={setMetric} />
    <label>Value ({metrics[metric][1]})<input name="value" type="number" step="any" required /></label>
    <label>Observed at (ISO timestamp with timezone)<input value={observedAt} onChange={event => setObservedAt(event.target.value)} required /></label>
    <label>Device ID (optional)<input name="device" maxLength={120} /></label>
    <label>Quality<select name="quality"><option value="valid">Valid</option><option value="suspect">Suspect</option><option value="invalid">Invalid</option></select></label>
  </div><button className="primary" type="submit">Record observation</button></fieldset>
    {mutation.isError && <p className="form-error" role="alert">{mutation.error.message} Retry unchanged evidence if the request outcome is uncertain.</p>}
    {mutation.isSuccess && <p role="status">Recorded {mutation.data.inserted}; already recorded {mutation.data.duplicates}.</p>}
  </form>;
}

function TargetForm({ path, readings, onSaved }: { path: string; readings: EnvironmentReading[]; onSaved: () => void }) {
  const [metric, setMetric] = useState<Metric>("temperature");
  const target = readings.find(row => row.metric === metric)?.target;
  const mutation = useMutation({ mutationFn: (body: unknown) => apiPost(`${path}/target`, body), onSuccess: onSaved });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    mutation.mutate({ metric, minimum: data.get("minimum") === "" ? null : Number(data.get("minimum")),
      maximum: data.get("maximum") === "" ? null : Number(data.get("maximum")), stale_minutes: Number(data.get("stale_minutes")) });
  }
  return <form onSubmit={submit}><h4>Room targets</h4><p>Operator-defined ranges, not cultivation recommendations. Configuring a target marks this measurement as expected.</p>
    <fieldset disabled={mutation.isPending}><MetricSelect value={metric} onChange={setMetric} />
      <div className="form-grid" key={`${metric}-${JSON.stringify(target)}`}>
        <label>Minimum ({metrics[metric][1]})<input name="minimum" type="number" step="any" defaultValue={target?.minimum ?? ""} /></label>
        <label>Maximum ({metrics[metric][1]})<input name="maximum" type="number" step="any" defaultValue={target?.maximum ?? ""} /></label>
        <label>Stale after (minutes)<input name="stale_minutes" type="number" min={1} max={10080} defaultValue={target?.stale_minutes ?? 60} required /></label>
      </div><button className="primary" type="submit">Save target</button></fieldset>
    {mutation.isError && <p className="form-error" role="alert">{mutation.error.message}</p>}
    {mutation.isSuccess && <p role="status">Target saved.</p>}
  </form>;
}
