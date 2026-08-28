import { useMemo, useState, type CSSProperties } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiPublicGet, apiPublicPost } from "../lib/api";

type Storefront = {
  id: string;
  slug: string;
  subdomain: string;
  url: string;
  display_name: string;
  headline: string;
  description: string;
  logo_url: string;
  hero_image_url: string;
  accent_color: string;
  contact_email: string;
  order_instructions: string;
  published: boolean;
};

type CatalogItem = {
  product_id: string;
  sku: string;
  name: string;
  unit: string;
  available: number;
  price_usd: number;
  minimum_quantity: number;
  case_quantity: number;
  featured: boolean;
};

type PublicCatalog = { storefront: Storefront; catalog: CatalogItem[] };
type SubmitResult = { request_id: string; status: string; estimated_subtotal: number; message: string };

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const COWBOY_LOGO = "https://cdn.prod.website-files.com/67e2f0206a0ebdea924dda1f/67e2f625ac0a258b94033c1e_relume-57886.jpg";
const COWBOY_PRE_ROLL_IMAGE = "https://cdn.prod.website-files.com/67e2f0206a0ebdea924dda1f/684605625f427990b7edb4b3_CK%20Pre%20Roll%20Tube-3.avif";
const COWBOY_FLOWER_IMAGE = "https://cdn.prod.website-files.com/67e2f0206a0ebdea924dda1f/6a7b9448313dd1e154bea918_Cowboy%20Kush%20Bag%202%20%28small%29.jpg";
const COWBOY_HERO_IMAGE = "https://cdn.prod.website-files.com/67e2f0206a0ebdea924dda1f/67e2f62c209cf18cde199520_696388bc840836ba53c0fc037ab51c30_cowboy-kush-man%20in%20cannabis%20field.avif";

function cowboyProductMeta(item: CatalogItem) {
  const text = `${item.name} ${item.sku}`.toLowerCase();
  const preRoll = /pre[ -]?roll/.test(text);
  const preground = text.includes("preground") || text.includes("pre-ground");
  const pack = text.match(/\b\d+(?:\.\d+)?\s*g\b/i)?.[0] || item.unit;
  return {
    image: preRoll ? COWBOY_PRE_ROLL_IMAGE : COWBOY_FLOWER_IMAGE,
    type: preRoll ? "PRE-ROLL" : preground ? "PREGROUND FULL-FLOWER" : "PREPACK FLOWER",
    packSize: pack,
    badges: preRoll ? ["FULL FLOWER", "MASSACHUSETTS"] : ["FULL FLOWER", "MASSACHUSETTS", "CRAFT VALUE"],
  };
}

