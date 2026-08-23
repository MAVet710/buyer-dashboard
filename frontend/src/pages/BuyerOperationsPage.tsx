import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { apiDownload, apiGet, apiPost, downloadBlob } from "../lib/api";

type Row = Record<string, unknown>;
type Dashboard = {
  controls: { target_doh: number; velocity_adjustment: number; sales_days: number; sku_window: number };
  summary: { units_sold: number; reorder_asap: number; tracked_products: number; categories: number };
  sources: { inventory: { filename: string; rows: number }; sales: { filename: string; rows: number } };
  category_dos: Row[];
  forecast: Row[];
  product_rows: Row[];
  product_rows_total: number;
  sku_views: { all: Row[]; reorder: Row[]; overstock: Row[]; expiring: Row[] };
};
type Drilldown = { sku_rows: Row[]; batch_rows: Row[] };
type DoobieResult = {
  answer: string;
  explanation?: string;
  recommendations?: unknown[];
  risk_flags?: unknown[];
  inefficiencies?: unknown[];
  sources?: unknown[];
  confidence?: string;
  mode?: string;
};
type SkuTab = "all" | "reorder" | "overstock" | "expiring";
type MetricFilter = "All" | "Reorder ASAP";
type InventoryCondition = {
  reorder: number;
  noStock: number;
  overstock: number;
  expiring: number;
  overstockExposure: number;
  expiringExposure: number;
  onHandCost: number;
  onHandUnits: number;
};

const REB_CATEGORIES = ["flower", "pre rolls", "vapes", "edibles", "beverages", "concentrates", "tinctures", "topicals"];
const FORECAST_COLUMNS = ["top_products","mastercategory","subcategory","strain_type","packagesize","onhandunits","unitssold","avgunitsperday","daysonhand","reorderqty","reorderpriority","product_count"];
const PRODUCT_COLUMNS = ["product_name","subcategory","strain_type","packagesize","onhandunits","unitssold","avgunitsperday","daysonhand"];
const SKU_COLUMNS = ["sku","product_name","brand_vendor","category","onhandunits","avg_weekly_sales","days_of_supply","weeks_of_supply","dollars_on_hand","retail_dollars_on_hand","expiration_date","days_to_expire","status"];
const SKU_COMPACT_COLUMNS = ["product_name","category","brand_vendor","onhandunits","avg_weekly_sales","days_of_supply","dollars_on_hand","expiration_date","status"];

