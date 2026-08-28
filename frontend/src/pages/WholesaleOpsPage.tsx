import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { CommerceStorefrontManager } from "../components/CommerceStorefrontManager";
import { WholesaleRegulatoryHealth } from "../components/WholesaleRegulatoryHealth";
import { apiGet } from "../lib/api";
import { OrdersPage } from "./OrdersPage";
import { WarehousePickPackPage } from "./WarehousePickPackPage";
import "../wholesale-ops.css";

type Tab = "overview" | "inventory" | "orders" | "fulfillment" | "customers" | "storefront";
type WholesaleLot = {
  lot_id:string; package_id:string; lot_code:string; product_id:string; sku:string; name:string; item_type:string;
  inventory_type:"bulk"|"retail_ready"; available:number; reserved:number; usable:number; unit:string; location:string;
  status:string; lab_testing_state:string; coa_reference:string; received_at:string|null; expiration_at:string|null;
  unit_cost:number; suggested_price_usd:number; eligible:boolean; blocked_reasons:string[];
};
type WholesaleInventory = {
  items:WholesaleLot[];
  blocked_items:WholesaleLot[];
  summary:{sellable_lots:number;bulk_lots:number;retail_ready_lots:number;sellable_quantity:number;blocked_lots:number};
  eligibility_policy:{requires_released_inventory:boolean;requires_passed_coa:boolean;requires_positive_uncommitted_quantity:boolean};
};
type Partner = {id:string;name:string;partner_type:string;license_or_registration:string;contact_name:string;contact_email:string;contact_phone:string;payment_terms:string;active:boolean};
type CommercialWorkspace = {
  metrics:{open_sales_value:number;open_orders:number;overdue_orders:number;fill_rate_pct:number};
  partners:Partner[];
  orders:{id:string;order_type:string;status:string;order_total:number}[];
};
type StorefrontSnapshot = { storefront:{published:boolean}|null; pending_orders:{id:string;status:string}[] };

const TABS:[Tab,string][] = [
  ["overview","Overview"],
  ["inventory","Inventory"],
  ["orders","Orders"],
  ["fulfillment","Fulfillment"],
  ["customers","Customers"],
  ["storefront","Storefront"],
];

export function WholesaleOpsPage({onNavigate}:{onNavigate:(page:string)=>void}) {
  const [tab,setTab]=useState<Tab>("overview");
  const inventory=useQuery({queryKey:["wholesale-inventory"],queryFn:({signal})=>apiGet<WholesaleInventory>("/api/v1/storefronts/wholesale-inventory",signal)});
  const commercial=useQuery({queryKey:["commercial-workspace"],queryFn:({signal})=>apiGet<CommercialWorkspace>("/api/v1/commercial/workspace",signal)});
  const storefront=useQuery({queryKey:["commerce-storefront"],queryFn:({signal})=>apiGet<StorefrontSnapshot>("/api/v1/storefronts",signal)});
  const pendingStorefront=(storefront.data?.pending_orders??[]).filter(row=>row.status==="submitted").length;
  const openSales=(commercial.data?.orders??[]).filter(row=>row.order_type==="sales"&&!["fulfilled","cancelled"].includes(row.status)).length;

  return <div className="page wholesale-ops-page">
    <div className="page-heading wholesale-hero">
      <div><div className="eyebrow">WHOLESALE OPS</div><h1>Sellable inventory to fulfilled order.</h1><p>One commercial workspace for passed-COA inventory, wholesale orders, fulfillment, customers, and the hosted storefront.</p></div>
      <div className="wholesale-flow"><span>Production</span><b>→</b><span>COA Passed</span><b>→</b><span>Wholesale</span><b>→</b><span>Fulfillment</span></div>
    </div>
    <div className="view-tabs parity-tabs wholesale-tabs" role="tablist">{TABS.map(([key,label])=><button key={key} role="tab" aria-selected={tab===key} className={tab===key?"active":""} onClick={()=>setTab(key)}>{label}</button>)}</div>

    {tab==="overview"?<Overview inventory={inventory.data} commercial={commercial.data} pendingStorefront={pendingStorefront} openSales={openSales} onTab={setTab}/>:null}
    {tab==="inventory"?<WholesaleInventoryPanel query={inventory}/>:null}
    {tab==="orders"?<OrdersPage/>:null}
    {tab==="fulfillment"?<WarehousePickPackPage onNavigate={page=>page==="Orders"?setTab("orders"):onNavigate(page)}/>:null}
    {tab==="customers"?<CustomersPanel commercial={commercial.data} loading={commercial.isLoading} error={commercial.isError?commercial.error.message:""}/>:null}
    {tab==="storefront"?<CommerceStorefrontManager/>:null}
  </div>;
}

