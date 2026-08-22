import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { apiDownload, apiGet, apiPost, apiPostForm, downloadBlob } from "../lib/api";

type CatalogRow = { id: string; canonical_name: string; sku: string; category: string; brand: string };
type Status = { catalog_count: number; mapping_count: number; catalog: CatalogRow[] };
type Suggestion = { source_name: string; correct_name: string; confidence: number; status: string; match_basis: string };
type ManifestResponse = { filename: string; row_count: number; rows: Suggestion[]; unique_suggestions: Suggestion[] };

export function NomenclatureMapperPage() {
  const client = useQueryClient();
  const status = useQuery({ queryKey: ["nomenclature-status"], queryFn: ({ signal }) => apiGet<Status>("/api/v1/parity-tools/nomenclature", signal) });
  const [catalogBusy, setCatalogBusy] = useState(false);
  const [manifestBusy, setManifestBusy] = useState(false);
  const [manifest, setManifest] = useState<ManifestResponse | null>(null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const catalogNames = useMemo(() => status.data?.catalog.map(row => row.canonical_name) ?? [], [status.data]);
  const unresolved = manifest?.unique_suggestions.filter(row => !(choices[row.source_name] ?? row.correct_name)) ?? [];

  const uploadCatalog = async (file?: File) => {
    if (!file) return;
    setCatalogBusy(true); setError(""); setMessage("");
    try {
      const form = new FormData(); form.append("file", file);
      const result = await apiPostForm<{ saved: number }>("/api/v1/parity-tools/nomenclature/catalog", form);
      setMessage(`Saved ${result.saved.toLocaleString()} approved Dutchie catalog names for this organization.`);
      await client.invalidateQueries({ queryKey: ["nomenclature-status"] });
      setManifest(null); setChoices({});
    } catch (err) { setError(err instanceof Error ? err.message : "Catalog upload failed."); }
    finally { setCatalogBusy(false); }
  };

  const uploadManifest = async (file?: File) => {
    if (!file) return;
    setManifestBusy(true); setError(""); setMessage("");
    try {
      const form = new FormData(); form.append("file", file);
      const result = await apiPostForm<ManifestResponse>("/api/v1/parity-tools/nomenclature/manifest", form);
      const initial: Record<string, string> = {};
      result.unique_suggestions.forEach(row => { initial[row.source_name] = row.correct_name; });
      setManifest(result); setChoices(initial);
    } catch (err) { setError(err instanceof Error ? err.message : "Manifest mapping failed."); }
    finally { setManifestBusy(false); }
  };

  const confirm = async () => {
    if (!manifest) return;
    const rows = manifest.unique_suggestions.map(row => ({ source_name: row.source_name, correct_name: choices[row.source_name] ?? row.correct_name }));
    if (rows.some(row => !row.correct_name)) return setError("Choose an approved Dutchie name for every unique METRC item before confirming.");
    setError("");
    try {
      const result = await apiPost<{ saved: number }>("/api/v1/parity-tools/nomenclature/confirm", { rows });
      setMessage(`Confirmed and remembered ${result.saved.toLocaleString()} mappings for this organization.`);
      await client.invalidateQueries({ queryKey: ["nomenclature-status"] });
    } catch (err) { setError(err instanceof Error ? err.message : "Could not confirm mappings."); }
  };

  const exportNames = async () => {
    if (!manifest) return;
    const correctNames = manifest.rows.map(row => choices[row.source_name] ?? row.correct_name);
    if (correctNames.some(value => !value)) return setError("Confirm a Dutchie name for every manifest row before exporting.");
    try {
      const blob = await apiDownload("/api/v1/parity-tools/nomenclature/export", { correct_names: correctNames });
      downloadBlob(blob, "Correct_METRC_Item_Names.xlsx");
    } catch (err) { setError(err instanceof Error ? err.message : "Export failed."); }
  };

  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">Buyer Operations</div><h1>Dutchie-to-METRC Nomenclature</h1><p>Organization-isolated catalog truth, deterministic suggestions, human review, learned mappings, and the original one-column Excel export.</p></div></div>
    <div className="metric-grid four"><div className="metric"><span>Catalog Items</span><strong>{status.data?.catalog_count.toLocaleString() ?? "—"}</strong><small>Approved Dutchie names</small></div><div className="metric"><span>Learned Mappings</span><strong>{status.data?.mapping_count.toLocaleString() ?? "—"}</strong><small>Remembered for this organization</small></div><div className="metric"><span>Export Shape</span><strong>1 column</strong><small>Correct Item Name</small></div><div className="metric"><span>Tenant Scope</span><strong>Organization</strong><small>No cross-company mappings</small></div></div>
    {error ? <div className="form-error">{error}</div> : null}{message ? <div className="success-banner">{message}</div> : null}
    <div className="two-column-grid">
      <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Step 1</div><h3>Dutchie Catalog</h3></div></div><p className="muted">Upload a Dutchie CSV/XLSX containing Product Name or Item Name. Saving replaces the active catalog while preserving confirmed METRC mappings.</p><label className="file-drop">{catalogBusy ? "Saving catalog…" : "Choose Dutchie catalog"}<input type="file" accept=".csv,.xlsx,.xls" disabled={catalogBusy} onChange={event => uploadCatalog(event.target.files?.[0])} /></label>{status.data?.catalog.length ? <div className="table-wrap compact-table"><table><thead><tr><th>Correct Item Name</th><th>SKU</th><th>Category</th><th>Brand</th></tr></thead><tbody>{status.data.catalog.slice(0, 50).map(row => <tr key={row.id}><td>{row.canonical_name}</td><td>{row.sku}</td><td>{row.category}</td><td>{row.brand}</td></tr>)}</tbody></table></div> : <div className="empty-state">Upload the first Dutchie naming catalog to begin.</div>}</section>
      <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Step 2</div><h3>Apply Names to METRC</h3></div></div><p className="muted">Upload the METRC manifest. Suggestions can only resolve to names in this organization's active Dutchie catalog.</p><label className="file-drop">{manifestBusy ? "Mapping manifest…" : "Choose METRC manifest"}<input type="file" accept=".csv,.xlsx,.xls" disabled={manifestBusy || !status.data?.catalog_count} onChange={event => uploadManifest(event.target.files?.[0])} /></label>{manifest ? <p className="muted">{manifest.row_count.toLocaleString()} manifest rows · {manifest.unique_suggestions.length.toLocaleString()} unique item names</p> : null}</section>
    </div>
    {manifest ? <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Human review</div><h3>Confirm suggested names</h3></div><span className="access-badge">{unresolved.length} unresolved</span></div><div className="table-wrap"><table><thead><tr><th>Original METRC Item</th><th>Correct Dutchie Item Name</th><th>Confidence</th><th>Status</th></tr></thead><tbody>{manifest.unique_suggestions.map(row => <tr key={row.source_name}><td>{row.source_name}</td><td><select value={choices[row.source_name] ?? ""} onChange={event => setChoices(current => ({ ...current, [row.source_name]: event.target.value }))}><option value="">Select approved name…</option>{catalogNames.map(name => <option value={name} key={name}>{name}</option>)}</select></td><td>{row.confidence.toFixed(0)}%</td><td><span className={`status-pill ${row.status.toLocaleLowerCase()}`}>{row.status}</span></td></tr>)}</tbody></table></div><div className="form-actions"><button className="secondary" onClick={confirm} disabled={unresolved.length > 0}>Confirm & remember mappings</button><button className="primary" onClick={exportNames} disabled={unresolved.length > 0}>Download Excel names</button></div></section> : null}
  </div>;
}
