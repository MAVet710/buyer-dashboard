import { useSearchParams } from "react-router-dom";
import { BuyerCurrentInventory, BuyerUploadedSourceNotice } from "../components/BuyerCurrentInventory";
import { BuyerOperationsPage } from "./BuyerOperationsPage";

export function BuyerCommandCenterPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const [params, setParams] = useSearchParams();
  const historical = params.get("buyerView") === "forecast";
  const chooseView = (view: "current" | "forecast") => setParams(previous => {
    const next = new URLSearchParams(previous); next.set("buyerView", view); return next;
  });
  return <div className="page buyer-operations-workspace">
    {!historical ? <div className="page-heading"><div><div className="eyebrow">Purchasing</div><h1>Buyer Dashboard</h1><p>Current inventory and historical forecasting, with their sources kept clear.</p></div></div> : null}
    <div className="view-tabs parity-tabs" role="tablist" aria-label="Buyer data source">
      <button type="button" role="tab" className={!historical ? "active" : ""} aria-selected={!historical} onClick={() => chooseView("current")}>Current inventory</button>
      <button type="button" role="tab" className={historical ? "active" : ""} aria-selected={historical} onClick={() => chooseView("forecast")}>Uploaded forecast analysis</button>
    </div>
    {historical ? <><BuyerUploadedSourceNotice /><BuyerOperationsPage onNavigate={onNavigate} /></> : <BuyerCurrentInventory />}
  </div>;
}
