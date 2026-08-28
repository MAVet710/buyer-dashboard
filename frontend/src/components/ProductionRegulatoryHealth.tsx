import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../lib/api";

type ResourceView = {
  count: number;
  records_truncated: boolean;
  evidence: { source_url?: string; verified_on?: string } | null;
  records: Array<{
    provider_id?: string;
    label?: string;
    name?: string;
    status?: string;
    quantity?: number | null;
    unit_of_measure?: string;
    last_modified?: string;
  }>;
};

type ManufacturingSnapshot = {
  configured: boolean;
  ready: boolean;
  provider: string;
  scope: string;
  jurisdiction_code?: string;
  license_number?: string;
  environment?: string;
  read_only: boolean;
  message: string;
  summary?: {
    active_package_count: number;
    active_processing_job_count: number;
  };
  resources: {
    packages?: ResourceView;
    processing_jobs?: ResourceView;
  };
};

export function ProductionRegulatoryHealth() {
  const [open, setOpen] = useState(false);
  const snapshot = useQuery({
    queryKey: ["production-metrc-regulatory-health"],
    queryFn: ({ signal }) =>
      apiGet<ManufacturingSnapshot>(
        "/api/v1/inventory/production/regulatory/manufacturing",
        signal,
      ),
    enabled: open,
    retry: false,
  });

  return (
    <section className="inventory-panel production-regulatory-health">
      <div className="section-heading">
        <div>
          <div className="eyebrow">Production · Metrc</div>
          <h3>Regulatory Health</h3>
          <p className="source-caption">
            Read-only manufacturing check. Live Metrc data loads only when you request it.
          </p>
        </div>
        <button className="secondary" type="button" onClick={() => setOpen((value) => !value)}>
          {open ? "Hide Metrc" : "Check Metrc"}
        </button>
      </div>

      {!open ? <div className="empty">No live Metrc request has been made from this panel.</div> : null}
      {open && snapshot.isLoading ? <div className="state">Checking the verified manufacturing license…</div> : null}
      {open && snapshot.isError ? <div className="state error">{snapshot.error.message}</div> : null}
      {open && snapshot.data && !snapshot.data.ready ? (
        <div className="info-banner">{snapshot.data.message}</div>
      ) : null}
      {open && snapshot.data?.ready ? (
        <>
          <div className="metrics four">
            <Metric label="Active Packages" value={snapshot.data.summary?.active_package_count ?? 0} />
            <Metric label="Active Processing" value={snapshot.data.summary?.active_processing_job_count ?? 0} />
            <Metric label="Environment" value={snapshot.data.environment ?? "—"} />
            <Metric label="Jurisdiction" value={snapshot.data.jurisdiction_code ?? "—"} />
          </div>
          <p className="source-caption">
            License {snapshot.data.license_number || "—"} · read-only · exact trusted facility mapping
          </p>
          <ResourceTable title="Active processing jobs" resource={snapshot.data.resources.processing_jobs} />
        </>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function ResourceTable({ title, resource }: { title: string; resource?: ResourceView }) {
  if (!resource) return null;
  return (
    <div>
      <h4>{title}</h4>
      {resource.records.length ? (
        <div className="table-wrap">
          <table>
            <thead><tr><th>ID / Label</th><th>Name</th><th>Status</th><th>Last Modified</th></tr></thead>
            <tbody>
              {resource.records.map((row, index) => (
                <tr key={`${row.provider_id || row.label || "record"}-${index}`}>
                  <td>{row.label || row.provider_id || "—"}</td>
                  <td>{row.name || "—"}</td>
                  <td>{row.status || "—"}</td>
                  <td>{row.last_modified || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <div className="empty">No active Metrc processing jobs were returned.</div>}
      {resource.records_truncated ? <p className="source-caption">Showing the first 100 records.</p> : null}
    </div>
  );
}
