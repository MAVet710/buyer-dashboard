import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../lib/api";

type Product = {
  id: string; sku: string; name: string; item_type: string; base_unit: string;
  unit_cost: number; retail_price: number; upc: string; external_product_id: string;
  active: boolean; retail_enabled: boolean; production_enabled: boolean;
  brand: string; category: string; product_format: string; image_url: string;
};
type Profile = {
  brand: string; category: string; subcategory: string; strain: string; manufacturer: string;
  product_format: string; image_url: string; description: string; retail_enabled: boolean; production_enabled: boolean;
};
type Packaging = {
  net_content: number; net_content_unit: string; units_per_package: number; sellable_unit: string;
  case_pack: number; warning_text: string; label_layout: "compact_single" | "compact_split" | "bulk_barcode";
  label_width_in: number; label_height_in: number; label_source_count: number;
};
type Detail = {
  product: Product; profile: Profile | null; packaging: Packaging | null;
  vendors: { id: string; partner_name: string; vendor_sku: string; is_primary: boolean }[];
  mappings: { id: string; system_name: string; external_id: string; external_name: string }[];
  aliases: { id: string; alias: string; source: string }[];
  value_history: { id: string; value_type: string; amount: number; currency: string; effective_at: string }[];
};

const blank = { sku: "", name: "", item_type: "finished_good", base_unit: "unit", upc: "", external_product_id: "", retail_enabled: true, production_enabled: true };
const blankProfile: Profile = { brand: "", category: "", subcategory: "", strain: "", manufacturer: "", product_format: "", image_url: "", description: "", retail_enabled: true, production_enabled: true };
const blankPackaging: Packaging = {
  net_content: 0,
  net_content_unit: "g",
  units_per_package: 1,
  sellable_unit: "each",
  case_pack: 0,
  warning_text: "",
  label_layout: "compact_single",
  label_width_in: 3.5,
  label_height_in: 2.1,
  label_source_count: 1,
};

