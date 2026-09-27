export const networkBase = "/api/v1/cultivation-networks";
export type NetworkConnection = {
  id: string; version: number; label: string; adapter: "aranet_cloud" | "things_stack";
  enabled: boolean; status: string; device_count: number; last_contact_at?: string;
  last_received_at?: string; last_observed_at?: string; unmapped_readings?: number;
  unmapped_messages?: number; dropped_readings?: number; dropped_messages?: number;
  transport_connected?: boolean;
};
export type NetworkStatus = { host_ready: boolean; can_manage: boolean; mqtt_available?: boolean;
  connections: NetworkConnection[]; truncated: boolean };
export type NetworkStream = { source_channel: string; source_metric: string; unit: string | null;
  source_unit_label: string; label: string; suggested_metric: string | null;
  sample_value: number | null; sample_at: string | null };
export type NetworkDevice = { id: string; name: string; status: string; streams: NetworkStream[] };
export type NetworkPreview = { id: string; state: string; devices: NetworkDevice[]; truncated: boolean;
  error: string | null; adapter: string; transport: string };
export type NetworkDeviceChoice = { source_id: string; room_id: string; zone_id: string | null;
  streams: { source_channel: string; metric: string }[] };
