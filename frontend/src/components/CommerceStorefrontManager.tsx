import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type Storefront = {
  id: string; subdomain: string; url: string; display_name: string; headline: string; description: string;
  logo_url: string; hero_image_url: string; accent_color: string; contact_email: string; order_instructions: string; published: boolean;
};
type Listing = { product_id:string;sku:string;name:string;unit:string;price_usd:number;minimum_quantity:number;case_quantity:number;featured:boolean;active:boolean;sort_order:number };
type CatalogOption = { product_id:string;sku:string;name:string;unit:string;available:number;suggested_price_usd:number };
type RequestLine = { product_id:string;sku:string;name:string;unit:string;quantity:number;price_usd:number;line_total:number };
type OrderRequest = { id:string;buyer_company:string;buyer_license:string;buyer_contact:string;buyer_email:string;buyer_phone:string;purchase_order_reference:string;requested_delivery_date:string|null;notes:string;lines:RequestLine[];estimated_subtotal:number;status:string;commercial_order_id:string|null;created_at:string;review_note:string };
type Snapshot = { storefront:Storefront|null;products:Listing[];pending_orders:OrderRequest[] };

type DraftListing = Listing & { selected:boolean };
const money = new Intl.NumberFormat("en-US", { style:"currency", currency:"USD" });

