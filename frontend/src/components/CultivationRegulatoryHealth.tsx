import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type CultivationSnapshot = {
  configured: boolean;
  ready: boolean;
  jurisdiction_code?: string;
  license_number?: string;
  environment?: string;
  read_only: boolean;
  source?: string;
  network_request_made?: boolean;
  last_synced_at?: string | null;
  message: string;
  summary?: {
    active_plant_batch_count: number;
    vegetative_plant_count: number;
    flowering_plant_count: number;
    active_harvest_count: number;
  };
  reconciliation: null | {
    summary: {
      status: string;
      matched_plant_count: number;
      discrepancy_count: number;
      high_count: number;
      medium_count: number;
      local_immature_unreconciled_count: number;
    };
    discrepancies: Array<{
      code: string;
      severity: string;
      plant_tag: string;
      local_phase: string;
      metrc_phase: string;
      local_room: string;
      metrc_room: string;
      message: string;
    }>;
  };
};

export function CultivationRegulatoryHealth() {
  const synced = useQuery({
    queryKey: ["cultivation-metrc-regulatory-snapshot"],
    queryFn: ({ signal }) =>
      apiGet<CultivationSnapshot>("/api/v1/inventory/production/plants/regulatory-snapshot", signal),
    retry: false,
  });
  const live = useQuery({
    queryKey: ["cultivation-metrc-regulatory-live"],
    queryFn: ({ signal }) =>
      apiGet<CultivationSnapshot>("/api/v1/inventory/production/plants/regulatory", signal),
    enabled: false,
    retry: false,
  });

  const active = live.data ?? synced.data;
  const reconciliation = active?.reconciliation;
  const sourceCaption = live.data
    ? "Live Metrc verification · provider request made explicitly by the operator"
    : active?.last_synced_at
      ? `Last synchronized ${new Date(active.last_synced_at).toLocaleString()} · no Metrc request on page load`
      : "Synchronized regulatory state loads locally; live Metrc verification is optional.";

  return (
    <section className="inventory-panel cultivation-regulatory-health">
      <div className="section-heading">
        <div>
          <div className="eyebrow">Cultivation · Metrc</div>
          <h3>Regulatory Health</h3>
          <p className="source-caption">Plant batches, active plants, and harvests appear from the last complete facility sync. Use live verification only when you need a fresh provider check.</p>
        </div>
        <button className="secondary" type="button" disabled={live.isFetching} onClick={() => void live.refetch()}>
          {live.isFetching ? "Verifying…" : "Verify live"}
        </button>
      </div>

      {synced.isLoading && !active ? <div className="state">Loading synchronized cultivation state…</div> : null}
      {synced.isError && !active ? <div className="state error">{synced.error.message}</div> : null}
      {live.isError ? <div className="state error">Live Metrc verification failed: {live.error.message}. The last synchronized state remains visible below.</div> : null}
      {active && !active.configured ? <div className="info-banner">{active.message}</div> : null}
      {active?.configured && !active.ready ? <div className="info-banner">{active.message}</div> : null}

      {active?.configured && active.summary ? (
        <>
          <div className="metrics four">
            <Metric label="Plant Batches" value={active.summary.active_plant_batch_count} />
            <Metric label="Vegetative" value={active.summary.vegetative_plant_count} />
            <Metric label="Flowering" value={active.summary.flowering_plant_count} />
            <Metric label="Active Harvests" value={active.summary.active_harvest_count} />
          </div>
          <div className="metrics four">
            <Metric label="Matched Tags" value={reconciliation?.summary.matched_plant_count ?? 0} />
            <Metric label="Discrepancies" value={reconciliation?.summary.discrepancy_count ?? 0} />
            <Metric label="High Priority" value={reconciliation?.summary.high_count ?? 0} />
            <Metric label="Environment" value={active.environment ?? "—"} />
          </div>
          <p className="source-caption">{sourceCaption}</p>
          <p className="source-caption">License {active.license_number || "—"} · {active.jurisdiction_code || "—"} · read-only regulatory mirror</p>

          {reconciliation?.discrepancies.length ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Severity</th><th>Plant Tag</th><th>Issue</th><th>DoobieLogic</th><th>Metrc</th></tr></thead>
                <tbody>
                  {reconciliation.discrepancies.slice(0, 100).map((row, index) => (
                    <tr key={`${row.plant_tag}-${row.code}-${index}`}>
                      <td><span className="badge">{row.severity}</span></td>
                      <td>{row.plant_tag}</td>
                      <td>{row.message}</td>
                      <td>{[row.local_phase, row.local_room].filter(Boolean).join(" · ") || "—"}</td>
                      <td>{[row.metrc_phase, row.metrc_room].filter(Boolean).join(" · ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : reconciliation ? <div className="empty">Tagged vegetative and flowering plants match the synchronized Metrc plant state.</div> : null}

          {(reconciliation?.summary.local_immature_unreconciled_count ?? 0) > 0 ? (
            <p className="source-caption">{reconciliation?.summary.local_immature_unreconciled_count} local clone/seedling record(s) remain outside individual-tag reconciliation and are represented separately by Metrc plant batches.</p>
          ) : null}
          {!reconciliation && active.ready === false ? <div className="empty">Plant reconciliation is withheld until both synchronized vegetative and flowering snapshots are complete.</div> : null}
        </>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}
