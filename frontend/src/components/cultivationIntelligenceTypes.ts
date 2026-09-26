export const intelligenceBase = "/api/v1/cultivation-intelligence";
export type Room = { id: string; room_code: string; display_name: string; phase: string; active: boolean; plant_capacity: number | null; plant_count?: number; current_cycle_ids?: string[]; current_stage?: { display_name: string } | null; context_truncated?: boolean };
export type Zone = { id: string; room_id: string; zone_code: string; display_name: string; active: boolean };
export type Cycle = { id: string; cycle_code: string; display_name: string; genetics_label: string; nursery_group_id: string | null; recipe_id: string | null; harvest_id: string | null; status: string; started_on: string | null; estimated_harvest_date: string | null; version: number };
export type Target = { metric: string; minimum: number | null; maximum: number | null; unit: string; threshold_seconds?: number | null };
export type Stage = { id?: string; stage_key: string; display_name: string; sequence: number; targets: Target[] };
export type Recipe = { id: string; name: string; version: number; status: string; description: string; approved_by: string | null; approved_at: string | null; stages: Stage[] };
export type Connection = { id: string; provider: string; label: string; mode: string; status: string; version: number; revoked_at: string | null; live_supported: false; last_import_at?: string | null };
export type RegistryMetric = { metric: string; unit: string; kind: string; aliases: string[]; display_name?: string };
export type Workspace = { rooms: Room[]; cycles: Cycle[]; connections: Connection[]; recipes: Recipe[]; truncated: boolean; can_manage: boolean; can_manage_connections: boolean; decision_support_only: true };
export type Evidence = Record<string, unknown>;
export type LatestReading = {
  connection_id: string; source_device_id: string; source_channel: string; device_id: string; sensor_id: string; metric: string;
  value: number | null; unit: string | null; original_value: number | string | null; original_unit: string | null;
  observed_at: string | null; received_at: string; data_age_seconds: number | null; latency_seconds: number | null;
  quality: string | null; state: string; reason: string | null; freshness: string; status: string;
  snapshot: { organization_id: string; facility_id: string; connection_id: string; room_id: string; device_id: string; sensor_id: string; mapping_revision: string | number; metric: string; effective_from: string; effective_to: string; zone_id?: string | null; cycle_id?: string | null; stage_id?: string | null; recipe_revision?: string | number | null; target_min?: number | null; target_max?: number | null; threshold_seconds?: number | null };
};
export type EdgeLatest = { as_of: string; readings: LatestReading[]; truncated: boolean; status: string };
export function record(value: unknown): Evidence { return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Evidence : {}; }
export function rows(value: unknown): Evidence[] { return Array.isArray(value) ? value.map(record) : []; }
export function textValue(value: unknown, fallback = "Unknown"): string { return typeof value === "string" || typeof value === "number" ? String(value) : fallback; }
export function metricLabel(metric: string, registry: RegistryMetric[] = []) { return registry.find(item => item.metric === metric)?.display_name || metric.replaceAll("_", " "); }
export function intelligenceScope() { return typeof localStorage === "undefined" ? [] : [localStorage.getItem("buyer-dash-organization") || "", localStorage.getItem("buyer-dash-facility") || ""]; }
