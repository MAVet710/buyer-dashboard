import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { apiDownload, apiGet, apiPost, downloadBlob } from "../lib/api";
import { purchaseDraftSelection, STAGED_PO_KEY, validPurchaseDraft, type PurchaseDraftLine, type PurchaseProduct } from "../lib/purchaseOrderContinuity";

const LegacyPdfBuilder = lazy(() => import("./PurchaseOrdersParityPage").then(module => ({ default: module.PurchaseOrdersParityPage })));
type Account = { user: { role: string }; organization: { id: string; name: string }; facility_id: string; facilities: Array<{ id: string; name: string }> };
type Planning = { recommendations: PurchaseProduct[]; vendors: Array<{ id: string; name: string; license_or_registration: string; payment_terms: string }> };
type SavedOrder = { id: string; order_number: string; status: string; order_date: string; due_at: string | null; currency: string; notes: string; partner_name?: string };
type OrderPage = { items: SavedOrder[]; total: number; has_more: boolean };
type OrderDetail = { order: SavedOrder; lines: Array<PurchaseDraftLine & { id: string; sku_snapshot: string; fulfilled_quantity: number }>; vendor_name: string; facility_name: string; total: string };
const BUY_ROLES = new Set(["dev", "admin", "supervisor", "buyer"]);

