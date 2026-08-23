import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../lib/api";
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
};

export function ExtractionUnifiedPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const [view, setView] = useState<View>("command");
  const lots = useQuery({
    queryKey: ["extraction-unified-lots"],
    queryFn: ({ signal }) => apiGet<Lot[]>("/api/v1/extraction/lots", signal),
    enabled: view === "inventory",
  });

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
      <div className="section-heading"><div><div className="eyebrow">Extraction Inventory</div><h2>Available input lots</h2><p>Durable facility lots available to reserve into extraction runs. Open Run 360 to reserve, consume, release and trace material through the process.</p></div></div>
      {lots.isLoading ? <div className="state">Loading extraction inventory…</div> : null}
      {lots.isError ? <div className="state error">{lots.error.message}</div> : null}
      <div className="metrics">
        <div className="metric"><span>Available lots</span><strong>{lots.data?.length ?? 0}</strong></div>
        <div className="metric"><span>Total available</span><strong>{(lots.data ?? []).reduce((sum, row) => sum + Number(row.available || 0), 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}</strong></div>
      </div>
      <div className="table-wrap"><table><thead><tr><th>Material</th><th>Lot</th><th>METRC package</th><th>Available</th></tr></thead><tbody>{(lots.data ?? []).map(row => <tr key={row.lot_id}><td><strong>{row.product_name}</strong></td><td>{row.lot_code}</td><td>{row.compliance_package_id || "—"}</td><td>{Number(row.available || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })} {row.unit}</td></tr>)}</tbody></table>{!lots.isLoading && !(lots.data?.length) ? <div className="empty">No available extraction input lots in this facility.</div> : null}</div>
    </section> : null}
  </div>;
}
