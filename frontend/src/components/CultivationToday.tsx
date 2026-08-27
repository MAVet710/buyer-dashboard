import { useMemo } from "react";
import type { CultivationPlant } from "../types/inventory";

type NextAction = {
  key: string;
  priority: "high" | "medium" | "low";
  action: string;
  reason: string;
  plant: CultivationPlant;
};

type ForecastRow = { week: string; strain: string; plants: number };

export function CultivationToday({ plants, onSelect }: { plants: CultivationPlant[]; onSelect: (plant: CultivationPlant) => void }) {
  const today = useMemo(() => startOfToday(), []);
  const active = useMemo(() => plants.filter((plant) => !["harvested", "destroyed"].includes(plant.phase)), [plants]);
  const flowering = useMemo(() => active.filter((plant) => plant.phase === "flowering"), [active]);
  const due7 = useMemo(() => flowering.filter((plant) => inWindow(plant.estimated_harvest_date, today, 0, 7)), [flowering, today]);
  const due30 = useMemo(() => flowering.filter((plant) => inWindow(plant.estimated_harvest_date, today, 0, 30)), [flowering, today]);
  const overdue = useMemo(() => flowering.filter((plant) => daysUntil(plant.estimated_harvest_date, today) < 0), [flowering, today]);
  const missingForecast = useMemo(() => active.filter((plant) => ["vegetative", "flowering"].includes(plant.phase) && !plant.estimated_harvest_date), [active]);
  const unassigned = useMemo(() => active.filter((plant) => !plant.room_code || plant.room_code === "UNASSIGNED"), [active]);

  const actions = useMemo<NextAction[]>(() => {
    const items: NextAction[] = [];
    overdue.forEach((plant) => items.push({ key: `overdue-${plant.id}`, priority: "high", action: "Review harvest readiness", reason: `Estimated harvest ${plant.estimated_harvest_date} is overdue.`, plant }));
    due7.forEach((plant) => items.push({ key: `due-${plant.id}`, priority: "medium", action: "Prepare for harvest", reason: `Estimated harvest is ${relativeDate(plant.estimated_harvest_date, today)}.`, plant }));
    missingForecast.forEach((plant) => items.push({ key: `forecast-${plant.id}`, priority: "medium", action: "Set harvest estimate", reason: `${title(plant.phase)} plant has no estimated harvest date.`, plant }));
    unassigned.forEach((plant) => items.push({ key: `room-${plant.id}`, priority: "medium", action: "Assign cultivation room", reason: "Plant is not assigned to an operating room.", plant }));
    return items.sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority) || a.plant.plant_tag.localeCompare(b.plant.plant_tag)).slice(0, 12);
  }, [due7, missingForecast, overdue, today, unassigned]);

  const forecast = useMemo<ForecastRow[]>(() => {
    const counts = new Map<string, ForecastRow>();
    flowering.forEach((plant) => {
      if (!plant.estimated_harvest_date) return;
      const days = daysUntil(plant.estimated_harvest_date, today);
      if (days < 0 || days > 56) return;
      const date = dateOnly(plant.estimated_harvest_date);
      if (!date) return;
      const week = mondayOf(date).toISOString().slice(0, 10);
      const key = `${week}|${plant.strain_name}`;
      const row = counts.get(key) ?? { week, strain: plant.strain_name, plants: 0 };
      row.plants += 1;
      counts.set(key, row);
    });
    return [...counts.values()].sort((a, b) => a.week.localeCompare(b.week) || a.strain.localeCompare(b.strain));
  }, [flowering, today]);

  const rooms = new Set(active.map((plant) => plant.room_code).filter((room) => room && room !== "UNASSIGNED")).size;

  return <section className="cultivation-today">
    <div className="section-heading"><div><div className="eyebrow">Cultivation Today</div><h3>What needs attention now</h3><p className="source-caption">Generated from live plant state. Select an action to work it in Plant 360.</p></div></div>
    <div className="metrics four"><Metric label="Active plants" value={active.length}/><Metric label="Harvest next 7d" value={due7.length}/><Metric label="Harvest next 30d" value={due30.length}/><Metric label="Active rooms" value={rooms}/></div>
    <div className="two-col">
      <section className="inventory-panel"><div className="section-heading"><div><h4>Next Actions</h4><p className="source-caption">No separate task setup. DoobieLogic derives these from dates, phases and room assignment.</p></div><span className="badge">{actions.length}</span></div>
        {actions.length ? <div className="table-wrap"><table><thead><tr><th>Priority</th><th>Plant</th><th>Action</th><th>Why</th></tr></thead><tbody>{actions.map((item) => <tr key={item.key} onClick={() => onSelect(item.plant)}><td><span className="badge">{item.priority}</span></td><td><strong>{item.plant.plant_tag}</strong><br/><small>{item.plant.strain_name} · {title(item.plant.phase)}</small></td><td>{item.action}</td><td>{item.reason}</td></tr>)}</tbody></table></div> : <div className="empty">No cultivation exceptions need attention from the current plant records.</div>}
      </section>
      <section className="inventory-panel"><div className="section-heading"><div><h4>8-week harvest forecast</h4><p className="source-caption">Expected flowering completions grouped by week and strain.</p></div></div>
        {forecast.length ? <div className="table-wrap"><table><thead><tr><th>Week of</th><th>Strain</th><th>Plants</th></tr></thead><tbody>{forecast.map((row) => <tr key={`${row.week}-${row.strain}`}><td>{row.week}</td><td>{row.strain}</td><td>{row.plants}</td></tr>)}</tbody></table></div> : <div className="empty">Add estimated harvest dates to flowering plants to build the forward forecast.</div>}
      </section>
    </div>
    {(overdue.length || missingForecast.length || unassigned.length) ? <div className="metrics"><Metric label="Overdue harvest estimates" value={overdue.length}/><Metric label="Missing harvest estimates" value={missingForecast.length}/><Metric label="Unassigned rooms" value={unassigned.length}/></div> : null}
  </section>;
}

function Metric({ label, value }: { label: string; value: number }) { return <div className="metric"><span>{label}</span><strong>{value.toLocaleString()}</strong></div>; }
function startOfToday() { const now = new Date(); return new Date(now.getFullYear(), now.getMonth(), now.getDate()); }
function dateOnly(value: string | null) { if (!value) return null; const parts = value.slice(0, 10).split("-").map(Number); return parts.length === 3 && parts.every(Number.isFinite) ? new Date(parts[0], parts[1] - 1, parts[2]) : null; }
function daysUntil(value: string | null, today: Date) { const date = dateOnly(value); return date ? Math.round((date.getTime() - today.getTime()) / 86_400_000) : Number.POSITIVE_INFINITY; }
function inWindow(value: string | null, today: Date, min: number, max: number) { const days = daysUntil(value, today); return days >= min && days <= max; }
function mondayOf(value: Date) { const date = new Date(value.getFullYear(), value.getMonth(), value.getDate()); const day = date.getDay(); date.setDate(date.getDate() - (day === 0 ? 6 : day - 1)); return date; }
function relativeDate(value: string | null, today: Date) { const days = daysUntil(value, today); if (!Number.isFinite(days)) return "not scheduled"; if (days === 0) return "today"; if (days === 1) return "tomorrow"; return `in ${days} days`; }
function title(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function priorityRank(value: NextAction["priority"]) { return value === "high" ? 0 : value === "medium" ? 1 : 2; }