function Overview({inventory,commercial,pendingStorefront,openSales,onTab}:{inventory:WholesaleInventory|undefined;commercial:CommercialWorkspace|undefined;pendingStorefront:number;openSales:number;onTab:(tab:Tab)=>void}) {
  return <>
    <section className="metrics wholesale-metrics">
      <Metric label="Sellable lots" value={inventory?.summary.sellable_lots??"—"} meta={`${inventory?.summary.bulk_lots??0} bulk · ${inventory?.summary.retail_ready_lots??0} retail ready`}/>
      <Metric label="Available to sell" value={inventory?number(inventory.summary.sellable_quantity):"—"} meta="After active reservations"/>
      <Metric label="Open sales orders" value={openSales} meta={commercial?money(commercial.metrics.open_sales_value):"Commercial order value"}/>
      <Metric label="Storefront approvals" value={pendingStorefront} meta="Public requests awaiting review"/>
      <Metric label="Fill rate" value={commercial?`${commercial.metrics.fill_rate_pct.toFixed(1)}%`:"—"} meta={`${commercial?.metrics.overdue_orders??0} overdue orders`}/>
    </section>
    <WholesaleRegulatoryHealth />
    <section className="wholesale-action-grid">
      <Action title="Wholesale Inventory" note="Only released lots with a passed COA and positive uncommitted quantity are sellable." action="Review inventory" onClick={()=>onTab("inventory")}/>
      <Action title="Orders" note="Storefront, direct, and account orders converge into the same commercial sales-order engine." action="Work orders" onClick={()=>onTab("orders")}/>
      <Action title="Fulfillment" note="Allocate, scan, pick, pack, and ship against the actual package or lot selected for the order." action="Open fulfillment" onClick={()=>onTab("fulfillment")}/>
      <Action title="Customers" note="Keep retailer licenses, contacts, payment terms, and account relationships attached to the commercial record." action="View customers" onClick={()=>onTab("customers")}/>
      <Action title="Storefront" note="Publish only inventory that Wholesale Ops currently considers legally and operationally sellable." action="Manage storefront" onClick={()=>onTab("storefront")}/>
    </section>
    {inventory?.summary.blocked_lots?<div className="info-banner"><strong>{inventory.summary.blocked_lots} inventory lot{inventory.summary.blocked_lots===1?" is":"s are"} intentionally excluded from wholesale.</strong><br/>Missing/failed COA, hold status, or fully committed inventory never flows into the sellable catalog.</div>:null}
  </>;
}

