import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../lib/api";

type ReconciliationSummary = {
  status: string;
  local_tracked_lot_count: number;
  metrc_package_count: number;
  matched_package_count: number;
  discrepancy_count: number;
  high_count: number;
  medium_count: number;
  info_count: number;
  untracked_local_lot_count: number;
  ignored_metrc_record_count: number;
  by_code: Record<string, number>;
};

type ReconciliationDiscrepancy = {
  code: string;
  severity: string;
  package_id: string;
  product_name: string;
  local_quantity: number | null;
  metrc_quantity: number | null;
  local_unit: string;
  metrc_unit: string;
  local_location: string;
  metrc_location: string;
  local_lab_state: string;
  metrc_lab_state: string;
  message: string;
};

type ReconciliationReport = {
  configured: boolean;
  ready: boolean;
  operation: string;
  provider: string;
  read_only: boolean;
  message: string;
  jurisdiction_code?: string;
  license_number?: string;
  environment?: string;
  compared_at?: string;
  truncated?: boolean;
  summary: ReconciliationSummary;
  discrepancies: ReconciliationDiscrepancy[];
};

export function InventoryReconciliationControl({ operation }: { operation: "retail" | "production" }) {
  const [open, setOpen] = useState(false);
  const report = useQuery({
    queryKey: ["inventory-metrc-reconciliation", operation],
    enabled: open,
    staleTime: 30_000,
    queryFn: ({ signal }) => apiGet<ReconciliationReport>(`/api/v1/inventory/${operation}/reconciliation`, signal),
  });

  if (!open) {
    return <button className="secondary" type="button" onClick={() => setOpen(true)}>Reconcile with Metrc</button>;
  }

  const summary = report.data?.summary;
  return <section className="inventory-panel">
    <div className="section-heading">
      <div>
        <h3>Metrc reconciliation</h3>
        <p>{report.data?.message || "Comparing the active Metrc package ledger with DoobieLogic physical inventory…"}</p>
      </div>
      <div className="audit-actions">
        <button className="secondary" type="button" disabled={report.isFetching} onClick={() => report.refetch()}>{report.isFetching ? "Checking…" : "Run again"}</button>
        <button className="secondary" type="button" onClick={() => setOpen(false)}>Close</button>
      </div>
    </div>

    <div className="info-banner"><strong>Read-only comparison.</strong> This does not change Metrc or DoobieLogic inventory. It compares Metrc active package quantity with the physical DoobieLogic transaction ledger, before Production or Wholesale reservations are subtracted.</div>
    {report.isLoading ? <div className="state">Loading all active Metrc packages for this exact facility license…</div> : null}
    {report.isError ? <div className="state error">{report.error.message}</div> : null}
    {report.data && !report.data.ready ? <div className="warning-banner">{report.data.message}</div> : null}
    {report.data?.truncated ? <div className="warning-banner">Metrc returned more pages than the safety ceiling. This report is incomplete and should not be treated as reconciled.</div> : null}

    {summary && report.data?.ready ? <>
      <div className="summary-grid">
        <div><span>Matched</span><strong>{summary.matched_package_count.toLocaleString()}</strong><small>packages</small></div>
        <div><span>Discrepancies</span><strong>{summary.discrepancy_count.toLocaleString()}</strong><small>{summary.high_count} high · {summary.medium_count} medium</small></div>
        <div><span>DoobieLogic</span><strong>{summary.local_tracked_lot_count.toLocaleString()}</strong><small>tracked lots</small></div>
        <div><span>Metrc</span><strong>{summary.metrc_package_count.toLocaleString()}</strong><small>active packages</small></div>
      </div>
      {summary.status === "clean" ? <div className="success-banner"><strong>Package ledgers reconcile.</strong> No deterministic package discrepancies were found in this read.</div> : null}
      {summary.untracked_local_lot_count ? <div className="warning-banner">{summary.untracked_local_lot_count} local lot(s) have no traceability package id and were excluded from package matching.</div> : null}
      {report.data?.discrepancies.length ? <div className="table-wrap"><table>
        <thead><tr><th>Severity</th><th>Package</th><th>Issue</th><th>DoobieLogic</th><th>Metrc</th><th>What it means</th></tr></thead>
        <tbody>{report.data.discrepancies.map((row, index) => <tr key={`${row.package_id}-${row.code}-${index}`}>
          <td><strong>{row.severity.toUpperCase()}</strong></td>
          <td>{row.package_id || "—"}<br/><small>{row.product_name || ""}</small></td>
          <td>{label(row.code)}</td>
          <td>{quantity(row.local_quantity, row.local_unit)}{row.local_location ? <><br/><small>{row.local_location}</small></> : null}</td>
          <td>{quantity(row.metrc_quantity, row.metrc_unit)}{row.metrc_location ? <><br/><small>{row.metrc_location}</small></> : null}</td>
          <td>{row.message}</td>
        </tr>)}</tbody>
      </table></div> : null}
      <p className="source-caption">Facility license: {report.data.license_number || "—"} · Jurisdiction: {report.data.jurisdiction_code || "—"} · Environment: {report.data.environment || "—"}{report.data.compared_at ? ` · Compared ${new Date(report.data.compared_at).toLocaleString()}` : ""}</p>
    </> : null}
  </section>;
}

function quantity(value: number | null, unit: string) {
  if (value === null || value === undefined) return "—";
  return `${value.toLocaleString()}${unit ? ` ${unit}` : ""}`;
}

function label(code: string) {
  const labels: Record<string, string> = {
    missing_in_doobielogic: "Missing in DoobieLogic",
    missing_in_metrc: "Missing in Metrc",
    quantity_mismatch: "Quantity mismatch",
    unit_mismatch: "Unit mismatch",
    location_mismatch: "Location mismatch",
    lab_state_mismatch: "Lab-state mismatch",
    duplicate_local_package: "Duplicate local package",
    duplicate_metrc_package: "Duplicate Metrc package",
  };
  return labels[code] || code.replaceAll("_", " ");
}
