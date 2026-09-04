import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type RegulatoryRow = {
  provider_id?: string;
  status?: string;
  receipt_number?: string;
  delivery_number?: string;
  recorded_at?: string;
  total?: string;
};

type RetailSnapshot = {
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
    active_sales_receipt_count: number;
    active_sales_delivery_count: number;
  };
  resources: {
    sales_receipts?: { count: number; status?: string; complete?: boolean; records?: RegulatoryRow[] };
    sales_deliveries?: { count: number; status?: string; complete?: boolean; records?: RegulatoryRow[] };
  };
};

export function RetailRegulatoryState() {
  const snapshot = useQuery({
    queryKey: ["retail-metrc-regulatory-snapshot"],
    queryFn: ({ signal }) => apiGet<RetailSnapshot>("/api/v1/retail-insights/regulatory-snapshot", signal),
    retry: false,
  });

  if (snapshot.isLoading) return <div className="state">Loading synchronized retail regulatory state…</div>;
  if (snapshot.isError) return <div className="state error">Synchronized Metrc retail state could not be loaded: {snapshot.error.message}</div>;
  const data = snapshot.data;
  if (!data) return null;

  const recent = [
    ...(data.resources.sales_receipts?.records ?? []).map(row => ({ ...row, kind: "Receipt" })),
    ...(data.resources.sales_deliveries?.records ?? []).map(row => ({ ...row, kind: "Delivery" })),
  ].slice(0, 10);

  return (
    <section className="inventory-panel retail-regulatory-state">
      <div className="section-heading">
        <div>
          <div className="eyebrow">Retail · Metrc regulatory mirror</div>
          <h2>Synchronized Sales State</h2>
          <p>{data.message}</p>
        </div>
      </div>
      {!data.configured ? <div className="info-banner">{data.message}</div> : null}
      {data.configured ? (
        <>
          <div className="metrics four">
            <Metric label="Metrc receipts" value={data.summary.active_sales_receipt_count} />
            <Metric label="Metrc deliveries" value={data.summary.active_sales_delivery_count} />
            <Metric label="Environment" value={data.environment ?? "—"} />
            <Metric label="Source" value="Synced" />
          </div>
          <p className="source-caption">
            {data.last_synced_at ? `Last synchronized ${new Date(data.last_synced_at).toLocaleString()} · ` : ""}
            no Metrc request on page load · provider records remain read-only and do not fabricate local POS sales
          </p>
          {recent.length ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Provider record</th><th>Reference</th><th>Status</th><th>Recorded</th></tr></thead>
                <tbody>
                  {recent.map((row, index) => (
                    <tr key={`${row.kind}-${row.provider_id || index}`}>
                      <td>{row.kind}</td>
                      <td>{row.receipt_number || row.delivery_number || row.provider_id || "—"}</td>
                      <td>{row.status || "—"}</td>
                      <td>{row.recorded_at ? new Date(row.recorded_at).toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : data.ready ? <div className="empty">No active Metrc sales receipt or delivery records are present in the synchronized snapshot.</div> : null}
        </>
      ) : null}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <article className="metric"><span>{label}</span><strong>{value}</strong></article>;
}
