import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDownload, apiGet, apiPost, apiPostForm, downloadBlob } from "../lib/api";

type CatalogRow = { id: string; canonical_name: string; sku: string; category: string; brand: string };
type CatalogPreviewRow = Omit<CatalogRow, "id">;
type CatalogPreview = { detected: number; preview: CatalogPreviewRow[] };
type Status = { catalog_count: number; mapping_count: number; catalog: CatalogRow[] };
type Suggestion = {
  source_name: string;
  correct_name: string;
  confidence: number;
  status: string;
  match_basis: string;
  proposed_new_name?: string;
};
type ManifestResponse = { filename: string; row_count: number; rows: Suggestion[]; unique_suggestions: Suggestion[] };
type NewDraft = { canonical_name: string; sku: string; category: string; brand: string };
type Tab = "catalog" | "map" | "library";

export function NomenclatureMapperPage() {
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["nomenclature-status"],
    queryFn: ({ signal }) => apiGet<Status>("/api/v1/parity-tools/nomenclature", signal),
  });
  const [tab, setTab] = useState<Tab>("catalog");
  const [catalogFile, setCatalogFile] = useState<File | null>(null);
  const [catalogPreview, setCatalogPreview] = useState<CatalogPreview | null>(null);
  const [catalogBusy, setCatalogBusy] = useState(false);
  const [catalogSaveBusy, setCatalogSaveBusy] = useState(false);
  const [manifestFile, setManifestFile] = useState<File | null>(null);
  const [manifestBusy, setManifestBusy] = useState(false);
  const [manifest, setManifest] = useState<ManifestResponse | null>(null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [createNew, setCreateNew] = useState<Record<string, boolean>>({});
  const [newDrafts, setNewDrafts] = useState<Record<string, NewDraft>>({});
  const [approveNew, setApproveNew] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [confirmedSignature, setConfirmedSignature] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const catalogNames = useMemo(() => status.data?.catalog.map(row => row.canonical_name) ?? [], [status.data]);
  const dominantBrand = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of status.data?.catalog ?? []) {
      const brand = row.brand.trim();
      if (brand) counts.set(brand, (counts.get(brand) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "";
  }, [status.data]);

  const currentSignature = () => JSON.stringify(
    (manifest?.unique_suggestions ?? []).map(row => [row.source_name, choices[row.source_name] ?? row.correct_name]),
  );

  const resetReviewConfirmation = () => {
    setReviewed(false);
    setConfirmedSignature("");
  };

  const previewCatalog = async (file?: File) => {
    if (!file) return;
    setCatalogFile(file);
    setCatalogPreview(null);
    setCatalogBusy(true);
    setError("");
    setMessage("");
    try {
      const form = new FormData();
      form.append("file", file);
      setCatalogPreview(await apiPostForm<CatalogPreview>("/api/v1/parity-tools/nomenclature/catalog/preview", form));
    } catch (err) {
      setError(`The Dutchie catalog could not be read: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setCatalogBusy(false);
    }
  };

  const saveCatalog = async () => {
    if (!catalogFile) return;
    setCatalogSaveBusy(true);
    setError("");
    setMessage("");
    try {
      const form = new FormData();
      form.append("file", catalogFile);
      const result = await apiPostForm<{ saved: number }>("/api/v1/parity-tools/nomenclature/catalog", form);
      setMessage(`Saved ${result.saved.toLocaleString()} catalog names for this organization.`);
      await client.invalidateQueries({ queryKey: ["nomenclature-status"] });
      setManifest(null);
      setManifestFile(null);
      setChoices({});
      setCreateNew({});
      setNewDrafts({});
      resetReviewConfirmation();
    } catch (err) {
      setError(`The Dutchie catalog could not be read: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setCatalogSaveBusy(false);
    }
  };

  const processManifest = async (file: File) => {
    setManifestBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await apiPostForm<ManifestResponse>("/api/v1/parity-tools/nomenclature/manifest", form);
      const initialChoices: Record<string, string> = {};
      const drafts: Record<string, NewDraft> = {};
      result.unique_suggestions.forEach(row => {
        initialChoices[row.source_name] = row.correct_name;
        drafts[row.source_name] = {
          canonical_name: row.proposed_new_name || row.source_name,
          sku: "",
          category: "",
          brand: dominantBrand,
        };
      });
      setManifest(result);
      setChoices(initialChoices);
      setCreateNew({});
      setNewDrafts(drafts);
      setApproveNew(false);
      resetReviewConfirmation();
    } catch (err) {
      setError(`The METRC manifest could not be processed: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setManifestBusy(false);
    }
  };

  const uploadManifest = async (file?: File) => {
    if (!file) return;
    setManifestFile(file);
    setMessage("");
    await processManifest(file);
  };

  const setChoice = (sourceName: string, value: string) => {
    setChoices(current => ({ ...current, [sourceName]: value }));
    resetReviewConfirmation();
  };

  const setCreateNewFor = (row: Suggestion, value: boolean) => {
    setCreateNew(current => ({ ...current, [row.source_name]: value }));
    if (value && !newDrafts[row.source_name]) {
      setNewDrafts(current => ({
        ...current,
        [row.source_name]: {
          canonical_name: row.proposed_new_name || row.source_name,
          sku: "",
          category: "",
          brand: dominantBrand,
        },
      }));
    }
    setApproveNew(false);
    resetReviewConfirmation();
  };

  const updateDraft = (sourceName: string, field: keyof NewDraft, value: string) => {
    setNewDrafts(current => ({
      ...current,
      [sourceName]: { ...(current[sourceName] ?? { canonical_name: "", sku: "", category: "", brand: "" }), [field]: value },
    }));
  };

  const addNewProducts = async () => {
    const rows = (manifest?.unique_suggestions ?? [])
      .filter(row => createNew[row.source_name])
      .map(row => newDrafts[row.source_name]);
    if (!rows.length || rows.some(row => !row?.canonical_name.trim())) {
      setError("Give every new product an approved Dutchie Product Name.");
      return;
    }
    if (!approveNew) return;
    setError("");
    try {
      const result = await apiPost<{ saved: number }>("/api/v1/parity-tools/nomenclature/catalog/items", { rows });
      setMessage(`Added ${result.saved.toLocaleString()} new approved product names. Re-matching the manifest now.`);
      await client.invalidateQueries({ queryKey: ["nomenclature-status"] });
      if (manifestFile) await processManifest(manifestFile);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add new products.");
    }
  };

  const confirm = async () => {
    if (!manifest) return;
    const rows = manifest.unique_suggestions.map(row => ({ source_name: row.source_name, correct_name: choices[row.source_name] ?? row.correct_name }));
    if (rows.some(row => !row.correct_name.trim())) {
      setError("Choose a correct catalog name for every item before confirming.");
      return;
    }
    setError("");
    try {
      const result = await apiPost<{ saved: number }>("/api/v1/parity-tools/nomenclature/confirm", { rows });
      setConfirmedSignature(currentSignature());
      setMessage(`Confirmed ${result.saved.toLocaleString()} mappings for this organization.`);
      await client.invalidateQueries({ queryKey: ["nomenclature-status"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm mappings.");
    }
  };

  const exportNames = async () => {
    if (!manifest || confirmedSignature !== currentSignature()) return;
    const correctNames = manifest.rows.map(row => choices[row.source_name] ?? row.correct_name);
    try {
      const blob = await apiDownload("/api/v1/parity-tools/nomenclature/export", { correct_names: correctNames });
      downloadBlob(blob, "Correct_METRC_Item_Names.xlsx");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed.");
    }
  };

  const readyCount = manifest?.unique_suggestions.filter(row => ["Ready", "Confirmed"].includes(row.status)).length ?? 0;
  const reviewCount = manifest?.unique_suggestions.filter(row => row.status === "Review").length ?? 0;
  const unmatchedCount = manifest?.unique_suggestions.filter(row => row.status === "Unmatched").length ?? 0;
  const hasNewItems = manifest?.unique_suggestions.some(row => createNew[row.source_name]) ?? false;
  const missingCount = manifest?.unique_suggestions.filter(row => !createNew[row.source_name] && !(choices[row.source_name] ?? row.correct_name).trim()).length ?? 0;
  const newItemRows = manifest?.unique_suggestions.filter(row => createNew[row.source_name]) ?? [];

  return <div className="page exact-nomenclature-mapper">
    <div className="page-heading"><div><div className="eyebrow">BUYER OPERATIONS</div><h1>Dutchie-to-METRC Nomenclature</h1><p>Apply each dispensary&apos;s approved Dutchie product names to the item rows in a METRC manifest.</p></div></div>
    <p className="muted">Dutchie catalog = naming source of truth. METRC manifest = incoming items to correct. The final file contains the corresponding Dutchie Product Name for every manifest row. Catalogs and confirmed mappings remain isolated by organization.</p>

    <div className="metric-grid three">
      <div className="metric"><span>Catalog Items</span><strong>{status.data?.catalog_count.toLocaleString() ?? "—"}</strong><small>Active Dutchie source-of-truth names</small></div>
      <div className="metric"><span>Learned Mappings</span><strong>{status.data?.mapping_count.toLocaleString() ?? "—"}</strong><small>Confirmed METRC names for this organization</small></div>
      <div className="metric"><span>Export Shape</span><strong>1 column</strong><small>Correct Item Name only</small></div>
    </div>

    {error ? <div className="form-error">{error}</div> : null}
    {message ? <div className="success-banner">{message}</div> : null}

    <div className="tab-strip" role="tablist" aria-label="Nomenclature mapper sections">
      <button type="button" className={tab === "catalog" ? "active" : ""} onClick={() => setTab("catalog")}>1 - Dutchie Catalog</button>
      <button type="button" className={tab === "map" ? "active" : ""} onClick={() => setTab("map")}>2 - Apply Names to METRC</button>
      <button type="button" className={tab === "library" ? "active" : ""} onClick={() => setTab("library")}>Mapping Library</button>
    </div>

    {tab === "catalog" ? <section className="inventory-panel">
      <h4>Upload the store&apos;s approved catalog</h4>
      <p>Upload a Dutchie CSV or Excel catalog containing a Product Name or Item Name column. Saving it replaces the organization&apos;s active catalog while preserving confirmed METRC mappings.</p>
      <label className="file-drop">{catalogBusy ? "Reading Dutchie catalog…" : "Dutchie catalog"}<input type="file" accept=".csv,.xlsx" disabled={catalogBusy || catalogSaveBusy} onChange={event => previewCatalog(event.target.files?.[0])} /></label>
      {catalogPreview ? <>
        <div className="success-banner">Detected {catalogPreview.detected.toLocaleString()} unique approved item names.</div>
        <CatalogTable rows={catalogPreview.preview} />
        <div className="form-actions"><button className="primary" type="button" disabled={catalogSaveBusy} onClick={saveCatalog}>{catalogSaveBusy ? "Saving…" : "Save as this organization's Dutchie catalog"}</button></div>
      </> : status.data?.catalog_count ? <div className="success-banner">An active catalog with {status.data.catalog_count.toLocaleString()} names is ready.</div> : <div className="info-banner">Upload the first Dutchie catalog to begin.</div>}
    </section> : null}

    {tab === "map" ? <section className="inventory-panel">
      {!status.data?.catalog_count ? <div className="info-banner">Save a Dutchie catalog in Step 1 before uploading a METRC manifest.</div> : <>
        <h4>Upload the METRC manifest to rename</h4>
        <p>The mapper reads each METRC Item value, finds the corresponding approved Dutchie Product Name, and keeps the original manifest row order.</p>
        <label className="file-drop">{manifestBusy ? "Processing METRC manifest…" : "METRC manifest"}<input type="file" accept=".csv,.xlsx" disabled={manifestBusy} onChange={event => uploadManifest(event.target.files?.[0])} /></label>
      </>}

      {manifest ? <>
        <div className="metric-grid four">
          <div className="metric"><span>Unique METRC Names</span><strong>{manifest.unique_suggestions.length.toLocaleString()}</strong><small>Detected in this manifest</small></div>
          <div className="metric"><span>Ready</span><strong>{readyCount.toLocaleString()}</strong><small>High-confidence or learned</small></div>
          <div className="metric"><span>Needs Review</span><strong>{reviewCount.toLocaleString()}</strong><small>Select the correct catalog name</small></div>
          <div className="metric"><span>Unmatched</span><strong>{unmatchedCount.toLocaleString()}</strong><small>No safe automatic match</small></div>
        </div>

        <h4>Review suggested names</h4>
        <p className="muted">Every Correct Item Name must come from the current Dutchie catalog. If the product is genuinely new, check Create New Product and approve a new name in the store&apos;s naming style.</p>
        <div className="table-wrap"><table><thead><tr><th>Original METRC Item</th><th>Correct Item Name</th><th>Create New Product</th><th>Confidence</th><th>Status</th></tr></thead><tbody>
          {manifest.unique_suggestions.map(row => <tr key={row.source_name}>
            <td>{row.source_name}</td>
            <td><select disabled={Boolean(createNew[row.source_name])} value={choices[row.source_name] ?? ""} onChange={event => setChoice(row.source_name, event.target.value)}><option value="">Select approved name…</option>{catalogNames.map(name => <option value={name} key={name}>{name}</option>)}</select></td>
            <td><input type="checkbox" checked={Boolean(createNew[row.source_name])} aria-label={`Create New Product for ${row.source_name}`} onChange={event => setCreateNewFor(row, event.target.checked)} /></td>
            <td>{row.confidence.toFixed(0)}%</td><td>{row.status}</td>
          </tr>)}
        </tbody></table></div>

        {hasNewItems ? <>
          <h4>Create genuinely new Dutchie products</h4>
          <p className="muted">These are editable drafts based on this organization&apos;s catalog style. Approve the final spelling, size, pack count, category, and brand before saving.</p>
          <div className="table-wrap"><table><thead><tr><th>Original METRC Item</th><th>New Dutchie Product Name</th><th>SKU</th><th>Category</th><th>Brand</th></tr></thead><tbody>
            {newItemRows.map(row => {
              const draft = newDrafts[row.source_name] ?? { canonical_name: row.proposed_new_name || row.source_name, sku: "", category: "", brand: dominantBrand };
              return <tr key={row.source_name}><td>{row.source_name}</td><td><input value={draft.canonical_name} onChange={event => updateDraft(row.source_name, "canonical_name", event.target.value)} /></td><td><input value={draft.sku} onChange={event => updateDraft(row.source_name, "sku", event.target.value)} /></td><td><input value={draft.category} onChange={event => updateDraft(row.source_name, "category", event.target.value)} /></td><td><input value={draft.brand} onChange={event => updateDraft(row.source_name, "brand", event.target.value)} /></td></tr>;
            })}
          </tbody></table></div>
          {newItemRows.some(row => !(newDrafts[row.source_name]?.canonical_name ?? "").trim()) ? <div className="info-banner">Give every new product an approved Dutchie Product Name.</div> : <>
            <label className="checkbox-row"><input type="checkbox" checked={approveNew} onChange={event => setApproveNew(event.target.checked)} />I approve these new names for this organization&apos;s Dutchie catalog.</label>
            <div className="form-actions"><button className="primary" type="button" disabled={!approveNew} onClick={addNewProducts}>Add new products to the Dutchie naming catalog</button></div>
          </>}
          <div className="info-banner">Save the approved new products to the Dutchie naming catalog before exporting.</div>
        </> : missingCount ? <div className="info-banner">Choose a correct catalog name for {missingCount} item(s) before exporting.</div> : <>
          <label className="checkbox-row"><input type="checkbox" checked={reviewed} onChange={event => { setReviewed(event.target.checked); setConfirmedSignature(""); }} />I reviewed the suggested names and confirmed they match this store&apos;s Dutchie catalog.</label>
          {reviewed ? <div className="form-actions"><button className="primary" type="button" onClick={confirm}>Confirm names and remember mappings</button></div> : null}
          {confirmedSignature === currentSignature() ? <>
            <div className="form-actions"><button className="primary" type="button" onClick={exportNames}>Download Dutchie product names</button></div>
            <p className="muted">The download contains {manifest.row_count.toLocaleString()} rows in manifest order and exactly one column: Correct Item Name (the approved Dutchie Product Name).</p>
          </> : <div className="info-banner">Confirm the reviewed names to unlock the one-column export.</div>}
        </>}
      </> : null}
    </section> : null}

    {tab === "library" ? <section className="inventory-panel">
      <h4>Organization naming source</h4>
      {status.data?.catalog_count ? <CatalogTable rows={status.data.catalog} /> : <div className="info-banner">No active Dutchie catalog has been saved.</div>}
      <p className="muted">{(status.data?.mapping_count ?? 0).toLocaleString()} confirmed METRC-to-Dutchie mappings are currently remembered for this organization.</p>
    </section> : null}
  </div>;
}

function CatalogTable({ rows }: { rows: CatalogPreviewRow[] | CatalogRow[] }) {
  return <div className="table-wrap compact-table"><table><thead><tr><th>Correct Item Name</th><th>SKU</th><th>Category</th><th>Brand</th></tr></thead><tbody>{rows.map((row, index) => <tr key={("id" in row && row.id) || `${row.canonical_name}-${index}`}><td>{row.canonical_name}</td><td>{row.sku}</td><td>{row.category}</td><td>{row.brand}</td></tr>)}</tbody></table></div>;
}