export function CommerceStorefrontManager() {
  const client = useQueryClient();
  const snapshot = useQuery({ queryKey:["commerce-storefront"], queryFn:({signal})=>apiGet<Snapshot>("/api/v1/storefronts", signal) });
  const options = useQuery({ queryKey:["commerce-storefront-options"], queryFn:({signal})=>apiGet<CatalogOption[]>("/api/v1/storefronts/catalog-options", signal) });
  const [name,setName]=useState(""); const [subdomain,setSubdomain]=useState(""); const [headline,setHeadline]=useState("Wholesale ordering");
  const [description,setDescription]=useState(""); const [logoUrl,setLogoUrl]=useState(""); const [heroUrl,setHeroUrl]=useState("");
  const [accent,setAccent]=useState("#8abf55"); const [contactEmail,setContactEmail]=useState(""); const [instructions,setInstructions]=useState(""); const [published,setPublished]=useState(false);
  const [listings,setListings]=useState<DraftListing[]>([]);
  const [partnerId,setPartnerId]=useState(""); const [days,setDays]=useState("90");

  useEffect(()=>{const row=snapshot.data?.storefront;if(!row)return;setName(row.display_name);setSubdomain(row.subdomain);setHeadline(row.headline);setDescription(row.description);setLogoUrl(row.logo_url);setHeroUrl(row.hero_image_url);setAccent(row.accent_color);setContactEmail(row.contact_email);setInstructions(row.order_instructions);setPublished(row.published);},[snapshot.data?.storefront]);
  useEffect(()=>{if(!options.data)return;const existing=new Map((snapshot.data?.products??[]).map(row=>[row.product_id,row]));setListings(options.data.map((product,index)=>{const row=existing.get(product.product_id);return {product_id:product.product_id,sku:product.sku,name:product.name,unit:product.unit,price_usd:row?.price_usd??product.suggested_price_usd,minimum_quantity:row?.minimum_quantity??1,case_quantity:row?.case_quantity??1,featured:row?.featured??false,active:row?.active??true,sort_order:row?.sort_order??index,selected:Boolean(row?.active)};}));},[options.data,snapshot.data?.products]);

  const refresh=async()=>{await client.invalidateQueries({queryKey:["commerce-storefront"]});await client.invalidateQueries({queryKey:["commerce-storefront-options"]});};
  const save=useMutation({mutationFn:()=>apiPost<Storefront>("/api/v1/storefronts",{display_name:name,subdomain,headline,description,logo_url:logoUrl,hero_image_url:heroUrl,accent_color:accent,contact_email:contactEmail,order_instructions:instructions,published}),onSuccess:refresh});
  const saveProducts=useMutation({mutationFn:()=>apiPost<Snapshot>("/api/v1/storefronts/products",{products:listings.filter(row=>row.selected).map(({selected: _selected,...row})=>({...row,active:true}))}),onSuccess:refresh});
  const approve=useMutation({mutationFn:(id:string)=>apiPost(`/api/v1/storefronts/orders/${id}/approve`,{note:"Approved from DoobieCommerce inbox."}),onSuccess:refresh});
  const reject=useMutation({mutationFn:(id:string)=>apiPost(`/api/v1/storefronts/orders/${id}/reject`,{note:"Rejected from DoobieCommerce inbox."}),onSuccess:refresh});
  const issue=useMutation({mutationFn:()=>apiPost<{id:string;token:string;expires_at:string;warning:string}>("/api/v1/control-tower/commerce/access",{partner_id:partnerId,expires_days:Number(days)})});
  const privatePortalUrl=useMemo(()=>issue.data?`${window.location.origin}/portal/${encodeURIComponent(issue.data.token)}`:"",[issue.data]);
  const publicUrl=snapshot.data?.storefront?.url || (subdomain?`https://${subdomain}.doobielogic.io`:"");
  const pending=(snapshot.data?.pending_orders??[]).filter(row=>row.status==="submitted");

  if(snapshot.isLoading)return <div className="state">Loading DoobieCommerce…</div>;
  if(snapshot.isError)return <div className="warning-banner">DoobieCommerce is unavailable: {snapshot.error.message}</div>;
  return <div className="commerce-manager">
    <section className="inventory-panel">
      <div className="eyebrow">HOSTED WHOLESALE SITE</div><h2>Storefront builder</h2>
      <p className="section-note">Publish a branded customer-facing wholesale site at <strong>{subdomain||"yourbrand"}.doobielogic.io</strong>. The public site can accept order requests, but only your team can approve them into Commercial Ops.</p>
      <div className="form-grid two">
        <label>Brand / storefront name<input value={name} onChange={e=>setName(e.target.value)} placeholder="Zero Hour Cannabis Co."/></label>
        <label>DoobieLogic subdomain<div className="input-suffix"><input value={subdomain} onChange={e=>setSubdomain(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g,""))} placeholder="zerohour"/><span>.doobielogic.io</span></div></label>
        <label className="full">Headline<input value={headline} onChange={e=>setHeadline(e.target.value)} placeholder="Premium Massachusetts cannabis, available wholesale"/></label>
        <label className="full">Brand story / landing-page copy<textarea rows={4} value={description} onChange={e=>setDescription(e.target.value)}/></label>
        <label>Logo URL<input value={logoUrl} onChange={e=>setLogoUrl(e.target.value)} placeholder="https://…"/></label>
        <label>Hero image URL<input value={heroUrl} onChange={e=>setHeroUrl(e.target.value)} placeholder="https://…"/></label>
        <label>Accent color<input type="color" value={accent} onChange={e=>setAccent(e.target.value)}/></label>
        <label>Sales email<input type="email" value={contactEmail} onChange={e=>setContactEmail(e.target.value)}/></label>
        <label className="full">Order instructions<textarea rows={3} value={instructions} onChange={e=>setInstructions(e.target.value)} placeholder="Minimums, delivery days, terms, sample policy…"/></label>
        <label className="checkbox-row full"><input type="checkbox" checked={published} onChange={e=>setPublished(e.target.checked)}/> Publish storefront</label>
      </div>
      <div className="audit-actions"><button className="primary" disabled={!name||!subdomain||save.isPending} onClick={()=>save.mutate()}>{save.isPending?"Saving…":"Save storefront"}</button>{publicUrl?<a className="secondary button-link" href={publicUrl} target="_blank" rel="noreferrer">Open storefront</a>:null}</div>
      {save.isError?<div className="form-error">{save.error.message}</div>:null}{snapshot.data?.storefront?<div className={snapshot.data.storefront.published?"success-banner":"info-banner"}><strong>{snapshot.data.storefront.published?"Published":"Draft"}</strong><br/><code>{snapshot.data.storefront.url}</code></div>:null}
    </section>

    <section className="inventory-panel">
      <div className="eyebrow">CATALOG MERCHANDISING</div><h2>Products & wholesale rules</h2><p className="section-note">Choose exactly what the public storefront can sell. Price, minimums, case quantities, featured placement, and live availability are enforced server-side.</p>
      {options.isLoading?<div className="state">Loading products…</div>:<div className="table-wrap"><table><thead><tr><th>Show</th><th>Product</th><th>Available</th><th>Wholesale price</th><th>Minimum</th><th>Case qty</th><th>Featured</th></tr></thead><tbody>{listings.map((row,index)=><tr key={row.product_id}><td><input type="checkbox" checked={row.selected} onChange={e=>setListings(current=>current.map((item,i)=>i===index?{...item,selected:e.target.checked}:item))}/></td><td><strong>{row.name}</strong><br/><small>{row.sku}</small></td><td>{options.data?.find(item=>item.product_id===row.product_id)?.available.toLocaleString()??"—"} {row.unit}</td><td><input type="number" min="0" step="0.01" value={row.price_usd} onChange={e=>setListings(current=>current.map((item,i)=>i===index?{...item,price_usd:Number(e.target.value)}:item))}/></td><td><input type="number" min="0.001" value={row.minimum_quantity} onChange={e=>setListings(current=>current.map((item,i)=>i===index?{...item,minimum_quantity:Number(e.target.value)}:item))}/></td><td><input type="number" min="0.001" value={row.case_quantity} onChange={e=>setListings(current=>current.map((item,i)=>i===index?{...item,case_quantity:Number(e.target.value)}:item))}/></td><td><input type="checkbox" checked={row.featured} onChange={e=>setListings(current=>current.map((item,i)=>i===index?{...item,featured:e.target.checked}:item))}/></td></tr>)}</tbody></table></div>}
      <button className="primary" disabled={!snapshot.data?.storefront||saveProducts.isPending} onClick={()=>saveProducts.mutate()}>{saveProducts.isPending?"Saving catalog…":"Save storefront catalog"}</button>{saveProducts.isError?<div className="form-error">{saveProducts.error.message}</div>:null}
    </section>

    <section className="inventory-panel">
      <div className="eyebrow">INCOMING WEB ORDERS</div><h2>Approval inbox</h2><p className="section-note">Public submissions stay here until approved. Approval rechecks live inventory, matches or creates the customer record, and then creates the canonical sales order.</p>
      {!pending.length?<div className="info-banner">No storefront orders are waiting for approval.</div>:<div className="table-wrap"><table><thead><tr><th>Buyer</th><th>Requested</th><th>Order</th><th>Subtotal</th><th>Decision</th></tr></thead><tbody>{pending.map(row=><tr key={row.id}><td><strong>{row.buyer_company}</strong><br/><small>{row.buyer_contact} · {row.buyer_email}{row.buyer_license?` · ${row.buyer_license}`:""}</small></td><td>{new Date(row.created_at).toLocaleString()}<br/><small>{row.requested_delivery_date?`Delivery ${row.requested_delivery_date}`:"No delivery date requested"}</small></td><td>{row.lines.map(line=><div key={line.product_id}>{line.quantity} {line.unit} · {line.name}</div>)}{row.purchase_order_reference?<small>PO: {row.purchase_order_reference}</small>:null}</td><td>{money.format(row.estimated_subtotal)}</td><td><div className="audit-actions"><button className="primary" disabled={approve.isPending||reject.isPending} onClick={()=>approve.mutate(row.id)}>Approve</button><button className="secondary" disabled={approve.isPending||reject.isPending} onClick={()=>reject.mutate(row.id)}>Reject</button></div></td></tr>)}</tbody></table></div>}
      {approve.isError?<div className="form-error">{approve.error.message}</div>:null}{approve.data?<div className="success-banner">Order approved and returned to DoobieLogic Commercial Ops.</div>:null}
    </section>

    <section className="inventory-panel">
      <div className="eyebrow">PRIVATE CUSTOMER PORTAL</div><h2>Negotiated retailer access</h2><p className="section-note">Keep the existing private portal for established customers who need account-specific pricing and terms. This sits beside the public branded storefront, not instead of it.</p>
      <div className="form-grid two"><label>Customer partner ID<input value={partnerId} onChange={e=>setPartnerId(e.target.value)} placeholder="Commercial partner ID"/></label><label>Expires in days<input type="number" min="1" max="365" value={days} onChange={e=>setDays(e.target.value)}/></label></div>
      <button className="primary" disabled={!partnerId||issue.isPending} onClick={()=>issue.mutate()}>Issue private retailer access</button>{issue.isError?<div className="form-error">{issue.error.message}</div>:null}{issue.data?<div className="success-banner"><strong>Private access issued.</strong><br/><code>{privatePortalUrl}</code><br/><small>{issue.data.warning}</small></div>:null}
    </section>
  </div>;
}
