import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { apiGet } from "../lib/api";
import type { InventoryPackage } from "../types/inventory";

type Context = { organization?: { id: string }; facility_id?: string; user?: { id: string }; capabilities?: { retail: boolean } };
type Stock = {
  evidence: { state: string; row_count: number; observed_at: string; provider_freshness: string };
  items: InventoryPackage[]; total: number; offset: number; limit: number; has_more: boolean;
  facets: { statuses: string[]; units: string[] };
  summary: { package_count: number; product_count: number; held_packages: number; totals_by_unit: Array<{ unit: string; on_hand: number; available: number; reserved: number }> };
  sales_sources: { state: string; message: string; items: Array<{ dataset: string; filename: string; rows: number; published_at: string }> };
};

export function BuyerCurrentInventory() {
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<Context>("/api/v1/account/context", signal) });
  if (context.isError) return <div className="state error" role="alert">Facility context is unavailable. No stock conclusion can be drawn.</div>;
  if (!context.data) return <div className="state">Loading facility context…</div>;
  const { organization, facility_id: facilityId, capabilities, user } = context.data;
  if (!organization?.id || !facilityId || !capabilities?.retail) return <div className="info-banner">Choose an authorized retail facility to view current stock.</div>;
  return <CurrentStock key={`${organization.id}:${facilityId}:${user?.id ?? ""}`} organizationId={organization.id} facilityId={facilityId} />;
}