export function BuyerOperationsPage(_props: { onNavigate?: (page: string) => void }) {
  const [targetDoh, setTargetDoh] = useState(21);
  const [velocity, setVelocity] = useState(0.5);
  const [salesDays, setSalesDays] = useState(60);
  const [skuWindow, setSkuWindow] = useState(56);
  const [metricFilter, setMetricFilter] = useState<MetricFilter>("All");
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [categorySelectionTouched, setCategorySelectionTouched] = useState(false);
  const [showProductRows, setShowProductRows] = useState(false);
  const [skuTab, setSkuTab] = useState<SkuTab>("all");
  const [buyerSearch, setBuyerSearch] = useState("");
  const [showTopN, setShowTopN] = useState(0);
  const [sortBy, setSortBy] = useState("dollars_on_hand_desc");
  const [legacyCategory, setLegacyCategory] = useState("All");
  const [legacyBrand, setLegacyBrand] = useState("All");
  const [expirationWindow, setExpirationWindow] = useState("Any");
  const [onHandOnly, setOnHandOnly] = useState(true);
  const [minDoh, setMinDoh] = useState(0);
  const [maxDoh, setMaxDoh] = useState(9999);

  useEffect(() => {
    sessionStorage.setItem("buyer-dash-buyer-controls", JSON.stringify({ target_doh: targetDoh, velocity_adjustment: velocity, sales_days: salesDays, sku_window: skuWindow }));
  }, [targetDoh, velocity, salesDays, skuWindow]);

  const query = useMemo(() => new URLSearchParams({
    target_doh: String(targetDoh),
    velocity_adjustment: String(velocity),
    sales_days: String(salesDays),
    sku_window: String(skuWindow),
  }), [targetDoh, velocity, salesDays, skuWindow]);
  const dashboard = useQuery({
    queryKey: ["buyer-parity", targetDoh, velocity, salesDays, skuWindow],
    queryFn: ({ signal }) => apiGet<Dashboard>(`/api/v1/buyer-parity/dashboard?${query}`, signal),
  });

  const categoryOptions = useMemo(() => {
    const values = Array.from(new Set((dashboard.data?.forecast ?? []).map(row => text(row.subcategory)).filter(Boolean)));
    return values.sort((a, b) => {
      const ai = REB_CATEGORIES.indexOf(a.toLowerCase());
      const bi = REB_CATEGORIES.indexOf(b.toLowerCase());
      const ar = ai < 0 ? REB_CATEGORIES.length : ai;
      const br = bi < 0 ? REB_CATEGORIES.length : bi;
      return ar === br ? a.localeCompare(b) : ar - br;
    });
  }, [dashboard.data]);
  const visibleCategories = categorySelectionTouched ? selectedCategories : categoryOptions;
  const metricRows = useMemo(() => {
    const rows = dashboard.data?.forecast ?? [];
    return metricFilter === "Reorder ASAP" ? rows.filter(row => text(row.reorderpriority) === "1 – Reorder ASAP") : rows;
  }, [dashboard.data, metricFilter]);
  const visibleForecast = useMemo(() => metricRows.filter(row => visibleCategories.includes(text(row.subcategory))), [metricRows, visibleCategories]);
  const visibleProductRows = useMemo(() => (dashboard.data?.product_rows ?? []).filter(row => visibleCategories.includes(text(row.subcategory))), [dashboard.data, visibleCategories]);
  const productRowsTruncated = Boolean(dashboard.data && dashboard.data.product_rows_total > dashboard.data.product_rows.length);

  const legacyCategoryOptions = useMemo(() => sortedUnique((dashboard.data?.sku_views.all ?? []).map(row => text(row.category))), [dashboard.data]);
  const legacyBrandOptions = useMemo(() => sortedUnique((dashboard.data?.sku_views.all ?? []).map(row => text(row.brand_vendor))), [dashboard.data]);
  const filteredInventoryBase = useMemo(() => {
    let rows = [...(dashboard.data?.sku_views.all ?? [])];
    const search = buyerSearch.trim().toLowerCase();
    if (search) rows = rows.filter(row => [row.sku, row.product_name, row.brand_vendor].some(value => text(value).toLowerCase().includes(search)));
    if (legacyCategory !== "All") rows = rows.filter(row => text(row.category) === legacyCategory);
    if (legacyBrand !== "All") rows = rows.filter(row => text(row.brand_vendor) === legacyBrand);
    if (expirationWindow !== "Any") {
      rows = rows.filter(row => {
        const days = optionalNumber(row.days_to_expire);
        if (days == null) return false;
        if (expirationWindow === "Expired") return days < 0;
        const windowDays = expirationWindow === "30 days" ? 30 : expirationWindow === "60 days" ? 60 : 90;
        return days >= 0 && days <= windowDays;
      });
    }
    if (onHandOnly) rows = rows.filter(row => number(row.onhandunits) > 0);
    rows = rows.filter(row => {
      const doh = number(row.days_of_supply);
      return doh >= minDoh && doh <= maxDoh;
    });
    const sorters: Record<string, (a: Row, b: Row) => number> = {
      dollars_on_hand_desc: (a, b) => number(b.dollars_on_hand) - number(a.dollars_on_hand),
      days_of_supply_asc: (a, b) => number(a.days_of_supply) - number(b.days_of_supply),
      days_of_supply_desc: (a, b) => number(b.days_of_supply) - number(a.days_of_supply),
      weekly_sales_desc: (a, b) => number(b.avg_weekly_sales) - number(a.avg_weekly_sales),
      on_hand_desc: (a, b) => number(b.onhandunits) - number(a.onhandunits),
      expiration_asc: (a, b) => (optionalNumber(a.days_to_expire) ?? 100000) - (optionalNumber(b.days_to_expire) ?? 100000),
    };
    rows.sort(sorters[sortBy] ?? sorters.dollars_on_hand_desc);
    return rows;
  }, [dashboard.data, buyerSearch, legacyCategory, legacyBrand, expirationWindow, onHandOnly, minDoh, maxDoh, sortBy]);
  const filteredSkuRows = useMemo(() => showTopN > 0 ? filteredInventoryBase.slice(0, showTopN) : filteredInventoryBase, [filteredInventoryBase, showTopN]);
  const filteredCondition = useMemo(() => inventoryCondition(filteredInventoryBase), [filteredInventoryBase]);
  const allSkuColumns = useMemo(() => {
    const ordered = [...SKU_COLUMNS];
    const extras = sortedUnique(filteredSkuRows.flatMap(row => Object.keys(row))).filter(column => !ordered.includes(column));
    return [...ordered, ...extras];
  }, [filteredSkuRows]);
  const statusRows = useMemo(() => {
    if (skuTab === "reorder") return filteredInventoryBase.filter(row => number(row.days_of_supply) > 0 && number(row.days_of_supply) <= 21);
    if (skuTab === "overstock") return filteredInventoryBase.filter(row => number(row.days_of_supply) >= 90);
    if (skuTab === "expiring") return filteredInventoryBase.filter(row => { const days = optionalNumber(row.days_to_expire); return days != null && days < 60; });
    return filteredInventoryBase;
  }, [filteredInventoryBase, skuTab]);

  const doobieCategories = legacyCategory === "All" ? visibleCategories : [legacyCategory];
  const doobiePayload = {
    categories: doobieCategories,
    brands: legacyBrand === "All" ? [] : [legacyBrand],
    search: buyerSearch,
    expiration_window: expirationWindow,
    on_hand_only: onHandOnly,
    min_doh: minDoh,
    max_doh: maxDoh,
    velocity_window: skuWindow,
    top_n: showTopN,
    sort_by: sortBy,
    target_doh: targetDoh,
    velocity_adjustment: velocity,
    sales_days: salesDays,
    state: "MA",
  };
  const inventoryCheck = useMutation({
    mutationFn: () => apiPost<DoobieResult>("/api/v1/buyer-parity/inventory-check", {
      ...doobiePayload,
      question: "Which inventory risks need immediate attention in the currently filtered Buyer Dashboard slice?",
    }),
  });
  const buyerBrief = useMutation({
    mutationFn: () => apiPost<DoobieResult>("/api/v1/buyer-parity/buyer-brief", {
      ...doobiePayload,
      question: "What should I reorder right now with quantities?",
    }),
  });

  const download = async (kind: "forecast" | "product" | "sku") => {
    const params = new URLSearchParams(query);
    params.set("kind", kind);
    visibleCategories.forEach(category => params.append("category", category));
    if (kind === "forecast" && metricFilter === "Reorder ASAP") params.set("reorder_only", "true");
    const names = { forecast: "forecast_table.xlsx", product: "product_level_forecast.xlsx", sku: "sku_inventory_buyer_view.xlsx" };
    downloadBlob(await apiDownload(`/api/v1/buyer-parity/export?${params}`), names[kind]);
  };

  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">Buyer Dashboard</div><h1>Buyer Dashboard</h1><p>Original buyer workflow ported into the modular app with Doobie replacing legacy AI.</p></div></div>

    <section className="inventory-panel parity-controls buyer-primary-controls">
      <NumberControl label="Target Days on Hand" value={targetDoh} min={1} max={60} step={1} onChange={setTargetDoh}/>
      <NumberControl label="Velocity Adjustment" value={velocity} min={0.01} max={5} step={0.01} onChange={setVelocity}/>
      <label>Days in Sales Period<input type="range" min={7} max={120} value={salesDays} onChange={event => setSalesDays(Number(event.target.value))}/><span>{salesDays}</span></label>
    </section>

    {dashboard.isError ? <div className="state error">{dashboard.error.message}</div> : null}
    {dashboard.isLoading ? <div className="state">Building the Buyer Dashboard forecast from the active inventory and sales sources…</div> : null}
    {dashboard.data ? <>
      <section className="buyer-filter-buttons">
        <button className={`metric metric-button ${metricFilter === "All" ? "active" : ""}`} type="button" onClick={() => setMetricFilter("All")}><span>Units Sold (Granular Size-Level)</span><strong>{dashboard.data.summary.units_sold.toLocaleString()}</strong></button>
        <button className={`metric metric-button ${metricFilter === "Reorder ASAP" ? "active" : ""}`} type="button" onClick={() => setMetricFilter("Reorder ASAP")}><span>Reorder ASAP (Lines)</span><strong>{dashboard.data.summary.reorder_asap.toLocaleString()}</strong></button>
      </section>
      <p className="current-filter"><em>Current filter: <strong>{metricFilter}</strong></em></p>

      <section className="inventory-panel buyer-visibility-controls">
        <CategoryMultiSelect options={categoryOptions} selected={visibleCategories} onChange={values => { setCategorySelectionTouched(true); setSelectedCategories(values); }}/>
        <label className="toggle"><input type="checkbox" checked={showProductRows} onChange={event => setShowProductRows(event.target.checked)}/> Show product-level rows</label>
      </section>

      <section className="metrics">
        <Metric label="Tracked Categories" value={new Set(visibleForecast.map(row => text(row.subcategory))).size}/>
        <Metric label="Forecast Rows" value={visibleForecast.length}/>
        <Metric label="Reorder ASAP" value={visibleForecast.filter(row => text(row.reorderpriority) === "1 – Reorder ASAP").length}/>
        <Metric label="Product Rows" value={dashboard.data.product_rows_total}/>
      </section>

      <section className="inventory-panel">
        <h3>Category DOS (at a glance)</h3>
        <DataTable rows={categoryDosForForecast(metricRows)} columns={["subcategory","category_dos","reorder_lines","product_count","top_products"]}/>
      </section>

      <section className="inventory-panel">
        <div className="section-heading"><div><h3>Forecast Table</h3></div><button className="secondary" type="button" onClick={() => download("forecast")}>📥 Export Forecast Table (Excel)</button></div>
        <DataTable rows={visibleForecast} columns={FORECAST_COLUMNS}/>
      </section>

      <section className="buyer-category-expanders">
        {visibleCategories.map(category => {
          const rows = visibleForecast.filter(row => text(row.subcategory) === category);
          if (!rows.length) return null;
          return <CategoryExpander key={category} category={category} rows={rows} targetDoh={targetDoh} velocity={velocity} salesDays={salesDays}/>;
        })}
      </section>

      {showProductRows && visibleProductRows.length ? <section className="inventory-panel">
        <h3>📦 Product-Level Rows</h3>
        {productRowsTruncated ? <p className="warning-caption">⚠️ Showing top {dashboard.data.product_rows.length.toLocaleString()} rows by units sold. Download below for full data.</p> : null}
        <DataTable rows={visibleProductRows} columns={PRODUCT_COLUMNS}/>
        <div className="download-row"><button className="secondary" type="button" onClick={() => download("product")}>📥 Download Product-Level Table (Excel)</button></div>
      </section> : null}

      <section className="inventory-panel buyer-filter-settings">
        <h3>🔍 Buyer Filters &amp; Settings</h3>
        <div className="buyer-settings-grid">
          <label className="buyer-setting-wide">Search (SKU / Product / Brand)<span className="field-help" title="Filters the current SKU inventory view and the inventory slice sent to Doobie.">?</span><input value={buyerSearch} placeholder="Type to filter…" onChange={event => setBuyerSearch(event.target.value)}/></label>
          <label>Velocity window<span className="field-help" title="Sales history used to calculate run rate and days of supply.">?</span><select value={skuWindow} onChange={event => setSkuWindow(Number(event.target.value))}><option value={28}>Last 28 days</option><option value={56}>Last 56 days</option><option value={84}>Last 84 days</option></select></label>
          <label>Show top N<select value={showTopN} onChange={event => setShowTopN(Number(event.target.value))}><option value={0}>All</option><option value={10}>10</option><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option></select></label>
          <label>Sort by<select value={sortBy} onChange={event => setSortBy(event.target.value)}><option value="dollars_on_hand_desc">$ on hand ↓</option><option value="days_of_supply_asc">DOH ↑</option><option value="days_of_supply_desc">DOH ↓</option><option value="weekly_sales_desc">Weekly sales ↓</option><option value="on_hand_desc">On hand ↓</option><option value="expiration_asc">Expiration ↑</option></select></label>
          <label>Category / Subcategory<select value={legacyCategory} onChange={event => setLegacyCategory(event.target.value)}><option>All</option>{legacyCategoryOptions.map(category => <option key={category}>{category}</option>)}</select></label>
          <label>Vendor / Brand<select value={legacyBrand} onChange={event => setLegacyBrand(event.target.value)}><option>All</option>{legacyBrandOptions.map(brand => <option key={brand}>{brand}</option>)}</select></label>
          <label>Expiration window<span className="field-help" title="Limits the current view by the nearest expiration date when inventory provides one.">?</span><select value={expirationWindow} onChange={event => setExpirationWindow(event.target.value)}><option>Any</option><option>30 days</option><option>60 days</option><option>90 days</option><option>Expired</option></select></label>
          <label className="toggle buyer-onhand-toggle"><input type="checkbox" checked={onHandOnly} onChange={event => setOnHandOnly(event.target.checked)}/> On-hand &gt; 0 <span className="field-help" title="When enabled, zero-stock items are removed from the working view.">?</span></label>
          <NumberControl label="DOH min (days)" value={minDoh} min={0} max={9999} step={1} onChange={setMinDoh}/>
          <NumberControl label="DOH max (days)" value={maxDoh} min={0} max={9999} step={1} onChange={setMaxDoh}/>
        </div>
      </section>

      <section className="metrics buyer-filter-condition">
        <Metric label="Units On Hand" value={filteredCondition.onHandUnits}/>
        <Metric label="Reorder / Low Cover" value={filteredCondition.reorder}/>
        <Metric label="No Stock" value={filteredCondition.noStock}/>
        <Metric label="🟠 Overstock SKUs" value={filteredCondition.overstock}/>
        <Metric label="⚠️ Expiring <60d" value={`${filteredCondition.expiring.toLocaleString()} (${money(filteredCondition.expiringExposure)})`}/>
        <Metric label="Overstock $" value={money(filteredCondition.overstockExposure)}/>
        <Metric label="$ On Hand" value={money(filteredCondition.onHandCost)}/>
      </section>

      <section className="inventory-panel">
        <div className="section-heading"><div><h3>📋 SKU Inventory Buyer View</h3><p>{filteredSkuRows.length.toLocaleString()} SKU(s) (velocity window: {skuWindow} days){showTopN > 0 && filteredInventoryBase.length > filteredSkuRows.length ? ` · showing top ${filteredSkuRows.length.toLocaleString()} of ${filteredInventoryBase.length.toLocaleString()}` : ""}</p></div></div>
        {dashboard.data.sources.inventory.rows > 0 ? <p className="source-caption">Inventory cross-reference is active for PO-related buyer review.</p> : null}
        <DataTable rows={filteredSkuRows} columns={SKU_COMPACT_COLUMNS}/>
        <details className="streamlit-expander buyer-all-columns"><summary>🔎 Show all columns</summary><div className="streamlit-expander-body"><DataTable rows={filteredSkuRows} columns={allSkuColumns}/></div></details>
        <details className="streamlit-expander buyer-status-views"><summary>Inventory status views</summary><div className="streamlit-expander-body"><div className="view-tabs"><button className={skuTab === "all" ? "active" : ""} onClick={() => setSkuTab("all")}>📦 All Inventory</button><button className={skuTab === "reorder" ? "active" : ""} onClick={() => setSkuTab("reorder")}>🔴 Reorder</button><button className={skuTab === "overstock" ? "active" : ""} onClick={() => setSkuTab("overstock")}>🟠 Overstock</button><button className={skuTab === "expiring" ? "active" : ""} onClick={() => setSkuTab("expiring")}>⚠️ Expiring</button></div><DataTable rows={statusRows} columns={SKU_COLUMNS}/></div></details>
      </section>

      <section className="inventory-panel">
        <h3>🤖 Doobie Inventory Check</h3>
        <p className="source-caption">Doobie replaces the legacy AI Inventory Check and evaluates this exact filtered buyer view.</p>
        <button className="primary" type="button" disabled={inventoryCheck.isPending || !filteredSkuRows.length} onClick={() => inventoryCheck.mutate()}>{inventoryCheck.isPending ? "Running…" : "Run Doobie Inventory Check"}</button>
        {inventoryCheck.isError ? <div className="state error">{inventoryCheck.error.message}</div> : null}
        {inventoryCheck.data ? <DoobieAnswer result={inventoryCheck.data}/> : null}
      </section>

      <section className="inventory-panel">
        <h3>🧠 Doobie Buyer Brief</h3>
        <button className="primary" type="button" disabled={buyerBrief.isPending || !filteredSkuRows.length} onClick={() => buyerBrief.mutate()}>{buyerBrief.isPending ? "Generating…" : "Generate Doobie Buyer Brief"}</button>
        {buyerBrief.isError ? <div className="state error">{buyerBrief.error.message}</div> : null}
        {buyerBrief.data ? <DoobieAnswer result={buyerBrief.data}/> : null}
      </section>
    </> : null}
  </div>;
}

