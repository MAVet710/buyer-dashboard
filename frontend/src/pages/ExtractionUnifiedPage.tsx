import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../lib/api";
import type { InventoryResponse } from "../types/inventory";
import { ExtractionCommandCenterPage } from "./ExtractionCommandCenterPage";
import { ExtractionPage } from "./ExtractionPage";

type View = "command" | "process" | "inventory";
type Lot = {
  lot_id: string;
  product_name: string;
  lot_code: string;
  compliance_package_id: string;
  available: number;
  unit: string;
  location?: string;
  status?: string;
};

export function ExtractionUnifiedPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const [view, setView] = useState<View>("command");
  const lots = useQuery({
    queryKey: ["extraction-unified-lots"],
    queryFn: ({ signal }) => apiGet<Lot[]>("/api/v1/extraction/lots", signal),
    enabled: view === "inventory",
  });
  const productionInventory = useQuery({
    queryKey: ["extraction-production-inventory-fallback"],
    queryFn: ({ signal }) => apiGet<InventoryResponse>("/api/v1/inventory/production/packages?view=all", signal),
    enabled: view === "inventory",
  });

  const fallbackLots: Lot[] = (productionInventory.data?.items ?? [])
    .filter(row => Number(row.available || 0) > 0 && ["available", "reserved"].includes(String(row.status || "").toLowerCase()))
    .map(row => ({
      lot_id: row.id,
      product_name: row.product_name,
      lot_code: row.lot_code,
      compliance_package_id: row.package_id,
      available: Number(row.available || 0),
      unit: row.unit,
      location: row.location,
      status: row.status,
    }));
  const inventoryRows = lots.data?.length ? lots.data : fallbackLots;
  const inventoryLoading = lots.isLoading && productionInventory.isLoading;
  const fallbackActive = !lots.isLoading && (!lots.data?.length || lots.isError) && fallbackLots.length > 0;
  const inventoryFailed = lots.isError && productionInventory.isError;

  return <div className="page extraction-unified">
    <div className="page-heading">
      <div>
        <div className="eyebrow">Production Ops · Extraction</div>
        <h1>Extraction Command Center</h1>
        <p>The full Buyer Dash extraction workflow in one place: operating analytics, durable Run 360, process stages, inventory inputs, outputs and QA, COGS, toll work, traceability/METRC, data input and Doobie.</p>
      </div>
    </div>
    <div className="view-tabs parity-tabs">
      <button className={view === "command" ? "active" : ""} onClick={() => setView("command")}>Command Center</button>
      <button className={view === "process" ? "active" : ""} onClick={() => setView("process")}>Run 360 / Process Tracker</button>
      <button className={view === "inventory" ? "active" : ""} onClick={() => setView("inventory")}>Extraction Inventory</button>
    </div>

    {view === "command" ? <div className="embedded-workspace"><ExtractionCommandCenterPage onNavigate={onNavigate} /></div> : null}
    {view === "process" ? <div className="embedded-workspace"><ExtractionPage onNavigate={onNavigate} /></div> : null}
    {view === "inventory" ? <section className="inventory-panel">
      <div className="section-heading"><div><div className="eyebrow">Extraction Inventory</div><h2>Available input lots</h2><p>Reservation-aware durable facility lots available to reserve into extraction runs. If that feed is unavailable, DoobieLogic falls back to the same Production Inventory package source instead of leaving this workspace blank.</p></div></div>
      {inventoryLoading ? <div className="state">Loading extraction inventory…</div> : null}
      {fallbackActive ? <div className="info-banner">The extraction reservation feed did not return usable rows, so this view is showing eligible Production Inventory lots. Run 360 will still validate availability again when material is reserved.</div> : null}
      {inventoryFailed ? <div className="state error">Extraction inventory could not be loaded. {lots.error.message} · {productionInventory.error.message}</div> : null}
      <div className="metrics">
        <div className="metric"><span>Available lots</span><strong>{inventoryRows.length}</strong></div>
        <div className="metric"><span>Total available</span><strong>{inventoryRows.reduce((sum, row) => sum + Number(row.available || 0), 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}</strong></div>
      </div>
      <div className="table-wrap"><table><thead><tr><th>Material</th><th>Lot</th><th>METRC / external package</th><th>Location</th><th>Available</th></tr></thead><tbody>{inventoryRows.map(row => <tr key={row.lot_id}><td><strong>{row.product_name}</strong></td><td>{row.lot_code}</td><td>{row.compliance_package_id || "—"}</td><td>{row.location || "—"}</td><td>{Number(row.available || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })} {row.unit}</td></tr>)}</tbody></table>{!inventoryLoading && !inventoryRows.length ? <div className="empty">No available extraction input lots in this facility.</div> : null}</div>
    </section> : null}
  </div>;
}
