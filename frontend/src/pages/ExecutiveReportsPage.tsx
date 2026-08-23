import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiDownload, apiGet, downloadBlob } from "../lib/api";

type ReportItem = { key: string; label: string; capability: string };
type Catalog = { items: ReportItem[] };
type PackKey = "retail" | "production" | "company";
type BuyerControls = { target_doh: number; velocity_adjustment: number; sales_days: number; sku_window: number };

function currentWhiteLabelPayload(): unknown {
  try {
    const raw = sessionStorage.getItem("white-label-current-report-payload");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function currentBuyerControls(): BuyerControls {
  const fallback: BuyerControls = { target_doh: 21, velocity_adjustment: 0.5, sales_days: 60, sku_window: 56 };
  try {
    const raw = sessionStorage.getItem("buyer-dash-buyer-controls");
    if (!raw) return fallback;
    const value = JSON.parse(raw) as Partial<BuyerControls>;
    return {
      target_doh: Number(value.target_doh ?? fallback.target_doh),
      velocity_adjustment: Number(value.velocity_adjustment ?? fallback.velocity_adjustment),
      sales_days: Number(value.sales_days ?? fallback.sales_days),
      sku_window: Number(value.sku_window ?? fallback.sku_window),
    };
  } catch {
    return fallback;
  }
}

function localDate(): string {
  const value = new Date();
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function ExecutiveReportsPage() {
  const catalog = useQuery({ queryKey:["executive-report-catalog"], queryFn:({signal})=>apiGet<Catalog>("/api/v1/executive-reports/catalog",signal) });
  const [busy, setBusy] = useState(""); const [error, setError] = useState("");
  const whiteLabel = currentWhiteLabelPayload();
  const buyerControls = currentBuyerControls();
  const download = async (item: ReportItem) => {
    setBusy(item.key); setError("");
    try {
      const body = item.key === "buyer" ? { buyer_controls: buyerControls } : undefined;
      downloadBlob(await apiDownload(`/api/v1/executive-reports/${item.key}.pdf`, body), `${item.label.replace(/[^A-Za-z0-9]+/g,"_")}.pdf`);
    }
    catch (err) { setError(err instanceof Error ? err.message : "Report generation failed."); }
    finally { setBusy(""); }
  };
  const downloadPack = async (key: PackKey) => {
    setBusy(`pack-${key}`); setError("");
    const names: Record<PackKey,string> = { retail:`retail_ops_executive_pack_${localDate()}.pdf`, production:`production_ops_executive_pack_${localDate()}.pdf`, company:`company_executive_pack_${localDate()}.pdf` };
    const body = key === "production" ? {} : { white_label: whiteLabel, buyer_controls: buyerControls };
    try { downloadBlob(await apiDownload(`/api/v1/executive-reports/packs/${key}.pdf`, body), names[key]); }
    catch (err) { setError(err instanceof Error ? err.message : "Report pack generation failed."); }
    finally { setBusy(""); }
  };
  return <div className="page"><div className="page-heading"><div><div className="eyebrow">DoobieLogic report system</div><h1>Executive Reports</h1><p>The same ReportLab executive report builders used by Streamlit are available here. Buyer reports use the active Buyer Dashboard planning controls and selected data source rather than a hidden default model.</p></div></div>
  {error ? <div className="form-error">{error}</div> : null}{catalog.isLoading ? <div className="state">Loading report catalog…</div> : null}
  <div className="report-card-grid">{catalog.data?.items.map(item=><article className="inventory-panel report-card" key={item.key}><div className="eyebrow">{item.capability} operations</div><h2>{item.label}</h2><p>Generated from the currently selected organization and facility using the retained Streamlit executive PDF engine.</p><button className="primary" disabled={Boolean(busy)} onClick={()=>download(item)}>{busy===item.key?"Generating PDF…":"Generate & Download PDF"}</button></article>)}</div>
  <section className="inventory-panel"><div className="eyebrow">Streamlit report packs</div><h2>Executive report packs</h2><p>Reports are separated into Retail Ops and Production Ops. Packs include currently available reports.</p><div className="report-card-grid"><article className="report-card"><h3>Retail Ops</h3><p>Buyer Operations{whiteLabel ? ", White Label / Repack" : ""}</p><button className="primary" disabled={Boolean(busy)} onClick={()=>downloadPack("retail")}>{busy==="pack-retail"?"Generating PDF…":"Download Retail Ops Pack"}</button></article><article className="report-card"><h3>Production Ops</h3><p>Co-Man Production and Extraction Operations when current facility data is available.</p><button className="primary" disabled={Boolean(busy)} onClick={()=>downloadPack("production")}>{busy==="pack-production"?"Generating PDF…":"Download Production Ops Pack"}</button></article></div><button className="secondary" disabled={Boolean(busy)} onClick={()=>downloadPack("company")}>{busy==="pack-company"?"Generating PDF…":"Download Company Executive Pack"}</button></section>
  </div>;
}