function CategoryExpander({ category, rows, targetDoh, velocity, salesDays }: { category: string; rows: Row[]; targetDoh: number; velocity: number; salesDays: number }) {
  const onHand = rows.reduce((sum, row) => sum + number(row.onhandunits), 0);
  const daily = rows.reduce((sum, row) => sum + number(row.avgunitsperday), 0);
  const categoryDos = daily > 0 ? Math.trunc(onHand / daily) : 0;
  const flagged = rows.filter(row => text(row.reorderpriority) === "1 – Reorder ASAP");
  return <details className="streamlit-expander"><summary>{title(category)}</summary><div className="streamlit-expander-body"><p><strong>Category DOS:</strong> {categoryDos} days</p><DataTable rows={rows} columns={FORECAST_COLUMNS}/>{flagged.length ? <><h4>🔎 Flagged Reorder Lines — View SKUs (Weighted by Velocity)</h4>{flagged.map((row, index) => <ReorderExpander key={`${category}-${text(row.strain_type)}-${text(row.packagesize)}-${index}`} row={row} targetDoh={targetDoh} velocity={velocity} salesDays={salesDays}/>)}</> : null}</div></details>;
}

function ReorderExpander({ row, targetDoh, velocity, salesDays }: { row: Row; targetDoh: number; velocity: number; salesDays: number }) {
  const [open, setOpen] = useState(false);
  const label = `${text(row.strain_type) || "unspecified"} • ${text(row.packagesize) || "unspecified"} • Reorder Qty: ${Math.trunc(number(row.reorderqty))}`;
  return <details className="streamlit-expander" onToggle={event => setOpen(event.currentTarget.open)}><summary>View SKUs — {label}</summary><div className="streamlit-expander-body">{open ? <ReorderDrilldown row={row} targetDoh={targetDoh} velocity={velocity} salesDays={salesDays}/> : null}</div></details>;
}

