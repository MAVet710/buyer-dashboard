import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import { InventoryDrivenLabelWorkflow, type LabelRun } from "./InventoryDrivenLabelWorkflow";

type HistoryRow = {
  id: string; product_name: string; sku: string; package_tag: string;
  source_packages: string[]; quantity: number; status: string; created_by: string;
  created_at: string; printed_at: string | null; print_requests: number;
  last_print_request_at: string | null; width_in: number | null; height_in: number | null;
  design_revision: number; sandbox_test_pass: boolean;
};
type HistoryPage = { items: HistoryRow[]; total: number; offset: number; limit: number; has_more: boolean };
type Props = {
  organizationId: string; facilityId: string; canWrite: boolean;
  selectedRunId: string; onSelect: (id: string) => void; onStartNew: () => void;
};
const STATUSES = ["draft", "validated", "tagged", "printed", "applied", "released", "fulfilled", "archived"];
const PAGE_SIZE = 50;

export function LabelRunHistory({ organizationId, facilityId, canWrite, selectedRunId, onSelect, onStartNew }: Props) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [offset, setOffset] = useState(0);
  const [appliedSearch, setAppliedSearch] = useState("");
  const scope = [organizationId, facilityId];
  const datesValid = !from || !to || from <= to;
  const params = new URLSearchParams({ search: appliedSearch, status, offset: String(offset), limit: String(PAGE_SIZE) });
  if (from) params.set("created_from", from);
  if (to) params.set("created_to", to);
  const history = useQuery({
    queryKey: ["label-run-history", ...scope, params.toString()],
    queryFn: ({ signal }) => apiGet<HistoryPage>(`/api/v1/label-printing/history?${params}`, signal),
    enabled: Boolean(organizationId && facilityId && !selectedRunId && datesValid),
  });
  const detail = useQuery({
    queryKey: ["label-run-history-detail", ...scope, selectedRunId],
    queryFn: ({ signal }) => apiGet<LabelRun>(`/api/v1/label-printing/production-runs/${encodeURIComponent(selectedRunId)}`, signal),
    enabled: Boolean(organizationId && facilityId && selectedRunId),
    staleTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  });
  if (!organizationId || !facilityId) return <div className="info-banner">Choose a facility to view saved labels.</div>;
  if (selectedRunId) return <section className="page label-history-detail">
    <div className="heading-actions"><button className="secondary" type="button" onClick={() => onSelect("")}>Back to label history</button></div>
    {detail.isFetching ? <div className="state">Loading the original saved label…</div> : null}
    {detail.isError ? <div className="state error">This saved label could not be opened in the selected facility. {detail.error.message}<button className="secondary" type="button" onClick={() => void detail.refetch()}>Retry</button></div> : null}
    {/* The renderer owns editable local state. Do not initialize it from a stale
        cached response while a reopen request is still fetching. A later fresh
        response must reset that local state, including the print audit trail. */}
    {detail.data && !detail.isError && !detail.isFetching ? <InventoryDrivenLabelWorkflow key={`${organizationId}:${facilityId}:${detail.data.id}:${detail.dataUpdatedAt}`} restoredRun={detail.data} canWrite={canWrite} onStartNew={onStartNew} /> : null}
  </section>;
  return <section className="page label-run-history">
    <div className="page-heading"><div><div className="eyebrow">LABEL STUDIO · SAVED RUNS</div><h2>History &amp; Reprints</h2><p>Find a saved label by finished tag, source package, product, SKU, batch, or date. Reprints use the original saved facts and design, not today's Product Master or COA.</p></div><button className="secondary" type="button" onClick={() => void history.refetch()} disabled={history.isFetching || !datesValid}>Refresh history</button></div>
    <form className="inventory-panel form-grid" onSubmit={event => { event.preventDefault(); setAppliedSearch(search.trim()); setOffset(0); }}>
      <label>Tag, product, SKU, or batch<input aria-label="Search label history" value={search} maxLength={160} onChange={event => setSearch(event.target.value)} placeholder="Scan or enter a package tag…" /></label>
      <label>Status<select value={status} onChange={event => { setStatus(event.target.value); setOffset(0); }}><option value="">All statuses, including archived</option>{STATUSES.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <label>Created from (UTC)<input type="date" value={from} onChange={event => { setFrom(event.target.value); setOffset(0); }} /></label>
      <label>Created through (UTC)<input type="date" value={to} onChange={event => { setTo(event.target.value); setOffset(0); }} /></label>
      <button className="primary" type="submit" disabled={!datesValid}>Search saved labels</button>
    </form>
    {!datesValid ? <div className="form-error">The start date must not be after the end date.</div> : null}
    {history.isLoading ? <div className="state">Loading saved label history…</div> : null}
    {history.isError ? <div className="state error">Label history is unavailable. {history.error.message}</div> : null}
    {datesValid && history.data && !history.isError ? <>
      <p className="source-caption">{history.data.total} saved run(s). Print-request counts record browser print requests, not confirmed physical printer output.</p>
      <div className="inventory-panel table-wrap"><table><thead><tr><th>Product / SKU</th><th>Finished tag / source</th><th>Original labels</th><th>Stock</th><th>Status</th><th>Created</th><th>Print requests</th><th>Open</th></tr></thead><tbody>{history.data.items.map(row => <tr key={row.id}>
        <td><strong>{row.product_name}</strong><br /><small>{row.sku}</small>{row.sandbox_test_pass ? <div className="badge">Sandbox test data</div> : null}</td>
        <td>{row.package_tag || "Not assigned"}<br /><small>{row.source_packages.filter(Boolean).join(" · ")}</small></td>
        <td>{row.quantity}</td><td>{row.width_in && row.height_in ? `${row.width_in} × ${row.height_in} in` : "Legacy layout not recorded"}</td>
        <td>{row.status}</td><td>{new Date(row.created_at).toLocaleString()}<br /><small>{row.created_by}</small></td>
        <td>{row.print_requests}{row.last_print_request_at ? <><br /><small>{new Date(row.last_print_request_at).toLocaleString()}</small></> : null}</td>
        <td><button className="secondary" type="button" aria-label={`Open saved label ${row.package_tag || row.product_name}`} onClick={() => onSelect(row.id)}>Preview / reopen</button></td>
      </tr>)}</tbody></table>{!history.data.items.length ? <div className="empty">No saved label runs match these filters. Labels printed through a separate internal-inventory or legacy print-job path do not become production label runs automatically.</div> : null}</div>
      <div className="heading-actions"><button className="secondary" type="button" disabled={offset === 0 || history.isFetching} onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}>Previous</button><span>Page {Math.floor(offset / PAGE_SIZE) + 1}</span><button className="secondary" type="button" disabled={!history.data.has_more || history.isFetching} onClick={() => setOffset(value => value + PAGE_SIZE)}>Next</button></div>
    </> : null}
  </section>;
}
