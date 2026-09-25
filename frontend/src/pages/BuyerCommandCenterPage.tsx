import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BuyerCurrentInventory, BuyerUploadedSourceNotice } from "../components/BuyerCurrentInventory";
import { BuyerOperationsPage } from "./BuyerOperationsPage";

export type BuyerView = "today" | "decide" | "act" | "analyze";
const views: BuyerView[] = ["today", "decide", "act", "analyze"];

export function BuyerCommandCenterPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const [params, setParams] = useSearchParams();
  const requested = params.get("buyerView");
  const view: BuyerView = requested === "forecast" ? "analyze" : requested === "current" ? "act" : views.includes(requested as BuyerView) ? requested as BuyerView : "today";
  const chooseView = (nextView: BuyerView) => setParams(previous => {
    const next = new URLSearchParams(previous); next.set("buyerView", nextView); return next;
  });
  return <div className="page buyer-operations-workspace">
    <div className="page-heading"><div><div className="eyebrow">Purchasing</div><h1>Buyer Dashboard</h1><p>Review exceptions, decide what matters, then act.</p></div></div>
    <div className="view-tabs parity-tabs buyer-flow-tabs" role="tablist" aria-label="Buyer workflow">
      {views.map((item, index) => <button key={item} id={`buyer-tab-${item}`} type="button" role="tab" aria-controls="buyer-panel" tabIndex={view === item ? 0 : -1} className={view === item ? "active" : ""} aria-selected={view === item} onClick={() => chooseView(item)} onKeyDown={event => {
        const next = event.key === "ArrowRight" ? views[(index + 1) % views.length] : event.key === "ArrowLeft" ? views[(index + views.length - 1) % views.length] : event.key === "Home" ? views[0] : event.key === "End" ? views[views.length - 1] : null;
        if (next) { event.preventDefault(); chooseView(next); document.getElementById(`buyer-tab-${next}`)?.focus(); }
      }}>{item[0].toUpperCase() + item.slice(1)}</button>)}
    </div>
    <div role="tabpanel" id="buyer-panel" aria-labelledby={`buyer-tab-${view}`}>
      {view === "today" ? <><BuyerCurrentInventory compact /><div className="heading-actions"><button className="primary" onClick={() => chooseView("decide")}>Review reorder decisions</button><button className="secondary" onClick={() => chooseView("act")}>Review current inventory</button></div></> : null}
      {view === "act" ? <section className="inventory-panel"><h2>Purchasing actions</h2><p>Verify current stock before turning uploaded recommendations into an order.</p><button className="primary" onClick={() => onNavigate("Purchase Orders")}>Open Purchase Orders</button><CurrentInventoryDisclosure /></section> : null}
      {view !== "today" ? <BuyerUploadedSourceNotice /> : null}
      <BuyerOperationsPage view={view} onViewChange={chooseView} />
    </div>
  </div>;
}

function CurrentInventoryDisclosure() {
  const [open, setOpen] = useState(false);
  return <details className="streamlit-expander" onToggle={event => setOpen(event.currentTarget.open)}><summary>Current inventory</summary>{open ? <BuyerCurrentInventory /> : null}</details>;
}