function ReorderDrilldown({ row, targetDoh, velocity, salesDays }: { row: Row; targetDoh: number; velocity: number; salesDays: number }) {
  const params = useMemo(() => new URLSearchParams({
    category: text(row.subcategory),
    size: text(row.packagesize) || "unspecified",
    strain_type: text(row.strain_type) || "unspecified",
    target_doh: String(targetDoh),
    velocity_adjustment: String(velocity),
    sales_days: String(salesDays),
  }).toString(), [row, targetDoh, velocity, salesDays]);
  const query = useQuery({ queryKey: ["buyer-reorder-drilldown", params], queryFn: ({ signal }) => apiGet<Drilldown>(`/api/v1/buyer-parity/drilldown?${params}`, signal) });
  if (query.isLoading) return <div className="state">Building SKU and batch evidence…</div>;
  if (query.isError) return <div className="state error">{query.error.message}</div>;
  if (!query.data) return null;
  return <>{query.data.sku_rows.length ? <DataTable rows={query.data.sku_rows} columns={["product_name","batch_id","package_id","unitssold","net_sales","est_units_per_day","sku"]}/> : <div className="state">No matching SKU-level sales rows found for this slice.</div>}{query.data.batch_rows.length ? <><h5>🧬 Batch / Lot Breakdown (On-Hand)</h5><DataTable rows={query.data.batch_rows} columns={["batch","batch_onhandunits"]}/></> : null}</>;
}

