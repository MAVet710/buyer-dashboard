import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../lib/api";

type CultivationSnapshot = {
  configured: boolean;
  ready: boolean;
  jurisdiction_code?: string;
  license_number?: string;
  environment?: string;
  read_only: boolean;
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
  const [open, setOpen] = useState(false);
  const snapshot = useQuery({
    queryKey: ["cultivation-metrc-regulatory-health"],
    queryFn: ({ signal }) =>
      apiGet<CultivationSnapshot>("/api/v1/inventory/production/plants/regulatory", signal),
    enabled: open,
    retry: false,
  });

  const reconciliation = snapshot.data?.reconciliation;
  return (
    <section className="inventory-panel cultivation-regulatory-health">
      <div className="section-heading">
        <div>
          <div className="eyebrow">Cultivation · Metrc</div>
          <h3>Regulatory Health</h3>
          <p className="source-caption">Read-only plant, batch, and harvest check. Metrc loads only when requested.</p>
        </div>
        <button className="secondary" type="button" onClick={() => setOpen((value) => !value)}>
          {open ? "Hide Metrc" : "Check Metrc"}
        </button>
      </div>
      {!open ? <div className="empty">No live Metrc request has been made from this panel.</div> : null}
      {open && snapshot.isLoading ? <div className="state">Checking the verified cultivation license…</div> : null}
      {open && snapshot.isError ? <div className="state error">{snapshot.error.message}</div> : null}
      {open && snapshot.data && !snapshot.data.ready ? <div className="info-banner">{snapshot.data.message}</div> : null}
      {open && snapshot.data?.ready ? (
        <>
          <div className="metrics four">
            <Metric label="Plant Batches" value={snapshot.data.summary?.active_plant_batch_count ?? 0} />
            <Metric label="Vegetative" value={snapshot.data.summary?.vegetative_plant_count ?? 0} />
            <Metric label="Flowering" value={snapshot.data.summary?.flowering_plant_count ?? 0} />
            <Metric label="Active Harvests" value={snapshot.data.summary?.active_harvest_count ?? 0} />
          </div>
          <div className="metrics four">
            <Metric label="Matched Tags" value={reconciliation?.summary.matched_plant_count ?? 0} />
            <Metric label="Discrepancies" value={reconciliation?.summary.discrepancy_count ?? 0} />
            <Metric label="High Priority" value={reconciliation?.summary.high_count ?? 0} />
            <Metric label="Environment" value={snapshot.data.environment ?? "—"} />
          </div>
          <p className="source-caption">License {snapshot.data.license_number || "—"} · {snapshot.data.jurisdiction_code || "—"} · read-only · exact trusted facility mapping</p>
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
          ) : reconciliation ? <div className="empty">Tagged vegetative and flowering plants match the active Metrc plant reads.</div> : null}
          {(reconciliation?.summary.local_immature_unreconciled_count ?? 0) > 0 ? (
            <p className="source-caption">{reconciliation?.summary.local_immature_unreconciled_count} local clone/seedling record(s) remain outside individual-tag reconciliation and are represented separately by Metrc plant batches.</p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}
