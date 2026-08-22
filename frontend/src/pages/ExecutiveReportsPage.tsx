import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiDownload, apiGet, downloadBlob } from "../lib/api";

type ReportItem = { key: string; label: string; capability: string };
type Catalog = { items: ReportItem[] };

export function ExecutiveReportsPage() {
  const catalog = useQuery({ queryKey:["executive-report-catalog"], queryFn:({signal})=>apiGet<Catalog>("/api/v1/executive-reports/catalog",signal) });
  const [busy, setBusy] = useState(""); const [error, setError] = useState("");
  const download = async (item: ReportItem) => {
    setBusy(item.key); setError("");
    try { downloadBlob(await apiDownload(`/api/v1/executive-reports/${item.key}.pdf`), `${item.label.replace(/[^A-Za-z0-9]+/g,"_")}.pdf`); }
    catch (err) { setError(err instanceof Error ? err.message : "Report generation failed."); }
    finally { setBusy(""); }
  };
  return <div className="page"><div className="page-heading"><div><div className="eyebrow">Buyer Dash report system</div><h1>Executive Reports</h1><p>The same ReportLab executive report builders used by Streamlit are available here. React only supplies the current organization/facility data and downloads the original PDF output.</p></div></div>
  {error ? <div className="form-error">{error}</div> : null}{catalog.isLoading ? <div className="state">Loading report catalog…</div> : null}
  <div className="report-card-grid">{catalog.data?.items.map(item=><article className="inventory-panel report-card" key={item.key}><div className="eyebrow">{item.capability} operations</div><h2>{item.label}</h2><p>Generated from the currently selected organization and facility using the retained Buyer Dash executive PDF engine.</p><button className="primary" disabled={Boolean(busy)} onClick={()=>download(item)}>{busy===item.key?"Generating PDF…":"Generate & Download PDF"}</button></article>)}</div></div>;
}
