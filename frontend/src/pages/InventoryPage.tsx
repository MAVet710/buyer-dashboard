import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useInventory } from "../hooks/useInventory";
import type { InventoryPackage } from "../types/inventory";
import { ReceiveInventory } from "../components/ReceiveInventory";
import { ReceiveHistory } from "../components/ReceiveHistory";
import { AdjustInventory } from "../components/AdjustInventory";
import { InventoryAudits } from "../components/InventoryAudits";
import { PackageLineage } from "../components/PackageLineage";
import { PlantInventory } from "../components/PlantInventory";
import { apiGet } from "../lib/api";

const baseColumns: ColumnDef<InventoryPackage>[] = [
  { accessorKey: "product_name", header: "Material" },
  { accessorKey: "package_id", header: "Package / Lot" },
  { accessorKey: "material_type", header: "Type" },
  { accessorKey: "location", header: "Location" },
  { accessorKey: "status", header: "Status" },
  { accessorKey: "available", header: "Available", cell: ({ row }) => `${row.original.available.toLocaleString()} ${row.original.unit}` },
  { accessorKey: "reserved", header: "Reserved", cell: ({ row }) => `${row.original.reserved.toLocaleString()} ${row.original.unit}` },
  { accessorKey: "attention", header: "Attention", cell: ({ getValue }) => <span className={`badge ${String(getValue()).toLowerCase().replaceAll(" ", "-")}`}>{String(getValue())}</span> },
];
const retailColumns: ColumnDef<InventoryPackage>[] = [
  ...baseColumns.slice(0, 5),
  { accessorKey: "available", header: "On hand", cell: ({ row }) => `${row.original.available.toLocaleString()} ${row.original.unit}` },
  { accessorKey: "sold_30d", header: "30d sold", cell: ({ getValue }) => Number(getValue()).toLocaleString() },
  { accessorKey: "days_on_hand", header: "DOH", cell: ({ getValue }) => getValue() == null ? "—" : Number(getValue()).toFixed(1) },
  { accessorKey: "margin_pct", header: "Margin", cell: ({ getValue }) => getValue() == null ? "—" : `${Number(getValue()).toFixed(1)}%` },
  baseColumns[baseColumns.length - 1],
];
const views = [["all", "All Material"], ["production-ready", "Production Ready"], ["low-balance", "Low Balance"], ["hold", "Quarantine / Hold"]] as const;