function CategoryMultiSelect({ options, selected, onChange }: { options: string[]; selected: string[]; onChange: (values: string[]) => void }) {
  const allSelected = options.length > 0 && selected.length === options.length;
  return <details className="multi-select-control"><summary><span>Visible Categories</span><strong>{allSelected ? "All categories" : `${selected.length} selected`}</strong></summary><div className="multi-select-menu"><div className="heading-actions"><button className="link-button" type="button" onClick={event => { event.preventDefault(); onChange(options); }}>Select all</button><button className="link-button" type="button" onClick={event => { event.preventDefault(); onChange([]); }}>Clear</button></div>{options.map(option => <label key={option}><input type="checkbox" checked={selected.includes(option)} onChange={event => onChange(event.target.checked ? [...selected, option] : selected.filter(value => value !== option))}/><span>{option}</span></label>)}</div></details>;
}

function categoryDosForForecast(rows: Row[]) {
  const grouped = new Map<string, Row[]>();
  rows.forEach(row => {
    const category = text(row.subcategory);
    grouped.set(category, [...(grouped.get(category) ?? []), row]);
  });
  return [...grouped.entries()].map(([subcategory, categoryRows]) => {
    const onHand = categoryRows.reduce((sum, row) => sum + number(row.onhandunits), 0);
    const daily = categoryRows.reduce((sum, row) => sum + number(row.avgunitsperday), 0);
    return {
      subcategory,
      category_dos: daily > 0 ? Math.trunc(onHand / daily) : 0,
      reorder_lines: categoryRows.filter(row => text(row.reorderpriority) === "1 – Reorder ASAP").length,
      product_count: categoryRows.reduce((sum, row) => sum + number(row.product_count), 0),
      top_products: categoryRows.map(row => text(row.top_products)).filter(Boolean).join(", "),
    };
  }).sort((a, b) => b.reorder_lines - a.reorder_lines || a.category_dos - b.category_dos);
}