function localDate(): string { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${String(now.getDate()).padStart(2,"0")}`; }
function newOrderNumber(): string { return `PO-${localDate().replaceAll("-", "")}-${crypto.randomUUID().slice(0,8).toUpperCase()}`; }
function readStaged(): unknown { try { return JSON.parse(sessionStorage.getItem(STAGED_PO_KEY) || "null"); } catch { return null; } }
function money(value: number | string): string { return Number(value).toLocaleString(undefined, { style: "currency", currency: "USD" }); }

export function PurchaseOrdersWorkspacePage({ onNavigate }: { onNavigate: (page: string) => void }) {
  const account = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<Account>("/api/v1/account/context", signal) });
  if (account.isLoading) return <div className="state">Loading purchasing context…</div>;
  if (account.isError || !account.data) return <div className="state error">Purchasing context is unavailable. {account.error?.message}</div>;
  return <PurchaseOrdersWorkspace key={`${account.data.organization.id}:${account.data.facility_id}:${account.data.user.role}`} account={account.data} onNavigate={onNavigate} />;
}

function PurchaseOrdersWorkspace({ account, onNavigate }: { account: Account; onNavigate: (page: string) => void }) {
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const selectedId = params.get("po") ?? "";
  const scope = [account.organization.id, account.facility_id];
  const canWrite = BUY_ROLES.has(account.user.role);
  const [legacy, setLegacy] = useState(false);
  const [staged] = useState(readStaged);
  const stagedApplied = useRef(false);
  const [editing, setEditing] = useState(Boolean(staged) && !selectedId);
  const [lines, setLines] = useState<PurchaseDraftLine[]>([]);
  const [vendorId, setVendorId] = useState("");
  const [orderNumber, setOrderNumber] = useState(newOrderNumber);
  const [orderDate, setOrderDate] = useState(localDate);
  const [dueDate, setDueDate] = useState("");
  const [notes, setNotes] = useState("");
  const [productId, setProductId] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [selectionNotice, setSelectionNotice] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const planning = useQuery({ queryKey: ["purchasing", ...scope], queryFn: ({ signal }) => apiGet<Planning>("/api/v1/purchasing/workspace", signal), enabled: canWrite && editing });
  const historyParams = new URLSearchParams({ search, offset: String(offset), limit: "50" });
  const history = useQuery({ queryKey: ["purchase-order-history", ...scope, historyParams.toString()], queryFn: ({ signal }) => apiGet<OrderPage>(`/api/v1/purchasing/purchase-orders?${historyParams}`, signal), enabled: !legacy });
  const detail = useQuery({ queryKey: ["purchase-order-detail", ...scope, selectedId], queryFn: ({ signal }) => apiGet<OrderDetail>(`/api/v1/purchasing/purchase-orders/${encodeURIComponent(selectedId)}`, signal), enabled: Boolean(selectedId) && !legacy, retry: false });
  useEffect(() => {
    if (stagedApplied.current || !planning.data || !staged) return;
    stagedApplied.current = true;
    const result = purchaseDraftSelection(staged, planning.data.recommendations);
    setLines(result.lines);
    setSelectionNotice(`${result.lines.length} selected product(s) carried into this draft. Product identities, units and starting prices were checked against the current facility. ${result.rejected ? `${result.rejected} unavailable or invalid selection(s) were not imported. ` : ""}${result.duplicates ? `${result.duplicates} repeated product selection(s) were included only once; review quantities. ` : ""}Review all quantities and quoted prices before saving.`);
  }, [planning.data, staged]);
  useEffect(() => { setReviewed(false); }, [lines, vendorId, orderNumber, orderDate, dueDate, notes]);
  const open = (id: string) => { setEditing(false); setParams(previous => { const next = new URLSearchParams(previous); if (id) next.set("po", id); else next.delete("po"); return next; }); };
  const refresh = () => Promise.all([client.invalidateQueries({ queryKey: ["purchase-order-history"] }), client.invalidateQueries({ queryKey: ["purchase-order-detail"] }), client.invalidateQueries({ queryKey: ["purchasing"] }), client.invalidateQueries({ queryKey: ["home-summary"] }), client.invalidateQueries({ queryKey: ["operations-inbox"] })]);
  const save = useMutation({
    mutationFn: () => {
      if (!canWrite || !reviewed || !vendorId || !validPurchaseDraft(lines)) throw new Error("Review the vendor, facility and valid order lines before saving.");
      return apiPost<{ id: string }>("/api/v1/purchasing/purchase-orders", { vendor_id: vendorId, order_number: orderNumber.trim(), order_date: orderDate, due_date: dueDate || null, notes, lines: lines.map(({ product_id, description, quantity, unit, unit_price }) => ({ product_id, description, quantity, unit, unit_price })) });
    },
    onSuccess: async result => { sessionStorage.removeItem(STAGED_PO_KEY); open(result.id); await refresh(); },
  });
  const confirm = useMutation({ mutationFn: () => apiPost(`/api/v1/purchasing/purchase-orders/${encodeURIComponent(selectedId)}/confirm`, {}), onSuccess: refresh });
  const pdf = useMutation({ mutationFn: () => apiDownload(`/api/v1/purchasing/purchase-orders/${encodeURIComponent(selectedId)}/pdf`), onSuccess: blob => downloadBlob(blob, `PO_${detail.data?.order.order_number.replace(/[^A-Za-z0-9._-]/g,"-") || selectedId}.pdf`) });
  const begin = () => { open(""); setEditing(true); setLines([]); setVendorId(""); setNotes(""); setDueDate(""); setOrderDate(localDate()); setOrderNumber(newOrderNumber()); setSelectionNotice(""); save.reset(); };
  const addProduct = () => { const product = planning.data?.recommendations.find(row => row.product_id === productId); if (!product || lines.some(line => line.product_id === product.product_id)) return; setLines(current => [...current, { product_id: product.product_id, sku: product.sku, description: product.product_name, quantity: Math.max(1, product.suggested_quantity || 1), unit: product.unit, unit_price: product.unit_cost }]); setProductId(""); };
  const facilityName = account.facilities.find(row => row.id === account.facility_id)?.name || account.facility_id;
  const estimatedTotal = lines.reduce((sum, line) => sum + Math.round(line.quantity * line.unit_price * 100) / 100, 0);
  return <div className="page purchase-orders-workspace">
    <div className="page-heading"><div><div className="eyebrow">BUYING · PURCHASE ORDERS</div><h1>Purchase Orders</h1><p>Save, reopen and confirm purchase orders in the existing commercial ledger. PDFs are generated from the saved order.</p><span className="source-caption">{account.organization.name} · {facilityName}</span></div>{canWrite && !legacy ? <button className="primary" type="button" disabled={save.isPending} onClick={begin}>New purchase order</button> : null}</div>
    <div className="view-tabs"><button type="button" className={!legacy?"active":""} onClick={() => setLegacy(false)}>Saved purchase orders</button><button type="button" className={legacy?"active":""} onClick={() => setLegacy(true)}>Legacy PDF tool</button><button type="button" onClick={() => onNavigate("Replenishment Policies")}>Planning settings</button></div>
    {legacy ? <><div className="warning-banner">This retained compatibility tool exports standalone PDFs. It does not save or confirm a purchase order. Use Saved purchase orders for operational purchasing.</div><Suspense fallback={<div className="state">Loading legacy PDF tool…</div>}><LegacyPdfBuilder onNavigate={onNavigate} /></Suspense></> : <>
      {editing && canWrite ? <section className="inventory-panel">
        <h2>Draft purchase order</h2>{selectionNotice ? <div className="info-banner">{selectionNotice}</div> : null}
        {planning.isLoading ? <div className="state">Loading authorized products and vendors…</div> : null}{planning.isError ? <div className="state error">{planning.error.message}</div> : null}
        <div className="form-grid"><label>Vendor<select value={vendorId} onChange={event => setVendorId(event.target.value)}><option value="">Select a vendor</option>{planning.data?.vendors.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>PO number<input value={orderNumber} maxLength={64} onChange={event => setOrderNumber(event.target.value)} /></label><label>Order date<input type="date" value={orderDate} onChange={event => setOrderDate(event.target.value)} /></label><label>Requested delivery<input type="date" value={dueDate} onChange={event => setDueDate(event.target.value)} /></label><label>Notes<textarea value={notes} onChange={event => setNotes(event.target.value)} /></label></div>
        <div className="inline-form"><label>Product<select aria-label="Add purchase-order product" value={productId} onChange={event => setProductId(event.target.value)}><option value="">Choose product</option>{planning.data?.recommendations.filter(row => !lines.some(line => line.product_id === row.product_id)).map(row => <option key={row.product_id} value={row.product_id}>{row.product_name} · {row.sku}</option>)}</select></label><button className="secondary" type="button" disabled={!productId || lines.length >= 500} onClick={addProduct}>Add product</button></div>
        <div className="table-wrap"><table><thead><tr><th>Product</th><th>Quantity</th><th>Unit</th><th>Quoted unit price</th><th>Estimated total</th><th>Remove</th></tr></thead><tbody>{lines.map(line => <tr key={line.product_id}><td>{line.description}<br /><small>{line.sku}</small></td><td><input type="number" min="0" step="any" aria-label={`Quantity for ${line.sku}`} value={line.quantity} onChange={event => setLines(current => current.map(value => value.product_id === line.product_id ? { ...value, quantity: Number(event.target.value) } : value))} /></td><td>{line.unit}</td><td><input type="number" min="0" step="0.01" aria-label={`Price for ${line.sku}`} value={line.unit_price} onChange={event => setLines(current => current.map(value => value.product_id === line.product_id ? { ...value, unit_price: Number(event.target.value) } : value))} /></td><td>{money(line.quantity * line.unit_price)}</td><td><button className="secondary" type="button" onClick={() => setLines(current => current.filter(value => value.product_id !== line.product_id))}>Remove</button></td></tr>)}</tbody></table></div>
        <p>Estimated draft total: <strong>{money(estimatedTotal)}</strong>. The saved record and its PDF use the server-calculated total.</p>
        <label className="toggle"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />I reviewed the facility, vendor, units, quantities and quoted prices. A zero price is intentional, not a missing quote.</label>
        <button className="primary" type="button" disabled={!reviewed || !vendorId || !orderNumber.trim() || !orderDate || !validPurchaseDraft(lines) || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving draft…" : "Save draft purchase order"}</button>
        {save.isError ? <div className="form-error">{save.error.message}<p>After a connection or server failure, refresh saved orders and search for {orderNumber} before retrying. Do not create a new order number to work around an uncertain response.</p></div> : null}
      </section> : null}
      {selectedId ? <section className="inventory-panel"><h2>Saved purchase order</h2>{detail.isLoading ? <div className="state">Loading saved order…</div> : null}{detail.isError ? <div className="state error">{detail.error.message}</div> : null}{detail.data ? <><h3>{detail.data.order.order_number} · {detail.data.order.status}</h3><p>{detail.data.vendor_name} · {detail.data.facility_name}</p><div className="table-wrap"><table><thead><tr><th>SKU / product</th><th>Ordered</th><th>Received</th><th>Unit</th><th>Unit price</th></tr></thead><tbody>{detail.data.lines.map(line => <tr key={line.id}><td>{line.sku_snapshot} · {line.description}</td><td>{line.quantity}</td><td>{line.fulfilled_quantity}</td><td>{line.unit}</td><td>{money(line.unit_price)}</td></tr>)}</tbody></table></div><p>Saved total ({detail.data.order.currency}): <strong>{detail.data.total}</strong></p><p>{detail.data.order.notes}</p><div className="heading-actions"><button className="primary" type="button" disabled={pdf.isPending} onClick={() => pdf.mutate()}>Download saved PO PDF</button>{canWrite && detail.data.order.status === "draft" ? <button className="secondary" type="button" disabled={confirm.isPending} onClick={() => { if (window.confirm(`Confirm purchase order ${detail.data!.order.order_number} for ${facilityName}? This records committed inbound inventory.`)) confirm.mutate(); }}>Approve &amp; confirm</button> : null}<button className="secondary" type="button" onClick={() => open("")}>Close order</button></div></> : null}{pdf.isError ? <div className="form-error">{pdf.error.message}</div> : null}{confirm.isError ? <div className="form-error">{confirm.error.message}</div> : null}</section> : null}
      <section className="inventory-panel"><h2>Saved orders</h2><div className="inline-form"><label>Find order or vendor<input aria-label="Search saved purchase orders" value={search} onChange={event => { setSearch(event.target.value); setOffset(0); }} maxLength={160} /></label><button className="secondary" type="button" onClick={() => void history.refetch()}>Refresh saved orders</button></div>{history.isLoading ? <div className="state">Loading saved orders…</div> : null}{history.isError ? <div className="state error">{history.error.message}</div> : null}{history.data ? <><p>{history.data.total} purchase order(s)</p><div className="table-wrap"><table><thead><tr><th>PO</th><th>Vendor</th><th>Status</th><th>Ordered</th><th>Due</th><th>Open</th></tr></thead><tbody>{history.data.items.map(order => <tr key={order.id}><td>{order.order_number}</td><td>{order.partner_name}</td><td>{order.status}</td><td>{order.order_date}</td><td>{order.due_at || "Not set"}</td><td><button className="secondary" type="button" onClick={() => open(order.id)}>Open saved PO</button></td></tr>)}</tbody></table>{!history.data.items.length ? <div className="empty">No saved purchase orders match.</div> : null}</div><div className="heading-actions"><button className="secondary" type="button" disabled={offset===0 || history.isFetching} onClick={() => setOffset(value => Math.max(0,value-50))}>Previous</button><button className="secondary" type="button" disabled={!history.data.has_more || history.isFetching} onClick={() => setOffset(value => value+50)}>Next</button></div></> : null}</section>
    </>}
  </div>;
}
