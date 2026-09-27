export type RadioMeasurement = { metric: string; value: number; unit: string; timestamp_basis: string };
export type RadioCandidate = { id: string; name: string; profile_id: string; supported: boolean; reason: string | null; device_hint: string; rssi_dbm: number | null; last_seen_at: string; measurements: RadioMeasurement[] };
export type RadioScan = { id: string; state: string; receiver_id: string; expires_at: string; error_code: string | null; devices: RadioCandidate[]; truncated: boolean };
export type RadioStatus = { enabled: boolean; host_matches: boolean; can_manage: boolean; receivers: { id: string; kind: string; band_label: string; available: boolean; reason: string }[]; runtime_error: string | null };
export type RadioConnection = { id: string; name: string; connection_id: string; device_id: string; room_id: string; zone_id: string | null; profile_id: string; status: string; last_received_at: string | null; version: number; return_route: string };
