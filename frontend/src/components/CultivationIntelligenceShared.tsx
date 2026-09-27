import { useIntelligence } from "./cultivationIntelligenceQueries";
import { useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { intelligenceScope, record, rows, textValue, type Zone } from "./cultivationIntelligenceTypes";
import { useState } from "react";

export function ZoneSelect({ roomId, name = "zone_id" }: { roomId: string; name?: string }) {
  const query = useIntelligence<{ zones: Zone[]; truncated: boolean }>(`/rooms/${encodeURIComponent(roomId)}/zones`, Boolean(roomId));
  if (!roomId) return <p>Choose a room before selecting a zone.</p>;
  return <ReadState query={query}>{data => <><label>Zone (optional)<select name={name} defaultValue=""><option value="">No zone assigned</option>{data.zones.filter(zone => zone.active).map(zone => <option key={zone.id} value={zone.id}>{zone.display_name || zone.zone_code}</option>)}</select></label>{data.truncated && <p>Zone choices are incomplete.</p>}</>}</ReadState>;
}
export function AggregateWindow({ onApply }: { onApply: (query: string) => void }) {
  const [error, setError] = useState("");
  return <form onSubmit={event => { event.preventDefault(); const fields = new FormData(event.currentTarget); const start = String(fields.get("start")); const end = String(fields.get("end")); const a = Date.parse(start); const b = Date.parse(end); if (!start.endsWith("Z") || !end.endsWith("Z") || !Number.isFinite(a) || !Number.isFinite(b) || a % 3600000 || b % 3600000 || b <= a || b - a > 2678400000) { setError("Use UTC hour boundaries with Z, increasing and at most 31 days apart."); return; } setError(""); onApply(`?${new URLSearchParams({ start, end })}`); }}><details><summary>Historical aggregate window</summary><p>Persisted aggregates only. Missing data remains unknown. Default: previous 24 completed UTC hours.</p><label>Start (UTC hour)<input name="start" required placeholder="2026-09-25T00:00:00Z" /></label><label>End (UTC hour)<input name="end" required placeholder="2026-09-26T00:00:00Z" /></label><button className="secondary">Read dated aggregates</button><button className="secondary" type="button" onClick={() => onApply("")}>Use default window</button>{error && <p role="alert">{error}</p>}</details></form>;
}
export function ConnectionFreshness({ value }: { value: unknown }) {
  const data = record(value);
  return <section><h4>Connection evidence clocks</h4><p>Connection scope only, not room condition or individual exposure. Check the connection details for authorization and transport health. A recent receipt does not prove every sensor is fresh.</p>{rows(data.connections).map((connection, index) => <p key={index}>Connection {textValue(connection.connection_id)}: last import {textValue(connection.last_import_at)}; last local receipt {textValue(connection.last_received_at)}; last valid sensor reading {textValue(connection.last_valid_observed_at)}.</p>)}{!rows(data.connections).length && <p>No connection clock evidence supplied.</p>}{data.truncated === true && <p>Connection clocks are incomplete.</p>}</section>;
}
export function ReadState<T>({ query, children }: { query: UseQueryResult<T, Error>; children: (data: T) => ReactNode }) {
  if (query.isError) return <div role="alert" className="state error">Unable to load evidence: {query.error.message} <button className="secondary" onClick={() => void query.refetch()}>Retry</button></div>;
  if (!query.data) return <p role="status">Loading evidence...</p>;
  return <>{children(query.data)}</>;
}
export function WriteState({ error, success }: { error: Error | null; success?: boolean }) {
  const client = useQueryClient();
  return <>{error && <div><p className="form-error" role="alert">{error.message} Your input is retained. For a version conflict, reload current evidence before submitting again.</p><button type="button" className="secondary" onClick={() => void client.invalidateQueries({ queryKey: ["cultivation-intelligence", ...intelligenceScope()] })}>Reload current evidence</button></div>}{success && <p role="status">Saved.</p>}</>;
}
export function EvidenceList({ value, empty }: { value: unknown; empty: string }) {
  const items = rows(Array.isArray(value) ? value.map(item => (typeof item === "string" || typeof item === "number") ? { title: item } : item) : value);
  return items.length ? <ul>{items.slice(0, 200).map((item, index) => <li key={textValue(item.id, String(index))}>{textValue(item.title ?? item.display_name ?? item.plant_tag ?? item.event_type ?? item.source_channel ?? item.stage_id ?? item.id ?? item.lot_id)}{item.occurred_at || item.entered_at ? ` Â· ${textValue(item.occurred_at ?? item.entered_at)}` : ""}{item.exited_at ? ` to ${textValue(item.exited_at)}` : ""}{["zone_id", "stage", "location_code", "started_at", "completed_at", "added_at", "removed_at", "transformation_type", "source_entity_type", "source_entity_id", "lot_id", "quantity", "unit", "measurement_basis", "lab_testing_state", "coa_document_id", "evidence_source", "verified_at", "cost_entry_id", "amount", "allocation", "reason"].filter(key => item[key] != null).map(key => <span key={key}> ? {key.replaceAll("_", " ")}: {textValue(item[key])}</span>)}{typeof item.room_id === "string" && <> Â· <a href={`/cultivation?room=${encodeURIComponent(item.room_id)}`}>Open Room 360</a></>}{typeof item.plant_id === "string" && <> Â· <a href={`/cultivation?plant=${encodeURIComponent(item.plant_id)}`}>Open plant</a></>}{typeof item.cycle_id === "string" && <> Â· <a href={`/cultivation?cycle=${encodeURIComponent(item.cycle_id)}`}>Open Crop Cycle</a></>}</li>)}</ul> : <p className="empty">{empty}</p>;
}