function inventoryCondition(rows: Row[]): InventoryCondition {
  let reorder = 0; let noStock = 0; let overstock = 0; let expiring = 0;
  let overstockExposure = 0; let expiringExposure = 0; let onHandCost = 0; let onHandUnits = 0;
  rows.forEach(row => {
    const onHand = number(row.onhandunits); const doh = number(row.days_of_supply); const dollars = number(row.dollars_on_hand); const expiry = optionalNumber(row.days_to_expire);
    onHandUnits += onHand; onHandCost += dollars;
    if (onHand <= 0) noStock += 1;
    if (doh > 0 && doh <= 21) reorder += 1;
    if (doh >= 90) { overstock += 1; overstockExposure += dollars; }
    if (expiry != null && expiry >= 0 && expiry < 60) { expiring += 1; expiringExposure += dollars; }
  });
  return { reorder, noStock, overstock, expiring, overstockExposure, expiringExposure, onHandCost, onHandUnits };
}

function DataTable({ rows, columns }: { rows: Row[]; columns: string[] }) {
  const visible = columns.filter(column => rows.some(row => Object.prototype.hasOwnProperty.call(row, column)));
  if (!rows.length) return <div className="empty">No matching rows.</div>;
  return <div className="table-wrap"><table><thead><tr>{visible.map(column => <th key={column}>{header(column)}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{visible.map(column => <td key={column}>{render(row[column])}</td>)}</tr>)}</tbody></table></div>;
}

