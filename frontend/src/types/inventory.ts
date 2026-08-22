export type InventoryPackage = {
  id: string;
  package_id: string;
  lot_code: string;
  product_id: string;
  sku: string;
  product_name: string;
  material_type: string;
  location: string;
  status: string;
  source_name: string;
  available: number;
  reserved: number;
  usable: number;
  unit: string;
  received_at: string | null;
  expiration_at: string | null;
  attention: string;
  sold_30d: number; daily_velocity: number; days_on_hand: number | null;
  unit_cost: number; retail_price: number; margin_pct: number | null;
  age_days: number | null; days_to_expiry: number | null;
};

export type InventoryResponse = {
  operation: "retail" | "production";
  grain: "packages";
  items: InventoryPackage[];
  facets: { statuses: string[]; material_types: string[]; locations: string[]; sources: string[] };
  summary: {
    package_count: number;
    available_quantity: number;
    reserved_quantity: number;
    hold_count: number;
    low_balance_count: number;
  };
};

export type ProductOption = { id: string; sku: string; name: string; item_type: string; base_unit: string };
export type InventoryReceipt = {
  product_id: string; package_id: string; lot_code: string; quantity: number; unit: string;
  location: string; source_name: string; manifest_reference: string; lab_testing_state: string;
  coa_reference: string; notes: string;
};
export type InventoryReceiptHistoryItem = {
  transaction_id: string; lot_id: string; product_name: string; package_id: string;
  quantity: number; unit: string; manifest_reference: string; source_name: string;
  actor: string; received_at: string;
};
export type InventoryAdjustment = { lot_id: string; adjustment_type: "incremental" | "set_quantity"; quantity: number; reason: string; reason_note: string };
export type AuditSummary = { id: string; audit_number: string; operation_type: "retail" | "production"; status: string; scope_label: string; blind_count: boolean; recount_tolerance: number; started_at: string; completed_at: string | null; created_by: string; scanned_count:number; total_count:number; recount_count:number };
export type AuditLine = { id: string; lot_id: string; product_name: string; package_id: string; location: string; expected_quantity: number | null; counted_quantity: number | null; variance_quantity: number; recount_required: boolean; unit: string; reason: string; notes: string; first_count_quantity: number | null; recount_quantity: number | null; counted_by: string; sku_or_upc: string; lot_code: string; metrc_package: string; primary_code: string; unit_cost: number; retail_price: number };
export type AuditScan = { id: string; raw_code: string; match_status: string; scan_stage: string; scanned_by: string; scanned_at: string };
export type AuditEvent = { id: string; action: string; actor: string; occurred_at: string; changes_json: string };
export type AuditDetail = { audit: AuditSummary; lines: AuditLine[]; scans: AuditScan[]; events: AuditEvent[] };
export type PackageLineage = { lot: { lot_id: string; lot_code: string; compliance_package_id: string; product_name: string; balance: number; unit: string }; created_by: null | { run_number: string; action_type: string; parents: { lot_id: string; lot_code: string; product_name: string; quantity: number; unit: string }[] }; used_by: { run_number: string; action_type: string; quantity_consumed: number; unit: string; outputs: { lot_id: string | null; lot_code: string; inventory_quantity: number; inventory_unit: string; purpose: string }[] }[] };
export type PlantPhase = "clone" | "seedling" | "vegetative" | "flowering" | "harvested" | "destroyed";
export type CultivationPlant = { id: string; plant_tag: string; strain_name: string; phase: PlantPhase; room_code: string; source_lot_id: string | null; mother_plant_tag: string; planted_at: string | null; estimated_harvest_date: string | null; retired_at: string | null; notes: string };
export type PlantEvent = { id: string; event_type: string; from_value: string; to_value: string; reason: string; notes: string; actor: string; occurred_at: string };
