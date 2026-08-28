import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../lib/api";

type Finding = {
  severity: "high" | "medium" | "info";
  domain: string;
  code: string;
  title: string;
  message: string;
  entity_type: string;
  entity_id: string;
  source: string;
  recommended_review: string;
  jurisdiction_code: string;
  license_number: string;
  environment: string;
};
type RegulatoryReport = {
  configured: boolean;
  ready: boolean;
  read_only: boolean;
  generated_at: string;
  message: string;
  scope: { capabilities: string[]; jurisdiction_code: string; license_number: string; environment: string };
  summary: { status: string; attention_score: number; finding_count: number; high_count: number; medium_count: number; info_count: number; by_domain: Record<string, number> };
  findings: Finding[];
  warnings: string[];
};

export function RegulatoryIntelligencePanel() {
  const [active, setActive] = useState(false);
  const report = useQuery({
    queryKey: ["compliance-regulatory-intelligence"],
    queryFn: ({ signal }) => apiGet<RegulatoryReport>("/api/v1/compliance/regulatory-intelligence", signal),
    enabled: active,
    staleTime: 30_000,
  });
  const data = report.data;
  const top = data?.findings.slice(0, 50) ?? [];

  return <section className="inventory-panel regulatory-intelligence-panel">
    <div className="section-heading">
      <div>
        <div className="eyebrow">REGULATORY INTELLIGENCE</div>
        <h2>Metrc &amp; traceability attention</h2>
        <p className="source-caption">Deterministic, read-only checks against the exact active facility mapping. Signals identify what needs review; they do not replace authoritative regulations or SOPs.</p>
      </div>
      <div className="audit-actions">
        {!active ? <button className="primary" type="button" onClick={() => setActive(true)}>Check regulatory state</button> : null}
        {active ? <button className="secondary" type="button" disabled={report.isFetching} onClick={() => void report.refetch()}>{report.isFetching ? "Checking…" : "Run again"}</button> : null}
      </div>
    </div>

    {!active ? <div className="info-banner">No live Metrc request is made until you run this check.</div> : null}
    {report.isLoading ? <div className="state">Checking Metrc and local reconciliation state…</div> : null}
    {report.isError ? <div className="warning-banner">Regulatory intelligence could not load: {report.error.message}</div> : null}

    {data ? <>
      <section className="metrics four">
        <Metric label="High" value={data.summary.high_count}/>
        <Metric label="Medium" value={data.summary.medium_count}/>
        <Metric label="Info" value={data.summary.info_count}/>
        <Metric label="Attention score" value={`${data.summary.attention_score}/100`}/>
      </section>
      <p className="source-caption">{data.scope.jurisdiction_code || "No jurisdiction"} · {data.scope.license_number || "No mapped license"} · {data.scope.environment || "—"} · {data.scope.capabilities.join(" / ") || "no facility capabilities"} · generated {new Date(data.generated_at).toLocaleString()}</p>
      {!data.ready ? <div className="warning-banner">{data.message}</div> : null}
      {data.ready && data.summary.finding_count === 0 ? <div className="success-banner">No deterministic regulatory exceptions were found in the checked data.</div> : null}
      {data.warnings.length ? <div className="warning-banner"><strong>Provider/read warnings</strong><br/>{data.warnings.slice(0, 5).join(" · ")}</div> : null}
      {top.length ? <div className="table-wrap"><table><thead><tr><th>Severity</th><th>Domain</th><th>Finding</th><th>Entity</th><th>Review</th><th>Source</th></tr></thead><tbody>{top.map((row, index) => <tr key={`${row.domain}-${row.code}-${row.entity_id}-${index}`}><td><span className="badge">{row.severity}</span></td><td>{title(row.domain)}</td><td><strong>{row.title}</strong><br/><small>{row.message}</small></td><td>{row.entity_id || "—"}<br/><small>{row.entity_type || ""}</small></td><td>{row.recommended_review}</td><td>{row.source}</td></tr>)}</tbody></table></div> : null}
      {data.findings.length > top.length ? <p className="source-caption">Showing the first {top.length} of {data.findings.length} findings, prioritized by severity.</p> : null}
    </> : null}
  </section>;
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <article className="metric"><span>{label}</span><strong>{value}</strong></article>;
}
function title(value: string) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase()); }