function Metric({ label, value }: { label: string; value: string | number }) { return <article className="metric"><span>{label}</span><strong>{typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : value}</strong></article>; }
function NumberControl({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (value: number) => void }) { return <label>{label}<input type="number" value={value} min={min} max={max} step={step} onChange={event => onChange(Number(event.target.value))}/></label>; }
function DoobieAnswer({ result }: { result: DoobieResult }) { return <div className="doobie-answer"><strong>{result.confidence ? `${result.confidence} confidence · ` : ""}Doobie</strong><p>{result.answer}</p>{result.explanation ? <p>{result.explanation}</p> : null}{Array.isArray(result.recommendations) && result.recommendations.length ? <><h4>Recommendations</h4><pre>{JSON.stringify(result.recommendations, null, 2)}</pre></> : null}{Array.isArray(result.risk_flags) && result.risk_flags.length ? <><h4>Risk flags</h4><pre>{JSON.stringify(result.risk_flags, null, 2)}</pre></> : null}</div>; }
function header(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase()); }
function title(value: string) { return value.replace(/\b\w/g, char => char.toUpperCase()); }
function text(value: unknown) { return value == null ? "" : String(value); }
function number(value: unknown) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0; }
function optionalNumber(value: unknown) { if (value == null || value === "") return null; const parsed = Number(value); return Number.isFinite(parsed) ? parsed : null; }
function sortedUnique(values: string[]) { return Array.from(new Set(values.filter(value => value.trim()))).sort((a, b) => a.localeCompare(b)); }
function money(value: number) { return Number(value || 0).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }); }
function render(value: unknown) { if (value == null || value === "") return "—"; if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 }); if (typeof value === "boolean") return value ? "Yes" : "No"; if (Array.isArray(value)) return value.join(", "); if (typeof value === "object") return JSON.stringify(value); return String(value); }