function WholesaleInventoryPanel({query}:{query:UseQueryResult<WholesaleInventory,Error>}) {
  const [kind,setKind]=useState<"all"|"bulk"|"retail_ready">("all");
  const [search,setSearch]=useState("");
  const [showBlocked,setShowBlocked]=useState(false);
  const rows=useMemo(()=>{
    const source=showBlocked?(query.data?.blocked_items??[]):(query.data?.items??[]);
    const needle=search.trim().toLowerCase();
    return source.filter(row=>(kind==="all"||row.inventory_type===kind)&&(!needle||[row.name,row.sku,row.package_id,row.lot_code,row.coa_reference,row.location].join(" ").toLowerCase().includes(needle)));
  },[query.data,kind,search,showBlocked]);
  if(query.isLoading)return <div className="state">Building wholesale inventory…</div>;
  if(query.isError)return <div className="warning-banner">Wholesale inventory could not be loaded: {query.error.message}</div>;
  return <>
    <section className="inventory-panel wholesale-policy"><div><div className="eyebrow">SELLABILITY POLICY</div><h2>Production inventory is still the source of truth.</h2><p>Wholesale Ops is a commercial projection, not a second inventory ledger. A lot appears here only when it is released, has a passed COA reference, and has positive quantity left after reservations.</p></div><div className="wholesale-policy-pills"><span>Released</span><span>Passed COA</span><span>Uncommitted Qty</span></div></section>
    <section className="inventory-panel">
      <div className="wholesale-inventory-tools"><div className="view-tabs parity-tabs"><button className={kind==="all"?"active":""} onClick={()=>setKind("all")}>All</button><button className={kind==="bulk"?"active":""} onClick={()=>setKind("bulk")}>Bulk</button><button className={kind==="retail_ready"?"active":""} onClick={()=>setKind("retail_ready")}>Retail Ready</button></div><label className="inventory-search"><span>Search</span><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Product, package, lot, COA, location"/></label><label className="checkbox-row"><input type="checkbox" checked={showBlocked} onChange={e=>setShowBlocked(e.target.checked)}/> Show blocked inventory</label></div>
      {!rows.length?<div className="info-banner">No inventory matches this wholesale view.</div>:<div className="table-wrap"><table><thead><tr><th>Type</th><th>Product</th><th>Package / Lot</th><th>COA</th><th>Available</th><th>Reserved</th><th>Sellable</th><th>Location</th><th>Status</th></tr></thead><tbody>{rows.map(row=><tr key={row.lot_id}><td><span className="status-pill">{row.inventory_type==="bulk"?"Bulk":"Retail Ready"}</span></td><td><strong>{row.name}</strong><br/><small>{row.sku}</small></td><td>{row.package_id}<br/><small>{row.lot_code}</small></td><td>{row.coa_reference||"Missing"}<br/><small>{row.lab_testing_state||"No lab state"}</small></td><td>{number(row.available)} {row.unit}</td><td>{number(row.reserved)} {row.unit}</td><td><strong>{number(row.usable)} {row.unit}</strong></td><td>{row.location||"—"}</td><td>{showBlocked&&row.blocked_reasons.length?<span title={row.blocked_reasons.join("; ")} className="warning-text">Blocked</span>:<span className="success-text">Sellable</span>}</td></tr>)}</tbody></table></div>}
    </section>
  </>;
}

function CustomersPanel({commercial,loading,error}:{commercial:CommercialWorkspace|undefined;loading:boolean;error:string}) {
  const customers=(commercial?.partners??[]).filter(row=>row.active&&["customer","both"].includes(row.partner_type));
  if(loading)return <div className="state">Loading wholesale customers…</div>;
  if(error)return <div className="warning-banner">Customers could not be loaded: {error}</div>;
  return <section className="inventory-panel"><div className="eyebrow">WHOLESALE ACCOUNTS</div><h2>Customers</h2><p className="section-note">Retailer and trade-account records already used by Commercial Ops. Their order history, terms, and private portal access remain connected to the same partner identity.</p>{!customers.length?<div className="info-banner">No active wholesale customers are configured yet. Create customer trade partners from the Orders workspace.</div>:<div className="table-wrap"><table><thead><tr><th>Customer</th><th>License / Registration</th><th>Contact</th><th>Email</th><th>Phone</th><th>Terms</th></tr></thead><tbody>{customers.map(row=><tr key={row.id}><td><strong>{row.name}</strong></td><td>{row.license_or_registration||"—"}</td><td>{row.contact_name||"—"}</td><td>{row.contact_email||"—"}</td><td>{row.contact_phone||"—"}</td><td>{row.payment_terms||"—"}</td></tr>)}</tbody></table></div>}</section>;
}

function Metric({label,value,meta}:{label:string;value:string|number;meta:string}){return <article className="metric"><span>{label}</span><strong>{value}</strong><small>{meta}</small></article>}
function Action({title,note,action,onClick}:{title:string;note:string;action:string;onClick:()=>void}){return <article className="inventory-panel wholesale-action"><div><h3>{title}</h3><p>{note}</p></div><button className="secondary" onClick={onClick}>{action}</button></article>}
function number(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:2})}
function money(value:number){return Number(value||0).toLocaleString(undefined,{style:"currency",currency:"USD",maximumFractionDigits:0})}