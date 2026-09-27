export const guidedMetrcBase = "/api/v1/integration-wizard/metrc-setup";
export type MetrcSetupStatus = {
  facility: { id: string; name: string; license_number: string };
  mode: string; environment: string; state: string; can_manage: boolean;
  user_key_saved: boolean; platform_key_ready: boolean; configured: boolean; trusted_mapping: boolean;
  can_manage_platform: boolean; production_available: boolean; production_writes_enabled: boolean; full_baseline_ready: boolean;
  run: null | { id: string; status: string; started_at: string; completed_at?: string; license_number: string;
    workspace_summary?: { conflict_count: number; summary_truncated: boolean };
    totals?: { records: number; accepted: number; duplicates: number; errors: number; restrictions: number } };
  resources: { resource: string; status: string; records_seen: number; records_written: number;
    restricted: boolean; last_success_at: string | null }[];
};
export type MetrcFacilityPreview = {
  preview_id: string; state: string; environment: string;
  facility: MetrcSetupStatus["facility"];
  facilities: { name: string; license_number: string; license_type: string; provider_facility_id: string }[];
  provider_mutations: number; local_records_created: number;
};
