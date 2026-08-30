import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../lib/api";

type TransferControlSnapshot = {
  metrics: {
    outgoing_open: number;
    inbound_open: number;
    provider_in_flight: number;
    exceptions: number;
    verified: number;
  };
  outgoing: Array<{
    proposal_id: string;
    title: string;
    stage: string;
    proposal_status: string;
    traceability_status: string;
    transaction_id: string;
    external_reference: string;
    order_number: string;
    customer: string;
    customer_license: string;
    package_count: number;
    departure: string;
    arrival: string;
    route: string;
    financial_impact_usd: number;
    error_message: string;
    mismatch_reason: string;
  }>;
  inbound: Array<{
    preflight_id: string;
    transfer_id: string;
    operation: string;
    status: string;
    manifest: string;
    vendor: string;
    vendor_license: string;
    package_count: number;
    expires_at: string | null;
    consumed_at: string | null;
    received_count: number;
    reason: string;
  }>;
  exceptions: Array<{
    kind: string;
    reference: string;
    status: string;
    message: string;
    proposal_id?: string;
    preflight_id?: string;
    transaction_id?: string;
    operation_type?: string;
  }>;
  policy: {
    live_sandbox_promotion_enabled: boolean;
    provider_network_calls_from_this_view: boolean;
    inbound_accept_write_enabled: boolean;
    message: string;
  };
};

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
  const transferControl = useQuery({
    queryKey: ["transfer-control"],
    queryFn: ({ signal }) => apiGet<TransferControlSnapshot>("/api/v1/inventory/transfer-control", signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
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
        <div className="eyebrow">TRANSFER CONTROL</div>
        <h2>Manifests, Receiving & Reconciliation</h2>
        <p className="source-caption">Durable DoobieLogic transfer state loads without contacting Metrc. Live provider reads stay optional and separate while sandbox credentials and write promotion are pending.</p>
      </div>
      <button className="secondary" type="button" onClick={() => setOpen(value => !value)}>{open ? "Hide live Metrc" : "Check live Metrc"}</button>
    </div>

    {transferControl.isLoading ? <div className="state">Loading durable transfer state…</div> : null}
    {transferControl.isError ? <div className="state error">Transfer Control could not load: {transferControl.error.message}</div> : null}
    {transferControl.data ? <>
      <div className="metrics four">
        <Metric label="Outgoing Open" value={transferControl.data.metrics.outgoing_open}/>
        <Metric label="Inbound Open" value={transferControl.data.metrics.inbound_open}/>
        <Metric label="Provider In Flight" value={transferControl.data.metrics.provider_in_flight}/>
        <Metric label="Needs Attention" value={transferControl.data.metrics.exceptions}/>
      </div>
      <div className="info-banner"><strong>Credential-independent control:</strong> {transferControl.data.policy.message}</div>

      {transferControl.data.exceptions.length ? <div className="warning-banner">
        <strong>Transfer exceptions requiring review</strong>
        <div className="table-wrap"><table>
          <thead><tr><th>Flow</th><th>Reference</th><th>Status</th><th>What needs attention</th></tr></thead>
          <tbody>{transferControl.data.exceptions.slice(0, 20).map((row, index) => <tr key={`${row.kind}-${row.reference}-${index}`}>
            <td>{row.kind}</td><td><strong>{row.reference || "—"}</strong></td><td>{label(row.status)}</td><td>{row.message}</td>
          </tr>)}</tbody>
        </table></div>
      </div> : <div className="success-banner"><strong>No durable transfer exceptions need attention.</strong><br/><span>Stale receiving snapshots, unknown receipt outcomes, rejected provider actions, and reconciliation-required transactions will surface here.</span></div>}

      <div className="section-heading"><div><div className="eyebrow">OUTBOUND</div><h3>Sales Order → Manifest</h3><p className="source-caption">Tracks the existing human-controlled manifest draft and traceability lifecycle without making a provider request.</p></div></div>
      {transferControl.data.outgoing.length ? <div className="table-wrap"><table>
        <thead><tr><th>Order</th><th>Customer</th><th>Packages</th><th>Stage</th><th>Departure</th><th>Value</th></tr></thead>
        <tbody>{transferControl.data.outgoing.slice(0, 25).map(row => <tr key={row.proposal_id}>
          <td><strong>{row.order_number || row.title}</strong><br/><small>{row.external_reference || row.transaction_id || "Draft only"}</small></td>
          <td>{row.customer || "—"}<br/><small>{row.customer_license || "—"}</small></td>
          <td>{row.package_count}</td><td>{label(row.stage)}</td><td>{dateTime(row.departure)}</td><td>{money(row.financial_impact_usd)}</td>
        </tr>)}</tbody>
      </table></div> : <div className="empty">No manifest drafts have been created for this facility yet.</div>}

      <div className="section-heading"><div><div className="eyebrow">INBOUND</div><h3>Transfer → Verified Receipt</h3><p className="source-caption">Prepared inbound snapshots must still pass the existing second-read provider match before local inventory posts.</p></div></div>
      {transferControl.data.inbound.length ? <div className="table-wrap"><table>
        <thead><tr><th>Manifest / Transfer</th><th>Vendor</th><th>Packages</th><th>Operation</th><th>Status</th><th>Expires / Completed</th></tr></thead>
        <tbody>{transferControl.data.inbound.slice(0, 25).map(row => <tr key={row.preflight_id}>
          <td><strong>{row.manifest || row.transfer_id}</strong><br/><small>{row.transfer_id}</small></td>
          <td>{row.vendor || "—"}<br/><small>{row.vendor_license || "—"}</small></td><td>{row.package_count}</td><td>{label(row.operation)}</td><td>{label(row.status)}</td><td>{row.consumed_at ? dateTime(row.consumed_at) : dateTime(row.expires_at)}</td>
        </tr>)}</tbody>
      </table></div> : <div className="empty">No controlled receiving preflights have been recorded for this facility yet.</div>}
    </> : null}

    <div className="section-heading" style={{marginTop: 20}}>
      <div><div className="eyebrow">OPTIONAL LIVE READ</div><h3>Metrc Regulatory Health</h3><p className="source-caption">Read-only outbound transfer, manifest, delivery, transporter, vehicle, and wholesale-package visibility. This section contacts Metrc only when requested.</p></div>
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

function label(value:string) {
  return value ? value.replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase()) : "—";
}

function money(value:number) {
  return new Intl.NumberFormat("en-US", {style:"currency", currency:"USD", maximumFractionDigits:0}).format(value || 0);
}

function dateTime(value:string|null|undefined) {
  if(!value)return "—";
  const parsed=new Date(value);
  return Number.isNaN(parsed.getTime())?value:parsed.toLocaleString();
}