function CurrentStock({ organizationId, facilityId }: { organizationId: string; facilityId: string }) {
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [status, setStatus] = useState("");
  const [unit, setUnit] = useState("");
  const [offset, setOffset] = useState(0);
  const params = new URLSearchParams({ search: appliedSearch, status, unit, offset: String(offset), limit: "50" });
  const stock = useQuery({
    queryKey: ["buyer-current-inventory", organizationId, facilityId, params.toString()],
    queryFn: async ({ signal }) => {
      const result = await apiGet<Stock>(`/api/v1/buyer-parity/current-inventory?${params}`, signal);
      if (!result?.evidence?.observed_at || !Array.isArray(result.items) || !Array.isArray(result.summary?.totals_by_unit) || !Array.isArray(result.sales_sources?.items)) throw new Error("Current inventory response is incomplete.");
      return result;
    },
    staleTime: 0, refetchOnMount: "always", retry: false,
  });
  // A failed refresh must not leave previous numbers presented as current facts.
  const data = stock.isError ? undefined : stock.data;
  return <section className="inventory-panel buyer-current-inventory" aria-label="Current buyer inventory">
    <div className="page-heading"><div><h2>Current stock &amp; availability</h2><p>The same package inventory used by the Inventory workspace and Inventory AI. No inventory or sales upload is required.</p></div><div className="heading-actions"><button className="secondary" type="button" disabled={stock.isFetching} onClick={() => void stock.refetch()}>Refresh current stock</button><Link to="/inventory">Open Inventory</Link></div></div>
    <form className="form-grid" onSubmit={event => { event.preventDefault(); setAppliedSearch(search.trim()); setOffset(0); }}>
      <label>Package, product, SKU, or location<input aria-label="Search current stock" maxLength={160} value={search} onChange={event => setSearch(event.target.value)} /></label>
      <label>Stock status<select aria-label="Current stock status" value={status} onChange={event => { setStatus(event.target.value); setOffset(0); }}><option value="">All statuses</option>{(data?.facets.statuses ?? (status ? [status] : [])).map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <label>Inventory unit<select aria-label="Current stock unit" value={unit} onChange={event => { setUnit(event.target.value); setOffset(0); }}><option value="">All units, kept separate</option>{(data?.facets.units ?? (unit ? [unit] : [])).map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <button className="primary" type="submit">Search current stock</button>
    </form>
    {stock.isFetching ? <div className="state" role="status">Reading current inventory…</div> : null}
    {stock.isError ? <div className="state error" role="alert">Current inventory is unavailable. This does not mean zero stock. No uploaded snapshot has been substituted. Use Refresh current stock to retry.</div> : null}
    {data ? <>
      <p className="source-caption">Database observation: {new Date(data.evidence.observed_at).toLocaleString()}. This is not a live Metrc sync check. Totals cover all matching packages, not just this page.</p>
      <div className="metrics"><article className="metric"><span>Matching packages</span><strong>{data.summary.package_count}</strong></article><article className="metric"><span>Distinct products</span><strong>{data.summary.product_count}</strong></article><article className="metric"><span>Held packages</span><strong>{data.summary.held_packages}</strong></article></div>
      {data.summary.totals_by_unit.length ? <div className="table-wrap"><table aria-label="Current stock totals by unit"><thead><tr><th>Unit</th><th>On hand</th><th>Available</th><th>Reserved</th></tr></thead><tbody>{data.summary.totals_by_unit.map(row => <tr key={row.unit}><th>{row.unit || "Unspecified unit"}</th><td>{quantity(row.on_hand)}</td><td>{quantity(row.available)}</td><td>{quantity(row.reserved)}</td></tr>)}</tbody></table></div> : null}
      <p className="section-note">On hand, available, and reserved are different measures. Grams and retail units are never added together. Sales velocity and reorder quantities remain in the separate uploaded forecast analysis until their product and unit mappings are verified.</p>
      {data.items.length ? <div className="table-wrap"><table aria-label="Current buyer packages"><thead><tr><th>Product / SKU</th><th>Package / lot</th><th>Unit</th><th>On hand</th><th>Available</th><th>Reserved</th><th>Location</th><th>Status</th></tr></thead><tbody>{data.items.map(row => <tr key={row.id}><td><Link to={`/inventory/products/${encodeURIComponent(row.product_id)}`}>{row.product_name}</Link><br /><small>{row.sku}</small></td><td><Link to={`/inventory/packages/${encodeURIComponent(row.id)}`}>{row.package_id || row.lot_code}</Link></td><td>{row.unit}</td><td>{quantity(row.on_hand)}</td><td>{quantity(row.available)}</td><td>{quantity(row.reserved)}</td><td>{row.location}</td><td>{row.status}<br /><small>{row.attention}</small></td></tr>)}</tbody></table></div> : <div className="empty">{data.evidence.state === "empty" ? "The authorized inventory read succeeded: this facility has no retail package records." : "No current packages match these filters."}</div>}
      <div className="heading-actions"><button className="secondary" type="button" disabled={!offset || stock.isFetching} onClick={() => setOffset(value => Math.max(0, value - 50))}>Previous stock page</button><span>{data.total} matching packages · page {Math.floor(offset / 50) + 1}</span><button className="secondary" type="button" disabled={!data.has_more || stock.isFetching} onClick={() => setOffset(value => value + 50)}>Next stock page</button></div>
      <div className="info-banner"><strong>Separate sales evidence</strong><p>{data.sales_sources.state === "missing" ? "No active sales upload is published. Current stock is still available; zero sales has not been assumed." : data.sales_sources.message}</p>{data.sales_sources.items.map(source => <p key={source.dataset}>{source.filename} · {source.rows} rows · published {new Date(source.published_at).toLocaleString()}</p>)}</div>
    </> : null}
  </section>;
}

function quantity(value: number) { return value.toLocaleString(undefined, { maximumFractionDigits: 4 }); }


export function BuyerUploadedSourceNotice() {
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<Context>("/api/v1/account/context", signal) });
  const evidence = useQuery({
    queryKey: ["buyer-uploaded-source-evidence", context.data?.organization?.id, context.data?.facility_id],
    queryFn: ({ signal }) => apiGet<Stock["sales_sources"]>("/api/v1/buyer-parity/uploaded-source-evidence", signal),
    enabled: Boolean(context.data?.organization?.id && context.data?.facility_id && !context.isError),
    staleTime: 0, retry: false,
  });
  return <div className="info-banner"><strong>Historical uploaded-snapshot analysis</strong><p>These forecasts, inventory checks, and buyer briefs use published inventory and sales files, not the current inventory ledger. Verify current availability and product/unit mappings before placing an order.</p>
    {Array.isArray(evidence.data?.items) && !evidence.isError ? (evidence.data?.items ?? []).map(source => <p key={source.dataset}>{source.dataset}: {source.filename} · {source.rows} rows · published {new Date(source.published_at).toLocaleString()}</p>) : null}
    <p>Publication dates are not sales coverage dates.{evidence.isError || evidence.data?.state === "unavailable" ? " Source publication metadata is unavailable." : ""}</p>
  </div>;
}