export function StorefrontPage({ slug }: { slug: string }) {
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [company, setCompany] = useState("");
  const [license, setLicense] = useState("");
  const [contact, setContact] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [poReference, setPoReference] = useState("");
  const [deliveryDate, setDeliveryDate] = useState("");
  const [notes, setNotes] = useState("");

  const catalog = useQuery({
    queryKey: ["hosted-storefront", slug],
    queryFn: ({ signal }) => apiPublicGet<PublicCatalog>(`/api/v1/commerce-storefronts/${encodeURIComponent(slug)}`, signal),
    retry: false,
  });

  const lines = useMemo(() => (catalog.data?.catalog ?? []).map(item => ({
    item,
    quantity: Math.max(0, Number(quantities[item.product_id] ?? 0)),
  })).filter(row => row.quantity > 0), [catalog.data, quantities]);
  const subtotal = lines.reduce((sum, row) => sum + row.quantity * row.item.price_usd, 0);

  const submit = useMutation({
    mutationFn: () => apiPublicPost<SubmitResult>(`/api/v1/commerce-storefronts/${encodeURIComponent(slug)}/orders`, {
      buyer_company: company,
      buyer_license: license,
      buyer_contact: contact,
      buyer_email: email,
      buyer_phone: phone,
      lines: lines.map(row => ({ product_id: row.item.product_id, quantity: row.quantity })),
      requested_delivery_date: deliveryDate || null,
      purchase_order_reference: poReference,
      notes,
    }),
    onSuccess: () => setQuantities({}),
  });

  if (catalog.isLoading) return <div className="storefront-shell"><div className="state">Loading wholesale storefront…</div></div>;
  if (catalog.isError) return <div className="storefront-shell"><main className="storefront-main"><div className="warning-banner"><strong>This storefront is unavailable.</strong><br/>{catalog.error.message}</div></main></div>;

  const data = catalog.data!;
  const cowboy = slug.trim().toLowerCase() === "cowboykush" || data.storefront.subdomain.trim().toLowerCase() === "cowboykush";
  const theme = cowboy
    ? ({ "--storefront-accent": "#b58b3d", "--cowboy-slate": "#536f80", "--cowboy-cream": "#e8e4dc" } as CSSProperties)
    : ({ "--storefront-accent": data.storefront.accent_color || "#8abf55" } as CSSProperties);

  const setItemQuantity = (item: CatalogItem, raw: number) => {
    const quantity = Math.min(item.available, Math.max(0, raw || 0));
    setQuantities(current => ({ ...current, [item.product_id]: quantity }));
  };

  const addMinimum = (item: CatalogItem) => {
    const current = Number(quantities[item.product_id] ?? 0);
    const next = current > 0 ? Math.min(item.available, current + item.case_quantity) : Math.min(item.available, item.minimum_quantity);
    setItemQuantity(item, next);
  };

  if (cowboy) {
    return <div className="storefront-shell cowboy-storefront" style={theme}>
      <header className="storefront-nav cowboy-nav">
        <div className="storefront-brand cowboy-brand">
          <img src={data.storefront.logo_url || COWBOY_LOGO} alt="Cowboy Kush" />
        </div>
        <nav className="cowboy-nav-actions" aria-label="Cowboy Kush wholesale navigation">
          <a href="#catalog">Wholesale</a>
          {data.storefront.contact_email ? <a href={`mailto:${data.storefront.contact_email}`}>Contact sales</a> : null}
          <a className="cowboy-order-link" href="#order-request">Order request <span>{lines.length}</span></a>
        </nav>
      </header>

      <main className="storefront-main cowboy-main">
        <section className="storefront-hero cowboy-hero" style={{ backgroundImage: `linear-gradient(90deg, rgba(7,29,50,.98) 0%, rgba(7,29,50,.91) 48%, rgba(7,29,50,.46) 100%), url(${data.storefront.hero_image_url || COWBOY_HERO_IMAGE})` }}>
          <div className="cowboy-hero-mark">★</div>
          <div className="storefront-kicker">ROOTED IN TRADITION · GROWN FOR ADVENTURE</div>
          <h1>Premium Massachusetts<br/>Flower &amp; Pre-Rolls</h1>
          <p>Cooperative grown. Craft quality. Consistently trusted. Built for licensed Massachusetts retail partners.</p>
          <a className="storefront-cta cowboy-cta" href="#catalog">Shop wholesale availability</a>
        </section>

        {submit.data ? <div className="success-banner storefront-message"><strong>Order request received.</strong><br/>Request {submit.data.request_id.slice(0, 8).toUpperCase()} was sent to Cowboy Kush for approval. Inventory is not deducted until their team reviews the request.</div> : null}
        {submit.isError ? <div className="warning-banner storefront-message"><strong>Order request could not be submitted.</strong><br/>{submit.error.message}</div> : null}

        <div className="storefront-layout cowboy-layout" id="catalog">
          <section className="cowboy-catalog">
            <div className="storefront-section-head cowboy-section-head">
              <div><span>AVAILABLE NOW</span><h2>Wholesale Catalog</h2></div>
              <small>{data.catalog.length} products currently orderable</small>
            </div>

            {!data.catalog.length ? <div className="info-banner">No Cowboy Kush products are currently available for online ordering.</div> : <div className="storefront-products cowboy-products">
              {data.catalog.map(item => {
                const quantity = quantities[item.product_id] ?? 0;
                const meta = cowboyProductMeta(item);
                return <article className={`storefront-product cowboy-card${item.featured ? " featured" : ""}`} key={item.product_id}>
                  <div className="cowboy-card-topline"><span>★</span><small>{item.featured ? "FEATURED" : "COWBOY KUSH"}</small></div>
                  <div className="cowboy-card-image"><img src={meta.image} alt={item.name} /></div>
                  <div className="cowboy-card-badges">{meta.badges.map(badge => <span key={badge}>{badge}</span>)}</div>
                  <div className="storefront-product-copy cowboy-card-copy"><small>{meta.type}</small><h3>{item.name}</h3><p>{item.available.toLocaleString()} {item.unit} available</p></div>

                  <dl className="cowboy-card-stats">
                    <div><dt>SKU</dt><dd>{item.sku}</dd></div>
                    <div><dt>Pack size</dt><dd>{meta.packSize}</dd></div>
                    <div><dt>Case qty</dt><dd>{item.case_quantity.toLocaleString()}</dd></div>
                    <div><dt>Wholesale</dt><dd>{money.format(item.price_usd)}</dd></div>
                    <div><dt>Min order</dt><dd>{item.minimum_quantity.toLocaleString()} {item.unit}</dd></div>
                    <div><dt>Status</dt><dd>In stock</dd></div>
                  </dl>

                  <div className="cowboy-card-order">
                    <label>Qty<input type="number" min="0" max={item.available} step={item.case_quantity} value={quantity} onChange={event => setItemQuantity(item, Number(event.target.value))} /></label>
                    <button type="button" onClick={() => addMinimum(item)}>{quantity > 0 ? "Add case" : "Add to order"} <span>＋</span></button>
                  </div>
                  <small className="storefront-order-rule">Minimum {item.minimum_quantity.toLocaleString()} · case multiple {item.case_quantity.toLocaleString()}</small>
                </article>;
              })}
            </div>}
          </section>

          <aside className="storefront-cart cowboy-cart" id="order-request">
            <div className="cowboy-cart-title"><span>ORDER REQUEST</span><strong>{lines.length} {lines.length === 1 ? "item" : "items"}</strong></div>
            {!lines.length ? <div className="cowboy-empty-cart"><strong>Build your wholesale order.</strong><p>Choose a quantity on any Cowboy Kush card and it will appear here.</p></div> : <div className="storefront-cart-lines cowboy-cart-lines">{lines.map(row => {
              const meta = cowboyProductMeta(row.item);
              return <div key={row.item.product_id}>
                <img src={meta.image} alt="" />
                <span>{row.item.name}<small>{row.quantity} {row.item.unit} · {money.format(row.item.price_usd)} / {row.item.unit}</small></span>
                <strong>{money.format(row.quantity * row.item.price_usd)}</strong>
              </div>;
            })}</div>}
            <div className="storefront-subtotal cowboy-subtotal"><span>Estimated subtotal</span><strong>{money.format(subtotal)}</strong></div>

            <div className="cowboy-retailer-note">
              <strong>Licensed retailer order request</strong>
              <span>Enter your store details so Cowboy Kush can review availability, pricing and delivery.</span>
            </div>

            <div className="form-grid storefront-buyer-form cowboy-buyer-form">
              <label>Business / dispensary name<input value={company} onChange={event => setCompany(event.target.value)} /></label>
              <label>MA license number<input value={license} onChange={event => setLicense(event.target.value)} placeholder="Recommended for faster approval" /></label>
              <label>Contact name<input value={contact} onChange={event => setContact(event.target.value)} /></label>
              <label>Email<input type="email" value={email} onChange={event => setEmail(event.target.value)} /></label>
              <label>Phone<input value={phone} onChange={event => setPhone(event.target.value)} /></label>
              <label>Your PO / reference<input value={poReference} onChange={event => setPoReference(event.target.value)} /></label>
              <label>Requested delivery date<input type="date" value={deliveryDate} onChange={event => setDeliveryDate(event.target.value)} /></label>
              <label>Notes<textarea rows={3} value={notes} onChange={event => setNotes(event.target.value)} placeholder="Delivery notes, substitutions, samples, or sales questions" /></label>
            </div>
            {data.storefront.order_instructions ? <p className="storefront-instructions">{data.storefront.order_instructions}</p> : null}
            <button className="storefront-submit cowboy-submit" type="button" disabled={!lines.length || !company || !contact || !email || submit.isPending} onClick={() => submit.mutate()}>{submit.isPending ? "Sending…" : "Submit order request"} <span>→</span></button>
            <p className="section-note cowboy-powered">Wholesale ordering powered by DoobieLogic · Request subject to Cowboy Kush review and approval.</p>
          </aside>
        </div>
      </main>
    </div>;
  }

  return <div className="storefront-shell" style={theme}>
    <header className="storefront-nav">
      <div className="storefront-brand">
        {data.storefront.logo_url ? <img src={data.storefront.logo_url} alt={`${data.storefront.display_name} logo`} /> : <div className="storefront-logo-fallback">{data.storefront.display_name.slice(0, 1).toUpperCase()}</div>}
        <div><strong>{data.storefront.display_name}</strong><span>Wholesale · Powered by DoobieLogic</span></div>
      </div>
      {data.storefront.contact_email ? <a href={`mailto:${data.storefront.contact_email}`}>Contact sales</a> : null}
    </header>

    <main className="storefront-main">
      <section className={`storefront-hero${data.storefront.hero_image_url ? " with-image" : ""}`} style={data.storefront.hero_image_url ? { backgroundImage: `linear-gradient(90deg, rgba(13,16,14,.93), rgba(13,16,14,.55)), url(${data.storefront.hero_image_url})` } : undefined}>
        <div className="storefront-kicker">LICENSED CANNABIS WHOLESALE</div>
        <h1>{data.storefront.headline || "Wholesale ordering"}</h1>
        <p>{data.storefront.description || `Browse current wholesale availability from ${data.storefront.display_name}, build your order, and send it directly to their sales team for approval.`}</p>
        <a className="storefront-cta" href="#catalog">Shop available inventory</a>
      </section>

      {submit.data ? <div className="success-banner storefront-message"><strong>Order request received.</strong><br/>Request {submit.data.request_id.slice(0, 8).toUpperCase()} was sent to {data.storefront.display_name} for approval. Nothing is deducted from inventory until their team reviews the request.</div> : null}
      {submit.isError ? <div className="warning-banner storefront-message"><strong>Order request could not be submitted.</strong><br/>{submit.error.message}</div> : null}

      <div className="storefront-layout" id="catalog">
        <section>
          <div className="storefront-section-head"><div><span>AVAILABLE NOW</span><h2>Wholesale catalog</h2></div><small>{data.catalog.length} products currently orderable</small></div>
          {!data.catalog.length ? <div className="info-banner">No products are currently available for online ordering.</div> : <div className="storefront-products">
            {data.catalog.map(item => {
              const quantity = quantities[item.product_id] ?? 0;
              return <article className={`storefront-product${item.featured ? " featured" : ""}`} key={item.product_id}>
                {item.featured ? <span className="storefront-featured">Featured</span> : null}
                <div className="storefront-product-copy"><small>{item.sku}</small><h3>{item.name}</h3><p>{item.available.toLocaleString()} {item.unit} available</p></div>
                <div className="storefront-price"><strong>{money.format(item.price_usd)}</strong><span>per {item.unit}</span></div>
                <label>Order quantity<input type="number" min="0" max={item.available} step={item.case_quantity} value={quantity} onChange={event => setItemQuantity(item, Number(event.target.value))}/></label>
                <small className="storefront-order-rule">Minimum {item.minimum_quantity.toLocaleString()} · case multiple {item.case_quantity.toLocaleString()}</small>
              </article>;
            })}
          </div>}
        </section>

        <aside className="storefront-cart">
          <div className="storefront-section-head"><div><span>ORDER REQUEST</span><h2>Send to sales</h2></div></div>
          {!lines.length ? <p className="section-note">Choose quantities from the catalog to start an order.</p> : <div className="storefront-cart-lines">{lines.map(row => <div key={row.item.product_id}><span>{row.item.name}<small>{row.quantity} {row.item.unit}</small></span><strong>{money.format(row.quantity * row.item.price_usd)}</strong></div>)}</div>}
          <div className="storefront-subtotal"><span>Estimated subtotal</span><strong>{money.format(subtotal)}</strong></div>
          <div className="form-grid storefront-buyer-form">
            <label>Business / dispensary name<input value={company} onChange={event => setCompany(event.target.value)} /></label>
            <label>License number<input value={license} onChange={event => setLicense(event.target.value)} placeholder="Recommended for faster approval" /></label>
            <label>Contact name<input value={contact} onChange={event => setContact(event.target.value)} /></label>
            <label>Email<input type="email" value={email} onChange={event => setEmail(event.target.value)} /></label>
            <label>Phone<input value={phone} onChange={event => setPhone(event.target.value)} /></label>
            <label>Your PO / reference<input value={poReference} onChange={event => setPoReference(event.target.value)} /></label>
            <label>Requested delivery date<input type="date" value={deliveryDate} onChange={event => setDeliveryDate(event.target.value)} /></label>
            <label>Notes<textarea rows={4} value={notes} onChange={event => setNotes(event.target.value)} placeholder="Delivery notes, samples, substitutions, or sales questions" /></label>
          </div>
          {data.storefront.order_instructions ? <p className="storefront-instructions">{data.storefront.order_instructions}</p> : null}
          <button className="storefront-submit" type="button" disabled={!lines.length || !company || !contact || !email || submit.isPending} onClick={() => submit.mutate()}>{submit.isPending ? "Sending…" : "Submit order for approval"}</button>
          <p className="section-note">Submitting creates an order request only. {data.storefront.display_name} reviews it inside DoobieLogic before it becomes an operational sales order.</p>
        </aside>
      </div>
    </main>
  </div>;
}
