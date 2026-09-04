import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type ProcessingJob = {
  provider_id?: string;
  name?: string;
  status?: string;
  job_type?: string;
  location?: string;
  package_label?: string;
  started_at?: string;
  last_modified?: string;
};

type ManufacturingSnapshot = {
  configured: boolean;
  ready: boolean;
  provider: string;
  scope: string;
  jurisdiction_code?: string;
  license_number?: string;
  environment?: string;
  source?: string;
  network_request_made?: boolean;
  last_synced_at?: string | null;
  message: string;
  summary: {
    active_package_count: number;
    active_processing_job_count: number;
  };
  resources: {
    packages?: { count: number; status?: string; complete?: boolean };
    processing_jobs?: {
      count: number;
      status?: string;
      complete?: boolean;
      records?: ProcessingJob[];
      records_truncated?: boolean;
    };
  };
};

export function ProductionRegulatoryState() {
  const synced = useQuery({
    queryKey: ["production-metrc-regulatory-snapshot"],
    queryFn: ({ signal }) =>
      apiGet<ManufacturingSnapshot>("/api/v1/inventory/production/regulatory/manufacturing-snapshot", signal),
    retry: false,
  });
  const live = useQuery({
    queryKey: ["production-metrc-regulatory-live"],
    queryFn: ({ signal }) =>
      apiGet<ManufacturingSnapshot>("/api/v1/inventory/production/regulatory/manufacturing", signal),
    enabled: false,
    retry: false,
  });
  const active = live.data ?? synced.data;
  const jobs = active?.resources?.processing_jobs?.records ?? [];
  const sourceCaption = live.data
    ? "Live Metrc verification · provider request made explicitly by the operator"
    : active?.last_synced_at
      ? `Last synchronized ${new Date(active.last_synced_at).toLocaleString()} · no Metrc request on page load`
      : "Synchronized manufacturing state loads locally; live Metrc verification is optional.";

  if (synced.isLoading && !active) return <div className="state">Loading synchronized manufacturing state…</div>;
  if (synced.isError && !active) return <div className="form-error">{synced.error.message}</div>;

  return (
    <section className="inventory-panel production-regulatory-state">
      <div className="section-heading">
        <div>
          <div className="eyebrow">Production · Metrc</div>
          <h3>Regulatory State</h3>
          <p className="source-caption">Active packages and Metrc processing jobs appear from the last facility sync without delaying Production Ops.</p>
        </div>
        <button className="secondary" type="button" disabled={live.isFetching} onClick={() => void live.refetch()}>
          {live.isFetching ? "Verifying…" : "Verify live"}
        </button>
      </div>

      {live.isError ? <div className="form-error">Live Metrc verification failed: {live.error.message}. The synchronized state remains available.</div> : null}
      {active && !active.configured ? <div className="info-banner">{active.message}</div> : null}
      {active?.configured && !active.ready ? <div className="info-banner">{active.message}</div> : null}

      {active?.configured ? (
        <>
          <div className="metrics four">
            <Metric label="Metrc Packages" value={active.summary.active_package_count} />
            <Metric label="Processing Jobs" value={active.summary.active_processing_job_count} />
            <Metric label="Environment" value={active.environment ?? "—"} />
            <Metric label="Mode" value={live.data ? "Live check" : "Synced"} />
          </div>
          <p className="source-caption">{sourceCaption}</p>
          <p className="source-caption">License {active.license_number || "—"} · {active.jurisdiction_code || "—"} · provider-owned processing history remains read-only</p>

          {jobs.length ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Processing Job</th><th>Status</th><th>Type</th><th>Location</th><th>Package</th></tr></thead>
                <tbody>
                  {jobs.slice(0, 100).map((job, index) => (
                    <tr key={job.provider_id || `${job.name}-${index}`}>
                      <td>{job.name || job.provider_id || "Metrc processing job"}</td>
                      <td><span className="badge">{job.status || "Active"}</span></td>
                      <td>{job.job_type || "—"}</td>
                      <td>{job.location || "—"}</td>
                      <td>{job.package_label || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {active.resources.processing_jobs?.records_truncated ? <p className="source-caption">Showing the first 100 synchronized processing jobs.</p> : null}
            </div>
          ) : active.ready ? <div className="empty">No active Metrc processing jobs are present in the synchronized facility snapshot.</div> : null}
        </>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}
