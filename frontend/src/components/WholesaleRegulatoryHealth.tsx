import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../lib/api";

type WholesaleRegulatorySnapshot = {
  configured: boolean;
  ready: boolean;
  jurisdiction_code?: string;
  license_number?: string;
  environment?: string;
  read_only: boolean;
  message: string;
  summary?: {
    outgoing_transfer_count: number;
    manifest_reference_count: number;
    expanded_transfer_count: number;
    delivery_count: number;
    wholesale_package_count: number;
    transfer_template_count: number;
    transporter_driver_count: number;
    transporter_vehicle_count: number;
    expansion_limited: boolean;
  };
  resources: {
    transfer_templates?: { available: boolean; message?: string };
    transporter_drivers?: { available: boolean; message?: string };
    transporter_vehicles?: { available: boolean; message?: string };
  };
  transfers: Array<{
    transfer_id: string;
    manifest_number: string;
    status: string;
    recipient: string;
    recipient_license: string;
    created_at: string;
    delivery_count: number;
    wholesale_package_count: number;
  }>;
  warnings: string[];
};

export function WholesaleRegulatoryHealth() {
  const [open, setOpen] = useState(false);
  const snapshot = useQuery({
    queryKey: ["wholesale-metrc-regulatory-health"],
    queryFn: ({ signal }) =>
      apiGet<WholesaleRegulatorySnapshot>("/api/v1/inventory/wholesale/regulatory", signal),
    enabled: open,
    retry: false,
  });

  return <section className="inventory-panel wholesale-regulatory-health">
    <div className="section-heading">
      <div>
        <div className="eyebrow">WHOLESALE · METRC</div>
        <h2>Regulatory Health</h2>
        <p className="source-caption">Read-only outbound transfer, manifest, delivery, transporter, vehicle, and wholesale-package visibility. Metrc loads only when requested.</p>
      </div>
      <button className="secondary" type="button" onClick={() => setOpen(value => !value)}>{open ? "Hide Metrc" : "Check Metrc"}</button>
    </div>
    {!open ? <div className="empty">No live Metrc request has been made from Wholesale Ops.</div> : null}
    {open && snapshot.isLoading ? <div className="state">Checking the verified wholesale facility mapping…</div> : null}
    {open && snapshot.isError ? <div className="state error">{snapshot.error.message}</div> : null}
    {open && snapshot.data && !snapshot.data.ready ? <div className="info-banner">{snapshot.data.message}</div> : null}
    {open && snapshot.data?.ready ? <>
      <div className="metrics four">
        <Metric label="Outgoing Transfers" value={snapshot.data.summary?.outgoing_transfer_count ?? 0}/>
        <Metric label="Manifest Refs" value={snapshot.data.summary?.manifest_reference_count ?? 0}/>
        <Metric label="Deliveries" value={snapshot.data.summary?.delivery_count ?? 0}/>
        <Metric label="Wholesale Packages" value={snapshot.data.summary?.wholesale_package_count ?? 0}/>
      </div>
      <div className="metrics four">
        <Metric label="Transfer Templates" value={snapshot.data.summary?.transfer_template_count ?? 0}/>
        <Metric label="Drivers" value={snapshot.data.summary?.transporter_driver_count ?? 0}/>
        <Metric label="Vehicles" value={snapshot.data.summary?.transporter_vehicle_count ?? 0}/>
        <Metric label="Environment" value={snapshot.data.environment ?? "—"}/>
      </div>
      <p className="source-caption">License {snapshot.data.license_number || "—"} · {snapshot.data.jurisdiction_code || "—"} · read-only · exact trusted facility mapping. Manifest references are shown here; manifest PDFs remain provider documents and are not modified by this view.</p>
      {snapshot.data.transfers.length ? <div className="table-wrap"><table>
        <thead><tr><th>Manifest</th><th>Recipient</th><th>Status</th><th>Deliveries</th><th>Wholesale Packages</th></tr></thead>
        <tbody>{snapshot.data.transfers.map((row, index) => <tr key={`${row.transfer_id || row.manifest_number || "transfer"}-${index}`}>
          <td><strong>{row.manifest_number || "—"}</strong><br/><small>{row.transfer_id || "No transfer id"}</small></td>
          <td>{row.recipient || "—"}<br/><small>{row.recipient_license || "—"}</small></td>
          <td>{row.status || "—"}</td>
          <td>{row.delivery_count}</td>
          <td>{row.wholesale_package_count}</td>
        </tr>)}</tbody>
      </table></div> : <div className="empty">No outgoing Metrc transfers were returned for this mapped facility.</div>}
      {snapshot.data.summary?.expansion_limited ? <div className="info-banner">The transfer list is larger than the safe expansion window. The first 50 transfers were expanded into delivery/package detail.</div> : null}
      {snapshot.data.warnings.length ? <div className="info-banner"><strong>Metrc read notes</strong><ul>{snapshot.data.warnings.slice(0, 10).map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul></div> : null}
    </> : null}
  </section>;
}

function Metric({label,value}:{label:string;value:string|number}) {
  return <article className="metric"><span>{label}</span><strong>{value}</strong></article>;
}
