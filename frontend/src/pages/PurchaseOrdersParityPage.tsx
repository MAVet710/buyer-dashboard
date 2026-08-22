import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { apiDownload, apiGet, apiPost, downloadBlob } from "../lib/api";

type Row = Record<string, unknown>;
type Workspace = {
  controls: { target_doh: number; velocity_adjustment: number; sales_days: number; sku_window: number };
  reorder_asap: Row[];
  inventory: Row[];
  smart_priorities: Row[];
};
type POLine = { sku: string; description: string; strain: string; size: string; quantity: number; price: number };
type Review = {
  sku: string; description: string; requested_quantity: number; matched_product: string; matched_sku: string;
  on_hand: number; days_of_supply: number; inventory_status: string; match_score: number; match_method: string;
  review: boolean; review_reason: string;
};

export function PurchaseOrdersParityPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const [targetDoh, setTargetDoh] = useState(21);
  const [velocity, setVelocity] = useState(0.5);
  const [salesDays, setSalesDays] = useState(60);
  const [skuWindow, setSkuWindow] = useState(56);
  const [items, setItems] = useState<POLine[]>([]);
  const [draft, setDraft] = useState<POLine>({ sku: "", description: "", strain: "", size: "", quantity: 1, price: 0 });
  const [review, setReview] = useState<Review[]>([]);
  const [store, setStore] = useState({ name: "Cannabis Store", address: "123 Main St\nCity, State 12345", phone: "", contact: "" });
  const [vendor, setVendor] = useState({ name: "", license: "", address: "", contact: "" });
  const [po, setPo] = useState({ number: `PO-${new Date().toISOString().slice(0, 10).replaceAll("-", "")}`, date: new Date().toISOString().slice(0, 10), terms: "", notes: "" });
  const [taxRate, setTaxRate] = useState(0); const [discount, setDiscount] = useState(0); const [shipping, setShipping] = useState(0);
  const params = useMemo(() => new URLSearchParams({ target_doh: String(targetDoh), velocity_adjustment: String(velocity), sales_days: String(salesDays), sku_window: String(skuWindow) }), [targetDoh, velocity, salesDays, skuWindow]);
  const data = useQuery({ queryKey: ["po-parity", params.toString()], queryFn: ({ signal }) => apiGet<Workspace>(`/api/v1/po-parity/workspace?${params}`, signal) });
  const crossCheck = useMutation({ mutationFn: () => apiPost<Review[]>(`/api/v1/po-parity/review?${params}`, { items }), onSuccess: setReview });
  const subtotal = items.reduce((sum, item) => sum + item.quantity * item.price, 0);
  const tax = subtotal * taxRate / 100; const total = subtotal + tax - discount + shipping;

  const addLine = (line: POLine) => setItems(current => [...current, { ...line, quantity: Math.max(0.01, Number(line.quantity) || 1), price: Math.max(0, Number(line.price) || 0) }]);
  const addAllReorder = () => {
    const rows = data.data?.reorder_asap ?? [];
    setItems(current => {
      const existing = new Set(current.map(item => `${item.description}|${item.size}|${item.strain}`.toLowerCase()));
      const additions = rows.map(row => {
        const description = String(row.top_products || row.product_name || `${row.subcategory || ""} ${row.strain_type || ""} ${row.packagesize || ""}`).split(",")[0].trim();
        const rawCost = Number(row.unit_cost || 0);
        return { sku: String(row.sku || ""), description, strain: String(row.strain_type || ""), size: String(row.packagesize || ""), quantity: Math.max(1, Number(row.reorderqty || 1)), price: rawCost > 0 ? rawCost / 2 : 0 } as POLine;
      }).filter(item => item.description && !existing.has(`${item.description}|${item.size}|${item.strain}`.toLowerCase()));
      return [...current, ...additions];
    });
    setReview([]);
  };
  const applySmartPriorities = () => {
    const priorities = data.data?.smart_priorities ?? [];
    setItems(current => {
      const existing = new Set(current.map(item => item.description.toLowerCase()));
      const additions: POLine[] = [];
      priorities.slice(0, 25).forEach(row => {
        const description = String(row["Need"] || row.product_name || row.need || "").trim();
        const qty = Number(row["Recommended units"] || row.recommended_units || row.recommended_quantity || 0);
        if (description && qty > 0 && !existing.has(description.toLowerCase())) additions.push({ sku: String(row.sku || ""), description, strain: String(row.strain_type || ""), size: String(row.package_size || row.packagesize || ""), quantity: qty, price: Number(row.unit_cost || 0) });
      });
      return [...current, ...additions];
    });
    setReview([]);
  };
  const pdfPayload = { store_name: store.name, store_address: store.address, store_phone: store.phone, store_contact: store.contact, vendor_name: vendor.name, vendor_license: vendor.license, vendor_address: vendor.address, vendor_contact: vendor.contact, po_number: po.number, po_date: po.date, terms: po.terms, fulfillment_notes: po.notes, tax_rate: taxRate, discount, shipping, items };
  const downloadPdf = async () => { const blob = await apiDownload("/api/v1/po-parity/pdf", pdfPayload); downloadBlob(blob, `${po.number || "purchase-order"}.pdf`); };

  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">Retail Ops · Streamlit parity</div><h1>Purchase Order Builder</h1><p>Create professional purchase orders from the same Buyer Dashboard reorder logic, with manual entry, inventory cross-checks, smart recommendations, totals and PDF export.</p></div><button className="secondary" onClick={() => onNavigate("Buying Budget")}>Open Buying Budget</button></div>
    <section className="inventory-panel parity-controls">
      <Num label="Target Days on Hand" value={targetDoh} onChange={setTargetDoh} min={1}/><Num label="Velocity Adjustment" value={velocity} onChange={setVelocity} min={0.01} step={0.01}/><Num label="Days in Sales Period" value={salesDays} onChange={setSalesDays} min={7}/><label>SKU Velocity Window<select value={skuWindow} onChange={e => setSkuWindow(Number(e.target.value))}>{[14,28,56,84].map(v => <option value={v} key={v}>{v} days</option>)}</select></label>
    </section>
    {data.isError ? <div className="state error">{data.error.message}</div> : null}{data.isLoading ? <div className="state">Loading purchase-order context…</div> : null}
    <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Inventory Dashboard cross-reference</div><h2>Reorder ASAP</h2><p>{data.data?.reorder_asap.length ?? 0} line(s) currently flagged from the Buyer Operations forecast.</p></div><button className="primary" disabled={!data.data?.reorder_asap.length} onClick={addAllReorder}>Add All Reorder ASAP Lines to PO</button></div><Table rows={data.data?.reorder_asap ?? []} columns={["subcategory","strain_type","packagesize","onhandunits","avgunitsperday","daysonhand","reorderqty","top_products"]}/></section>

    <div className="two-column-grid">
      <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Original manual workflow</div><h2>Add PO Item</h2></div></div><div className="form-grid"><Text label="SKU" value={draft.sku} onChange={value => setDraft({ ...draft, sku: value })}/><Text label="Description" value={draft.description} onChange={value => setDraft({ ...draft, description: value })}/><Text label="Strain" value={draft.strain} onChange={value => setDraft({ ...draft, strain: value })}/><Text label="Size" value={draft.size} onChange={value => setDraft({ ...draft, size: value })}/><Num label="Quantity" value={draft.quantity} onChange={value => setDraft({ ...draft, quantity: value })} min={0.01}/><Num label="Price" value={draft.price} onChange={value => setDraft({ ...draft, price: value })} min={0} step={0.01}/></div><button className="primary submit" disabled={!draft.description.trim()} onClick={() => { addLine(draft); setDraft({ sku: "", description: "", strain: "", size: "", quantity: 1, price: 0 }); }}>Add Item</button></section>
      <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Smart PO</div><h2>Doobie-supported priorities</h2><p>Deterministic Buyer Dash evidence stays underneath the recommendation layer.</p></div></div><Table rows={data.data?.smart_priorities ?? []} columns={["Need","Recommended units","Current on hand","Days of cover","Units sold","SKUs","Reason"]}/><div className="heading-actions"><button className="secondary" disabled={!data.data?.smart_priorities.length} onClick={applySmartPriorities}>Add Smart Recommendations</button><button className="primary" onClick={() => onNavigate("Doobie")}>Open Doobie</button></div></section>
    </div>

    <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Current Items</div><h2>PO Lines</h2></div><div className="heading-actions"><button className="secondary" disabled={!items.length} onClick={() => crossCheck.mutate()}>Inventory Cross-Check</button><button className="secondary" disabled={!items.length} onClick={() => { setItems([]); setReview([]); }}>Clear All Items</button></div></div><div className="table-wrap"><table><thead><tr><th>SKU</th><th>Description</th><th>Strain</th><th>Size</th><th>Quantity</th><th>Price</th><th>Total</th><th>Inventory</th><th></th></tr></thead><tbody>{items.map((item,index) => { const check = review[index]; return <tr key={`${index}-${item.description}`}><td><input className="table-input" value={item.sku} onChange={e => patchLine(index, "sku", e.target.value, items, setItems, setReview)}/></td><td><input className="table-input wide" value={item.description} onChange={e => patchLine(index, "description", e.target.value, items, setItems, setReview)}/></td><td><input className="table-input" value={item.strain} onChange={e => patchLine(index, "strain", e.target.value, items, setItems, setReview)}/></td><td><input className="table-input" value={item.size} onChange={e => patchLine(index, "size", e.target.value, items, setItems, setReview)}/></td><td><input className="table-quantity" type="number" min="0.01" value={item.quantity} onChange={e => patchLine(index, "quantity", Number(e.target.value), items, setItems, setReview)}/></td><td><input className="table-quantity" type="number" min="0" step="0.01" value={item.price} onChange={e => patchLine(index, "price", Number(e.target.value), items, setItems, setReview)}/></td><td>{money(item.quantity * item.price)}</td><td>{check ? <span className={check.review ? "badge hold" : "badge production-ready"} title={check.review_reason}>{check.matched_product || "No match"}<br/><small>{check.on_hand.toLocaleString()} on hand · {check.review_reason}</small></span> : "Not checked"}</td><td><button className="link-button" onClick={() => { setItems(items.filter((_,i) => i !== index)); setReview([]); }}>Remove</button></td></tr>})}</tbody></table>{items.length === 0 ? <div className="empty">No items on this purchase order yet.</div> : null}</div></section>

    <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Order Information</div><h2>Purchase Order Details</h2></div></div><div className="form-grid three"><Text label="Store Name" value={store.name} onChange={name => setStore({ ...store, name })}/><Area label="Store Address" value={store.address} onChange={address => setStore({ ...store, address })}/><Text label="Store Phone" value={store.phone} onChange={phone => setStore({ ...store, phone })}/><Text label="Store Contact" value={store.contact} onChange={contact => setStore({ ...store, contact })}/><Text label="Vendor Name" value={vendor.name} onChange={name => setVendor({ ...vendor, name })}/><Text label="Vendor License" value={vendor.license} onChange={license => setVendor({ ...vendor, license })}/><Area label="Vendor Address" value={vendor.address} onChange={address => setVendor({ ...vendor, address })}/><Text label="Vendor Contact" value={vendor.contact} onChange={contact => setVendor({ ...vendor, contact })}/><Text label="PO Number" value={po.number} onChange={number => setPo({ ...po, number })}/><label>PO Date<input type="date" value={po.date} onChange={e => setPo({ ...po, date: e.target.value })}/></label><Text label="Terms" value={po.terms} onChange={terms => setPo({ ...po, terms })}/><Area label="Fulfillment Notes" value={po.notes} onChange={notes => setPo({ ...po, notes })}/></div></section>

    <section className="inventory-panel"><div className="section-heading"><div><div className="eyebrow">Totals</div><h2>Order Total</h2></div></div><div className="form-grid"><Num label="Tax Rate (%)" value={taxRate} onChange={setTaxRate} min={0} step={0.1}/><Num label="Discount ($)" value={discount} onChange={setDiscount} min={0} step={1}/><Num label="Shipping ($)" value={shipping} onChange={setShipping} min={0} step={1}/></div><div className="po-total-stack"><span>Subtotal <strong>{money(subtotal)}</strong></span>{taxRate > 0 ? <span>Tax ({taxRate}%) <strong>{money(tax)}</strong></span> : null}{discount > 0 ? <span>Discount <strong>-{money(discount)}</strong></span> : null}{shipping > 0 ? <span>Shipping <strong>{money(shipping)}</strong></span> : null}<span className="grand-total">Total <strong>{money(total)}</strong></span></div><button className="primary submit" disabled={!items.length} onClick={downloadPdf}>Generate & Download PDF</button></section>
  </div>;
}