export function ProductMasterPage({ initialOperation = "retail" }: { initialOperation?: "retail" | "production" }) {
  const client = useQueryClient();
  const [operation, setOperation] = useState<"retail" | "production">(initialOperation);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("active");
  const [itemType, setItemType] = useState("");
  const [selected, setSelected] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ ...blank, retail_enabled: initialOperation === "retail", production_enabled: initialOperation === "production" });
  const [profile, setProfile] = useState(blankProfile);
  const [packaging, setPackaging] = useState(blankPackaging);
  const [alias, setAlias] = useState("");
  const [mapping, setMapping] = useState({ system_name: "dutchie", external_id: "", external_name: "" });
  const [value, setValue] = useState({ value_type: "retail_price", amount: 0, currency: "USD", source: "manual", source_reference: "" });

  const products = useQuery({
    queryKey: ["product-master", operation, search, status, itemType],
    queryFn: ({ signal }) => apiGet<Product[]>(`/api/v1/product-master?operation=${operation}&search=${encodeURIComponent(search)}&status=${status}&item_type=${itemType}`, signal),
  });
  const detail = useQuery({
    queryKey: ["product-master-detail", operation, selected],
    queryFn: ({ signal }) => apiGet<Detail>(`/api/v1/product-master/${selected}`, signal),
    enabled: Boolean(selected),
  });

  useEffect(() => {
    if (!detail.data) return;
    setProfile(detail.data.profile ?? { ...blankProfile, retail_enabled: detail.data.product.retail_enabled, production_enabled: detail.data.product.production_enabled });
    setPackaging(detail.data.packaging ?? { ...blankPackaging });
  }, [detail.data]);

  const refresh = () => {
    client.invalidateQueries({ queryKey: ["product-master"] });
    client.invalidateQueries({ queryKey: ["product-master-detail"] });
  };
  const create = useMutation({
    mutationFn: () => apiPost<Product>("/api/v1/product-master", createForm),
    onSuccess: row => {
      setShowCreate(false);
      setCreateForm({ ...blank, retail_enabled: operation === "retail", production_enabled: operation === "production" });
      setSelected(row.id);
      refresh();
    },
  });
  const saveProfile = useMutation({ mutationFn: () => apiPost(`/api/v1/product-master/${selected}/profile`, profile), onSuccess: refresh });
  const savePackaging = useMutation({ mutationFn: () => apiPost(`/api/v1/product-master/${selected}/packaging`, packaging), onSuccess: refresh });
  const addAlias = useMutation({ mutationFn: () => apiPost(`/api/v1/product-master/${selected}/aliases`, { alias, source: "manual" }), onSuccess: () => { setAlias(""); refresh(); } });
  const addMapping = useMutation({ mutationFn: () => apiPost(`/api/v1/product-master/${selected}/mappings`, mapping), onSuccess: () => { setMapping({ ...mapping, external_id: "", external_name: "" }); refresh(); } });
  const addValue = useMutation({ mutationFn: () => apiPost(`/api/v1/product-master/${selected}/values`, value), onSuccess: refresh });
  const archive = useMutation({
    mutationFn: () => {
      const row = detail.data!.product;
      return apiPost(`/api/v1/product-master/${selected}/identity`, {
        sku: row.sku, name: row.name, item_type: row.item_type, base_unit: row.base_unit,
        upc: row.upc, external_product_id: row.external_product_id, active: !row.active,
        retail_enabled: profile.retail_enabled, production_enabled: profile.production_enabled,
      });
    },
    onSuccess: refresh,
  });
  const error = create.error || saveProfile.error || savePackaging.error || addAlias.error || addMapping.error || addValue.error || archive.error;

  return <div className="page">
    <div className="operation-switch">
      <button className={operation === "retail" ? "active" : ""} onClick={() => { setOperation("retail"); setSelected(""); }}>Retail Ops</button>
      <button className={operation === "production" ? "active" : ""} onClick={() => { setOperation("production"); setSelected(""); }}>Production Ops</button>
    </div>
    <div className="page-heading">
      <div>
        <div className="eyebrow">{operation} ops · canonical catalog</div>
        <h1>Product Master</h1>
        <p>{operation === "retail" ? "Govern finished sellable products, merchandising, UPCs, packaging label defaults, vendors and retail pricing." : "Govern bulk materials, work in process, production inputs and outputs, package semantics, compliance mappings and cost history."}</p>
      </div>
      <button className="primary" onClick={() => {
        setCreateForm({ ...blank, item_type: operation === "retail" ? "finished_good" : "cannabis", base_unit: operation === "retail" ? "unit" : "g", retail_enabled: operation === "retail", production_enabled: operation === "production" });
        setShowCreate(true);
      }}>New product</button>
    </div>

    <div className="metrics">
      <div className="metric"><span>Visible products</span><strong>{products.data?.length ?? 0}</strong></div>
      <div className="metric"><span>Needs classification</span><strong>{products.data?.filter(row => !row.category).length ?? 0}</strong></div>
      <div className="metric"><span>Archived</span><strong>{products.data?.filter(row => !row.active).length ?? 0}</strong></div>
      <div className="metric"><span>Workspace</span><strong>{operation === "retail" ? "Retail" : "Production"}</strong></div>
    </div>

    <div className="catalog-layout">
      <section className="inventory-panel">
        <div className="filters">
          <label className="search"><input placeholder="Search name, SKU, UPC or external ID" value={search} onChange={event => setSearch(event.target.value)}/></label>
          <select value={status} onChange={event => setStatus(event.target.value)}><option value="active">Active</option><option value="archived">Archived</option><option value="all">All</option></select>
          <select value={itemType} onChange={event => setItemType(event.target.value)}><option value="">All item types</option><option value="cannabis">Cannabis material</option><option value="packaging">Packaging</option><option value="wip">Work in process</option><option value="finished_good">Finished good</option></select>
        </div>
        <div className="table-wrap"><table><thead><tr><th>Product</th><th>SKU</th><th>Classification</th><th>Unit</th><th>Price / cost</th><th>Status</th></tr></thead><tbody>
          {products.data?.map(row => <tr key={row.id} className={selected === row.id ? "selected-row" : ""} onClick={() => setSelected(row.id)}>
            <td><strong>{row.name}</strong><br/><small>{row.brand || "No brand"} · {row.product_format || row.item_type.replaceAll("_", " ")}</small></td>
            <td>{row.sku}<br/><small>{row.upc || "No UPC"}</small></td><td>{row.category || "Needs setup"}</td><td>{row.base_unit}</td>
            <td>${row.retail_price.toFixed(2)} / ${row.unit_cost.toFixed(2)}</td><td><span className="badge">{row.active ? "active" : "archived"}</span></td>
          </tr>)}
        </tbody></table></div>
      </section>

      <aside className="catalog-detail">
        {!selected ? <div className="empty">Select a product to manage its catalog rules.</div> : detail.isLoading ? <div className="state">Loading product…</div> : detail.data ? <>
          <div className="catalog-title"><div><span>{detail.data.product.sku}</span><h2>{detail.data.product.name}</h2></div><button className="secondary" onClick={() => archive.mutate()}>{detail.data.product.active ? "Archive" : "Restore"}</button></div>
          {profile.image_url ? <img src={profile.image_url} alt={`${detail.data.product.name} menu`} className="catalog-product-image"/> : null}
          <h3>Classification & scope</h3>
          <div className="form-grid">
            {(["brand","category","subcategory","strain","manufacturer","product_format"] as const).map(key => <label key={key}>{key.replaceAll("_", " ")}<input value={profile[key]} onChange={event => setProfile({ ...profile, [key]: event.target.value })}/></label>)}
            <label className="span-2">Menu picture URL<input value={profile.image_url} onChange={event => setProfile({ ...profile, image_url: event.target.value })}/></label>
            <label className="span-2">Description<input value={profile.description} onChange={event => setProfile({ ...profile, description: event.target.value })}/></label>
            <label className="toggle"><input type="checkbox" checked={profile.retail_enabled} onChange={event => setProfile({ ...profile, retail_enabled: event.target.checked })}/>Retail Ops catalog</label>
            <label className="toggle"><input type="checkbox" checked={profile.production_enabled} onChange={event => setProfile({ ...profile, production_enabled: event.target.checked })}/>Production Ops catalog</label>
          </div>
          <button className="primary catalog-save" onClick={() => saveProfile.mutate()}>Save catalog rules</button>

          <h3>Packaging & label defaults</h3>
          <p className="section-note">Label Studio uses these package facts and print settings automatically. The compact split layout works for a two-source Duo label or a one-source 3.5g/7g flower pouch; the tested-source setting controls which version is generated.</p>
          <div className="form-grid">
            <label>Net content<input type="number" min="0" step="0.01" value={packaging.net_content} onChange={event => setPackaging({ ...packaging, net_content: Number(event.target.value) })}/></label>
            <label>Net content unit<input value={packaging.net_content_unit} onChange={event => setPackaging({ ...packaging, net_content_unit: event.target.value })} placeholder="g"/></label>
            <label>Units per package<input type="number" min="0.0001" step="1" value={packaging.units_per_package} onChange={event => setPackaging({ ...packaging, units_per_package: Number(event.target.value) })}/></label>
            <label>Sellable unit<input value={packaging.sellable_unit} onChange={event => setPackaging({ ...packaging, sellable_unit: event.target.value })} placeholder="each"/></label>
            <label>Case pack<input type="number" min="0" step="1" value={packaging.case_pack} onChange={event => setPackaging({ ...packaging, case_pack: Number(event.target.value) })}/></label>
            <label>Print layout<select value={packaging.label_layout} onChange={event => {
              const layout = event.target.value as Packaging["label_layout"];
              setPackaging({ ...packaging, label_layout: layout, label_source_count: layout === "compact_split" ? packaging.label_source_count : 1 });
            }}><option value="compact_single">Compact single-product</option><option value="compact_split">Compact split · Duo / flower pouch</option><option value="bulk_barcode">Wide barcode / bulk</option></select></label>
            <label>Label width (in)<input type="number" min="0.5" max="12" step="0.01" value={packaging.label_width_in} onChange={event => setPackaging({ ...packaging, label_width_in: Number(event.target.value) })}/></label>
            <label>Label height (in)<input type="number" min="0.5" max="12" step="0.01" value={packaging.label_height_in} onChange={event => setPackaging({ ...packaging, label_height_in: Number(event.target.value) })}/></label>
            <label>Tested sources<select aria-label="Label tested source count" value={packaging.label_source_count} disabled={packaging.label_layout !== "compact_split"} onChange={event => setPackaging({ ...packaging, label_source_count: Number(event.target.value) })}><option value={1}>1 source · flower / single product</option><option value={2}>2 sources · Duo</option></select></label>
            <label className="span-2">Package warning statement<textarea rows={5} value={packaging.warning_text} onChange={event => setPackaging({ ...packaging, warning_text: event.target.value })} placeholder="Approved warning language printed with this package configuration"/></label>
          </div>
          <div className="catalog-row"><strong>Label Studio print target</strong><span>{packaging.label_width_in} × {packaging.label_height_in} in</span><small>{packaging.label_layout.replaceAll("_", " ")} · {packaging.label_source_count} tested source{packaging.label_source_count === 1 ? "" : "s"}</small></div>
          <button className="primary catalog-save" onClick={() => savePackaging.mutate()} disabled={savePackaging.isPending}>{savePackaging.isPending ? "Saving…" : "Save packaging & label defaults"}</button>

          <h3>Aliases</h3>
          <div className="inline-form"><input placeholder="Alternate product name" value={alias} onChange={event => setAlias(event.target.value)}/><button className="secondary" disabled={!alias} onClick={() => addAlias.mutate()}>Add</button></div>
          <div className="chip-list">{detail.data.aliases.map(row => <span className="badge" key={row.id}>{row.alias} · {row.source}</span>)}</div>

          <h3>External mappings</h3>
          <div className="form-grid"><label>System<select value={mapping.system_name} onChange={event => setMapping({ ...mapping, system_name: event.target.value })}><option>dutchie</option><option>metrc</option><option>leaflink</option><option>other</option></select></label><label>External ID<input value={mapping.external_id} onChange={event => setMapping({ ...mapping, external_id: event.target.value })}/></label><label className="span-2">External name<input value={mapping.external_name} onChange={event => setMapping({ ...mapping, external_name: event.target.value })}/></label></div>
          <button className="secondary catalog-save" disabled={!mapping.external_id} onClick={() => addMapping.mutate()}>Map external product</button>
          {detail.data.mappings.map(row => <div className="catalog-row" key={row.id}><strong>{row.system_name}</strong><span>{row.external_id}</span><small>{row.external_name}</small></div>)}

          <h3>Price & cost history</h3>
          <div className="inline-form"><select value={value.value_type} onChange={event => setValue({ ...value, value_type: event.target.value })}><option value="retail_price">Retail price</option><option value="unit_cost">Unit cost</option><option value="wholesale_price">Wholesale price</option><option value="landed_cost">Landed cost</option></select><input type="number" min="0" step="0.01" value={value.amount} onChange={event => setValue({ ...value, amount: Number(event.target.value) })}/><button className="secondary" onClick={() => addValue.mutate()}>Record</button></div>
          {detail.data.value_history.slice(0, 8).map(row => <div className="catalog-row" key={row.id}><strong>{row.value_type.replaceAll("_", " ")}</strong><span>{row.currency} {row.amount.toFixed(2)}</span><small>{new Date(row.effective_at).toLocaleString()}</small></div>)}
        </> : null}
      </aside>
    </div>
    {error ? <div className="form-error">{error.message}</div> : null}

    {showCreate ? <div className="modal-backdrop"><div className="modal compact">
      <div className="modal-heading"><div><div className="eyebrow">Canonical catalog</div><h2>New product</h2></div><button className="secondary" onClick={() => setShowCreate(false)}>Close</button></div>
      <div className="form-grid">
        <label>Product name<input value={createForm.name} onChange={event => setCreateForm({ ...createForm, name: event.target.value })}/></label>
        <label>SKU<input value={createForm.sku} onChange={event => setCreateForm({ ...createForm, sku: event.target.value })}/></label>
        <label>Item type<select value={createForm.item_type} onChange={event => setCreateForm({ ...createForm, item_type: event.target.value })}><option value="finished_good">Finished good</option><option value="cannabis">Cannabis material</option><option value="wip">Work in process</option><option value="packaging">Packaging</option></select></label>
        <label>Base unit<input value={createForm.base_unit} onChange={event => setCreateForm({ ...createForm, base_unit: event.target.value })}/></label>
        <label>UPC<input value={createForm.upc} onChange={event => setCreateForm({ ...createForm, upc: event.target.value })}/></label>
        <label>External product ID<input value={createForm.external_product_id} onChange={event => setCreateForm({ ...createForm, external_product_id: event.target.value })}/></label>
        <label className="toggle"><input type="checkbox" checked={createForm.retail_enabled} onChange={event => setCreateForm({ ...createForm, retail_enabled: event.target.checked })}/>Retail Ops</label>
        <label className="toggle"><input type="checkbox" checked={createForm.production_enabled} onChange={event => setCreateForm({ ...createForm, production_enabled: event.target.checked })}/>Production Ops</label>
      </div>
      <button className="primary submit" disabled={!createForm.name || !createForm.sku} onClick={() => create.mutate()}>Create catalog product</button>
    </div></div> : null}
  </div>;
}