export function InventoryPage({ initialOperation="retail", initialAudits=false }: { initialOperation?:"retail"|"production"; initialAudits?:boolean } = {}) {
  const account = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<{ capabilities: { retail: boolean; production: boolean; cultivation: boolean } }>("/api/v1/account/context", signal) });
  const [operation, setOperation] = useState<"retail" | "production">(initialOperation);
  const [grain, setGrain] = useState<"packages" | "plants">("packages"); const [receiving, setReceiving] = useState(false); const [showHistory, setShowHistory] = useState(false); const [selected, setSelected] = useState<InventoryPackage | null>(null); const [adjusting, setAdjusting] = useState(false); const [showAudits, setShowAudits] = useState(initialAudits); const [showLineage, setShowLineage] = useState(false); const [search, setSearch] = useState(""); const [view, setView] = useState("all"); const [status, setStatus] = useState(""); const [materialType, setMaterialType] = useState(""); const [location, setLocation] = useState("");
  const inventory = useInventory({ operation, search, view, status, materialType, location }); const data = inventory.data?.items ?? []; const tableColumns = useMemo(() => operation === "retail" ? retailColumns : baseColumns, [operation]); const table = useReactTable({ data, columns: tableColumns, getCoreRowModel: getCoreRowModel() }); const summary = inventory.data?.summary; const facets = inventory.data?.facets;
  const retailEnabled = account.data?.capabilities.retail ?? true; const productionEnabled = account.data?.capabilities.production ?? true; const cultivationEnabled = account.data?.capabilities.cultivation ?? false;
  useEffect(() => { if (account.data && operation === "production" && !productionEnabled && retailEnabled) setOperation("retail"); if (account.data && operation === "retail" && !retailEnabled && productionEnabled) setOperation("production"); if (!cultivationEnabled && grain === "plants") setGrain("packages"); }, [account.data, cultivationEnabled, grain, operation, productionEnabled, retailEnabled]);
  return <div className="page">
    <div className="operation-switch" role="group" aria-label="Inventory operation">{retailEnabled ? <button className={operation === "retail" ? "active" : ""} onClick={() => { setOperation("retail"); setGrain("packages"); }}>Retail Ops</button> : null}{productionEnabled ? <button className={operation === "production" ? "active" : ""} onClick={() => setOperation("production")}>Production Ops</button> : null}</div>
    {operation === "production" && cultivationEnabled ? <div className="view-tabs grain-tabs"><button className={grain === "packages" ? "active" : ""} onClick={() => setGrain("packages")}>Packages</button><button className={grain === "plants" ? "active" : ""} onClick={() => setGrain("plants")}>Plants</button></div> : null}
    <div className="page-heading"><div><div className="eyebrow">{operation === "retail" ? "Retail Ops" : "Production Ops"}</div><h1>Inventory</h1><p>{operation === "retail" ? "Sellable products from the durable package ledger." : "Bulk cannabis material by durable package and lot."}</p></div>{grain === "packages" ? <div className="heading-actions"><button className="secondary" disabled={!selected} onClick={() => setShowLineage(true)}>Package 360</button><button className="secondary" onClick={() => setShowAudits(true)}>Audits</button><button className="secondary" disabled={!selected} onClick={() => setAdjusting(true)}>Adjust</button><button className="secondary" onClick={() => setShowHistory(true)}>Receive history</button><button className="primary" onClick={() => setReceiving(true)}>Receive</button></div> : null}</div>
    {grain === "plants" && operation === "production" ? <section className="inventory-panel plant-panel"><PlantInventory /></section> : <><section className="metrics"><Metric label="Packages" value={summary?.package_count ?? "—"} /><Metric label="Available quantity" value={summary ? summary.available_quantity.toLocaleString() : "—"} /><Metric label="Reserved quantity" value={summary ? summary.reserved_quantity.toLocaleString() : "—"} /><Metric label="On hold" value={summary?.hold_count ?? "—"} warning /></section></>}
    <div className="view-tabs">{views.map(([key, label]) => <button key={key} className={view === key ? "active" : ""} onClick={() => setView(key)}>{label}</button>)}</div>
    <section className="inventory-panel"><div className="filters"><label className="search"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search material, package, lot, SKU…" /></label><Filter label="Status" value={status} values={facets?.statuses} onChange={setStatus} /><Filter label="Material type" value={materialType} values={facets?.material_types} onChange={setMaterialType} /><Filter label="Location" value={location} values={facets?.locations} onChange={setLocation} /></div>{inventory.isError ? <div className="state error">{inventory.error.message}</div> : null}{inventory.isLoading ? <div className="state">Loading durable inventory…</div> : null}{!inventory.isLoading && !inventory.isError ? <div className="table-wrap"><table><thead>{table.getHeaderGroups().map(group => <tr key={group.id}>{group.headers.map(header => <th key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}</thead><tbody>{table.getRowModel().rows.map(row => <tr key={row.id} className={selected?.id === row.original.id ? "selected-row" : ""} onClick={() => setSelected(row.original)}>{row.getVisibleCells().map(cell => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody></table>{data.length === 0 ? <div className="empty">No packages match these filters.</div> : null}</div> : null}</section>
    {receiving ? <ReceiveInventory operation={operation} onClose={() => setReceiving(false)} /> : null}{showHistory ? <ReceiveHistory operation={operation} onClose={() => setShowHistory(false)} /> : null}{adjusting && selected ? <AdjustInventory operation={operation} item={selected} onClose={() => setAdjusting(false)} /> : null}{showAudits ? <InventoryAudits operation={operation} onClose={() => setShowAudits(false)} /> : null}{showLineage && selected ? <PackageLineage operation={operation} item={selected} onClose={() => setShowLineage(false)} /> : null}
  </div>;
}
function Metric({ label, value, warning = false }: { label: string; value: string | number; warning?: boolean }) { return <article className={warning ? "metric warning" : "metric"}><span>{label}</span><strong>{value}</strong></article>; }
function Filter({ label, value, values = [], onChange }: { label: string; value: string; values?: string[]; onChange: (value: string) => void }) { return <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}><option value="">All {label.toLowerCase()}s</option>{values.map(item => <option key={item}>{item}</option>)}</select>; }
