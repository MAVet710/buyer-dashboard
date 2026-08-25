import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiPublicGet, apiPublicPost } from "../lib/api";
import { BRAND_IMAGE_URL } from "../lib/brand";

type CatalogItem = {
  product_id: string;
  sku: string;
  name: string;
  unit: string;
  available: number;
  price_usd: number;
};
type Catalog = {
  partner: { id: string; name: string; payment_terms: string };
  facility_id: string;
  catalog: CatalogItem[];
};
type OrderResult = { order_id: string; order_number: string; status: string };

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function CommercePortalPage({ token }: { token: string }) {
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [poReference, setPoReference] = useState("");
  const [deliveryDate, setDeliveryDate] = useState("");
  const [notes, setNotes] = useState("");
  const catalog = useQuery({
    queryKey: ["commerce-portal", token],
    queryFn: ({ signal }) => apiPublicGet<Catalog>(`/api/v1/commerce-portal/${encodeURIComponent(token)}`, signal),
    retry: false,
  });
  const lines = useMemo(() => (catalog.data?.catalog ?? []).map(item => ({ item, quantity: Math.max(0, Number(quantities[item.product_id] ?? 0)) })).filter(row => row.quantity > 0), [catalog.data, quantities]);
  const subtotal = lines.reduce((sum, row) => sum + row.quantity * row.item.price_usd, 0);
  const order = useMutation({
    mutationFn: () => apiPublicPost<OrderResult>(`/api/v1/commerce-portal/${encodeURIComponent(token)}/orders`, {
      lines: lines.map(row => ({ product_id: row.item.product_id, quantity: row.quantity })),
      requested_delivery_date: deliveryDate || null,
      purchase_order_reference: poReference,
      notes,
    }),
    onSuccess: () => setQuantities({}),
  });

  if (catalog.isLoading) return <div className="marketing-page"><div className="state">Loading your wholesale catalog…</div></div>;
  if (catalog.isError) return <div className="marketing-page"><section className="marketing-section"><div className="warning-banner"><strong>Retailer access is unavailable.</strong><br/>{catalog.error.message}</div></section></div>;
  const data = catalog.data!;
  return <div className="marketing-page commerce-portal-page">
    <header className="marketing-nav-wrap"><nav className="marketing-nav" aria-label="DoobieCommerce retailer portal"><div className="marketing-brand"><img className="marketing-brand-image" src={BRAND_IMAGE_URL} alt="DoobieLogic"/><span className="marketing-wordmark"><strong>Doobie</strong><em>Logic</em></span></div><div className="marketing-eyebrow">DoobieCommerce · Retailer Portal</div></nav></header>
    <main className="marketing-section">
      <section className="marketing-section-heading compact"><div className="marketing-eyebrow">PRIVATE WHOLESALE CATALOG</div><h1>{data.partner.name || "Retail Partner"}</h1><p>Live available inventory and your negotiated pricing. Payment terms: <strong>{data.partner.payment_terms || "Per agreement"}</strong>.</p></section>
      {order.data ? <div className="success-banner"><strong>Order {order.data.order_number} received.</strong><br/>It entered the supplier's DoobieLogic Commercial Ops queue as {order.data.status}.</div> : null}
      {order.isError ? <div className="warning-banner"><strong>Order could not be submitted.</strong><br/>{order.error.message}</div> : null}
      <div className="two-column-grid commerce-portal-layout">
        <section className="inventory-panel"><div className="eyebrow">AVAILABLE NOW</div><h2>Wholesale catalog</h2>{!data.catalog.length ? <div className="info-banner">No products are currently available for ordering.</div> : <div className="table-wrap"><table><thead><tr><th>Product</th><th>Available</th><th>Your price</th><th>Order qty</th></tr></thead><tbody>{data.catalog.map(item => <tr key={item.product_id}><td><strong>{item.name}</strong><br/><small>{item.sku}</small></td><td>{item.available.toLocaleString()} {item.unit}</td><td>{money.format(item.price_usd)}</td><td><input aria-label={`Quantity for ${item.name}`} type="number" min="0" max={item.available} step="1" value={quantities[item.product_id] ?? 0} onChange={event => setQuantities(current => ({ ...current, [item.product_id]: Math.min(item.available, Math.max(0, Number(event.target.value) || 0)) }))}/></td></tr>)}</tbody></table></div>}</section>
        <aside className="inventory-panel"><div className="eyebrow">ORDER</div><h2>Purchase summary</h2>{!lines.length ? <p className="section-note">Add quantities from the catalog to build an order.</p> : lines.map(row => <div className="status-line" key={row.item.product_id}><strong>{row.item.name}</strong><span>{row.quantity} × {money.format(row.item.price_usd)} = {money.format(row.quantity * row.item.price_usd)}</span></div>)}<div className="status-line"><strong>Estimated subtotal</strong><span>{money.format(subtotal)}</span></div><div className="form-grid"><label>Your PO / reference<input value={poReference} onChange={event => setPoReference(event.target.value)} placeholder="Optional"/></label><label>Requested delivery date<input type="date" value={deliveryDate} onChange={event => setDeliveryDate(event.target.value)}/></label><label>Notes<textarea rows={4} value={notes} onChange={event => setNotes(event.target.value)} placeholder="Delivery notes, substitutions, samples, or other requests"/></label></div><button className="marketing-primary" type="button" disabled={!lines.length || order.isPending} onClick={() => order.mutate()}>{order.isPending ? "Submitting…" : "Submit Wholesale Order"}</button><p className="section-note">Availability and pricing are revalidated by DoobieLogic when the order is submitted. This page cannot change supplier inventory directly.</p></aside>
      </div>
    </main>
  </div>;
}