function patchLine<K extends keyof POLine>(index:number,key:K,value:POLine[K],items:POLine[],setItems:(rows:POLine[])=>void,setReview:(rows:Review[])=>void){const next=items.map((item,i)=>i===index?{...item,[key]:value}:item);setItems(next);setReview([])}
function Text({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}){return <label>{label}<input value={value} onChange={e=>onChange(e.target.value)}/></label>}
function Area({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}){return <label>{label}<textarea value={value} onChange={e=>onChange(e.target.value)}/></label>}
function Num({label,value,onChange,min=0,step=1}:{label:string;value:number;onChange:(value:number)=>void;min?:number;step?:number}){return <label>{label}<input type="number" min={min} step={step} value={value} onChange={e=>onChange(Number(e.target.value))}/></label>}
function money(value:number){return value.toLocaleString(undefined,{style:"currency",currency:"USD",minimumFractionDigits:2,maximumFractionDigits:2})}
function show(value:unknown){if(value==null||value==="")return"—";if(typeof value==="number")return Number.isInteger(value)?value.toLocaleString():value.toLocaleString(undefined,{maximumFractionDigits:2});return String(value)}
function head(value:string){return value.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase())}
function Table({rows,columns}:{rows:Row[];columns:string[]}){const visible=columns.filter(column=>rows.some(row=>row[column]!==undefined));return <div className="table-wrap compact-table"><table><thead><tr>{visible.map(column=><th key={column}>{head(column)}</th>)}</tr></thead><tbody>{rows.slice(0,100).map((row,index)=><tr key={index}>{visible.map(column=><td key={column}>{show(row[column])}</td>)}</tr>)}</tbody></table>{rows.length===0?<div className="empty">No rows available.</div>:null}</div>}
