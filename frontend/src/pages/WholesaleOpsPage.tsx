import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { lazy, Suspense, useMemo, useState } from "react";
import { ManifestDraftControl } from "../components/ManifestDraftControl";
import { WholesaleRegulatoryHealth } from "../components/WholesaleRegulatoryHealth";
import { apiGet } from "../lib/api";
import "../wholesale-ops.css";

const CommerceStorefrontManager = lazy(() => import("../components/CommerceStorefrontManager").then(module => ({ default: module.CommerceStorefrontManager })));
const StorefrontSalesUnitManager = lazy(() => import("../components/StorefrontSalesUnitManager").then(module => ({ default: module.StorefrontSalesUnitManager })));
const OrdersPage = lazy(() => import("./OrdersPage").then(module => ({ default: module.OrdersPage })));
const WarehousePickPackPage = lazy(() => import("./WarehousePickPackPage").then(module => ({ default: module.WarehousePickPackPage })));
const WholesaleAccountingPanel = lazy(() => import("./WholesaleAccountingPanel").then(module => ({ default: module.WholesaleAccountingPanel })));

const WholesaleCRMPanel = lazy(() => import("./WholesaleCRMPanel").then(module => ({ default: module.WholesaleCRMPanel })));

type Tab = "pipeline" | "overview" | "inventory" | "orders" | "fulfillment" | "customers" | "accounting" | "storefront";
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
type PendingStorefrontOrder = {
  id:string;
  status:string;
  buyer_company?:string;
  buyer_contact?:string;
  buyer_email?:string;
  buyer_license?:string;
  estimated_subtotal?:number;
  created_at?:string|null;
  lines?:Array<{product_id:string;name?:string;quantity:number;unit?:string}>;
};
type StorefrontSnapshot = { storefront:{published:boolean}|null; pending_orders:PendingStorefrontOrder[] };
type OrderToCashException = {
  kind:"qa_hold"|"customer_ar_pending_order"|"low_margin_order"|"waiting_manifest"|"late_fulfillment"|"invoice_ar_handoff"|string;
  severity:"high"|"warning"|string;
  request_id?:string; order_id?:string; order_number?:string; customer?:string;
  message:string; next_action:string;
};
type OrderToCashOrder = {
  order_id:string; order_number:string; customer:string; order_status:string; payment_status:string; stage:string; next_action:string;
  order_value_usd:number; estimated_cost_usd:number; estimated_gross_margin_usd:number; estimated_gross_margin_pct:number|null;
  remaining_quantity:number; allocated_remaining_quantity:number; shipment_status:string; manifest_reference:string;
  invoice_status:string; invoice_balance_usd:number;
};
type WholesaleIntelligence = {
  summary:{
    order_to_cash_exceptions:number; qa_hold_orders:number; customer_ar_pending_orders:number;
    low_margin_orders:number; orders_waiting_manifest:number; late_fulfillment_orders:number; invoice_ar_handoff_orders:number;
  };
  order_to_cash_exceptions:OrderToCashException[];
  order_to_cash:{orders:OrderToCashOrder[];stage_counts:Record<string,number>};
};

const TABS:[Tab,string][] = [
  ["overview","Overview"],
  ["inventory","Inventory"],
  ["orders","Orders"],
  ["fulfillment","Fulfillment"],
  ["customers","Customers"],
  ["pipeline","Pipeline"],
  ["accounting","Accounting"],
  ["storefront","Storefront"],
];

function DeferredWorkspace({children}:{children:React.ReactNode}) {
  return <Suspense fallback={<div className="state">Loading workspace…</div>}>{children}</Suspense>;
}

export function WholesaleOpsPage({onNavigate}:{onNavigate:(page:string)=>void}) {
  const [tab,setTab]=useState<Tab>(() => new URLSearchParams(window.location.search).get("tab") === "customers" ? "customers" : "overview");
  const inventoryNeeded=tab==="overview"||tab==="inventory";
  const commercialNeeded=tab==="overview";
  const storefrontNeeded=tab==="overview"||tab==="storefront";
  const inventory=useQuery({
    queryKey:["wholesale-inventory"],
    queryFn:({signal})=>apiGet<WholesaleInventory>("/api/v1/storefronts/wholesale-inventory",signal),
    enabled:inventoryNeeded,
    staleTime:20_000,
  });
  const commercial=useQuery({
    queryKey:["commercial-workspace"],
    queryFn:({signal})=>apiGet<CommercialWorkspace>("/api/v1/commercial/workspace",signal),
    enabled:commercialNeeded,
    staleTime:30_000,
  });
  const storefront=useQuery({
    queryKey:["commerce-storefront"],
    queryFn:({signal})=>apiGet<StorefrontSnapshot>("/api/v1/storefronts",signal),
    enabled:storefrontNeeded,
    staleTime:15_000,
    refetchInterval:storefrontNeeded?30_000:false,
  });
  const intelligence=useQuery({
    queryKey:["wholesale-order-to-cash-intelligence"],
    queryFn:({signal})=>apiGet<WholesaleIntelligence>("/api/v1/storefronts/agent/snapshot",signal),
    enabled:tab==="overview",
    staleTime:15_000,
    refetchInterval:tab==="overview"?30_000:false,
  });
  const pendingOrders=(storefront.data?.pending_orders??[]).filter(row=>row.status==="submitted");
  const pendingStorefront=pendingOrders.length;
  const openSales=(commercial.data?.orders??[]).filter(row=>row.order_type==="sales"&&!["fulfilled","cancelled"].includes(row.status)).length;

  return <div className="page wholesale-ops-page">
    <div className="page-heading wholesale-hero">
      <div><div className="eyebrow">WHOLESALE OPS</div><h1>Sellable inventory to collected revenue.</h1><p>One commercial workspace for passed-COA inventory, wholesale orders, fulfillment, customers, accounting, and the hosted storefront.</p></div>
      <div className="wholesale-flow"><span>Production</span><b>→</b><span>Wholesale</span><b>→</b><span>Fulfillment</span><b>→</b><span>Accounting</span></div>
    </div>
    <div className="view-tabs parity-tabs wholesale-tabs" role="tablist">{TABS.map(([key,label])=><button key={key} role="tab" aria-selected={tab===key} className={tab===key?"active":""} onClick={()=>setTab(key)}>{label}{key==="storefront"&&pendingStorefront>0?<span className="status-pill" style={{marginLeft:8}}>{pendingStorefront}</span>:null}</button>)}</div>

    {tab==="overview"?<Overview inventory={inventory.data} commercial={commercial.data} intelligence={intelligence.data} pendingOrders={pendingOrders} openSales={openSales} storefrontLoading={storefront.isLoading} storefrontError={storefront.isError?storefront.error.message:""} intelligenceLoading={intelligence.isLoading} intelligenceError={intelligence.isError?intelligence.error.message:""} onTab={setTab}/>:null}
    {tab==="inventory"?<WholesaleInventoryPanel query={inventory}/>:null}
    {tab==="orders"?<DeferredWorkspace><OrdersPage/></DeferredWorkspace>:null}
    {tab==="fulfillment"?<DeferredWorkspace><WarehousePickPackPage onNavigate={page=>page==="Orders"?setTab("orders"):onNavigate(page)}/></DeferredWorkspace>:null}
    {tab==="customers"||tab==="pipeline"?<DeferredWorkspace><WholesaleCRMPanel key={tab} pipeline={tab==="pipeline"}/></DeferredWorkspace>:null}
    {tab==="accounting"?<DeferredWorkspace><WholesaleAccountingPanel onNavigate={onNavigate}/></DeferredWorkspace>:null}
    {tab==="storefront"?<DeferredWorkspace><StorefrontSalesUnitManager/><CommerceStorefrontManager/></DeferredWorkspace>:null}
  </div>;
}

function Overview({inventory,commercial,intelligence,pendingOrders,openSales,storefrontLoading,storefrontError,intelligenceLoading,intelligenceError,onTab}:{inventory:WholesaleInventory|undefined;commercial:CommercialWorkspace|undefined;intelligence:WholesaleIntelligence|undefined;pendingOrders:PendingStorefrontOrder[];openSales:number;storefrontLoading:boolean;storefrontError:string;intelligenceLoading:boolean;intelligenceError:string;onTab:(tab:Tab)=>void}) {
  const pendingStorefront=pendingOrders.length;
  return <>
    <section className="metrics wholesale-metrics">
      <Metric label="Sellable lots" value={inventory?.summary.sellable_lots??"—"} meta={`${inventory?.summary.bulk_lots??0} bulk · ${inventory?.summary.retail_ready_lots??0} retail ready`}/>
      <Metric label="Available to sell" value={inventory?number(inventory.summary.sellable_quantity):"—"} meta="After active reservations"/>
      <Metric label="Open sales orders" value={openSales} meta={commercial?money(commercial.metrics.open_sales_value):"Commercial order value"}/>
      <Metric label="Storefront approvals" value={pendingStorefront} meta="Public requests awaiting review"/>
      <Metric label="Fill rate" value={commercial?`${commercial.metrics.fill_rate_pct.toFixed(1)}%`:"—"} meta={`${commercial?.metrics.overdue_orders??0} overdue orders`}/>
      <Metric label="Order-to-cash exceptions" value={intelligence?.summary.order_to_cash_exceptions??"—"} meta={`${intelligence?.summary.orders_waiting_manifest??0} manifest · ${intelligence?.summary.invoice_ar_handoff_orders??0} invoice/A/R`}/>
    </section>
    <StorefrontApprovalQueue orders={pendingOrders} loading={storefrontLoading} error={storefrontError} onReview={()=>onTab("storefront")}/>
    <OrderToCashPipeline snapshot={intelligence} loading={intelligenceLoading} error={intelligenceError} onTab={onTab}/>
    <OrderToCashExceptions snapshot={intelligence} loading={intelligenceLoading} error={intelligenceError} onTab={onTab}/>
    <WholesaleRegulatoryHealth />
    <ManifestDraftControl />
    <section className="wholesale-action-grid">
      <Action title="Wholesale Inventory" note="Only released lots with a passed COA and positive uncommitted quantity are sellable." action="Review inventory" onClick={()=>onTab("inventory")}/>
      <Action title="Orders" note="Approved storefront, direct, and account orders converge into the same commercial sales-order engine." action="Work orders" onClick={()=>onTab("orders")}/>
      <Action title="Fulfillment" note="Allocate, scan, pick, pack, and ship against the actual package or lot selected for the order." action="Open fulfillment" onClick={()=>onTab("fulfillment")}/>
      <Action title="Customers" note="Keep retailer licenses, contacts, payment terms, and account relationships attached to the commercial record." action="View customers" onClick={()=>onTab("customers")}/>
      <Action title="Accounting" note="See A/R aging, invoice balances, payments, payment status, and QuickBooks synchronization in one wholesale control center." action="Open accounting" onClick={()=>onTab("accounting")}/>
      <Action title="Storefront" note="Review incoming storefront orders and manage what inventory customers can order." action={pendingStorefront?`Review ${pendingStorefront} pending`:"Manage storefront"} onClick={()=>onTab("storefront")}/>
    </section>
    {inventory?.summary.blocked_lots?<div className="info-banner"><strong>{inventory.summary.blocked_lots} inventory lot{inventory.summary.blocked_lots===1?" is":"s are"} intentionally excluded from wholesale.</strong><br/>Missing/failed COA, hold status, or fully committed inventory never flows into the sellable catalog.</div>:null}
  </>;
}

function StorefrontApprovalQueue({orders,loading,error,onReview}:{orders:PendingStorefrontOrder[];loading:boolean;error:string;onReview:()=>void}) {
  return <section className="inventory-panel storefront-approval-queue">
    <div className="page-heading" style={{marginBottom:12}}>
      <div><div className="eyebrow">NEEDS APPROVAL</div><h2>Pending Storefront Orders</h2><p className="section-note">Orders submitted from hosted storefronts land here before they become commercial sales orders or reserve inventory.</p></div>
      {orders.length?<button className="primary" type="button" onClick={onReview}>Review approvals</button>:null}
    </div>
    {loading?<div className="state">Checking for new storefront orders…</div>:null}
    {error?<div className="warning-banner">Storefront approval queue could not be loaded: {error}</div>:null}
    {!loading&&!error&&!orders.length?<div className="success-banner"><strong>No storefront orders are waiting for approval.</strong><br/><span>New customer submissions will appear here automatically.</span></div>:null}
    {orders.length?<div className="table-wrap"><table><thead><tr><th>Customer</th><th>Contact</th><th>License</th><th>Items</th><th>Estimated total</th><th>Submitted</th><th></th></tr></thead><tbody>{orders.slice(0,8).map(order=><tr key={order.id}><td><strong>{order.buyer_company||"Wholesale customer"}</strong><br/><small>{order.id.slice(0,8).toUpperCase()}</small></td><td>{order.buyer_contact||"—"}<br/><small>{order.buyer_email||"—"}</small></td><td>{order.buyer_license||"Not supplied"}</td><td>{order.lines?.length??0}</td><td><strong>{money(order.estimated_subtotal??0)}</strong></td><td>{dateTime(order.created_at)}</td><td><button className="secondary" type="button" onClick={onReview}>Review order</button></td></tr>)}</tbody></table></div>:null}
  </section>;
}

function OrderToCashPipeline({snapshot,loading,error,onTab}:{snapshot:WholesaleIntelligence|undefined;loading:boolean;error:string;onTab:(tab:Tab)=>void}) {
  const rows=snapshot?.order_to_cash?.orders??[];
  const target=(stage:string):Tab=>["confirmation_required","allocation_required"].includes(stage)?"orders":["invoice_required","invoice_send_required","ar_open","paid"].includes(stage)?"accounting":"fulfillment";
  const stageLabel=(stage:string)=>({
    confirmation_required:"Confirm order",allocation_required:"Allocate inventory",shipment_setup_required:"Create shipment",
    pick_pack:"Pick / pack",manifest_required:"Manifest required",ready_to_ship:"Ready to ship",
    fulfillment_in_progress:"Fulfillment in progress",fulfillment_reconciliation:"Reconcile fulfillment",
    invoice_required:"Invoice required",invoice_send_required:"Send invoice",ar_open:"A/R open",paid:"Paid",
  } as Record<string,string>)[stage]??stage.replaceAll("_"," ");
  return <section className="inventory-panel">
    <div className="page-heading" style={{marginBottom:12}}><div><div className="eyebrow">ORDER-TO-CASH PIPELINE</div><h2>Every open handoff in one sequence.</h2><p className="section-note">Derived from the canonical sales order, allocation, shipment, manifest, invoice, and payment records. Margin uses current product cost against the order price.</p></div></div>
    {loading?<div className="state">Building order-to-cash pipeline…</div>:null}
    {error?<div className="warning-banner">Order-to-cash pipeline could not be loaded: {error}</div>:null}
    {!loading&&!error&&!rows.length?<div className="info-banner">No wholesale sales orders are available for the continuity pipeline.</div>:null}
    {rows.length?<div className="table-wrap"><table><thead><tr><th>Order / Customer</th><th>Stage</th><th>Inventory handoff</th><th>Margin</th><th>Finance</th><th>Next action</th><th></th></tr></thead><tbody>{rows.slice(0,20).map(row=><tr key={row.order_id}><td><strong>{row.order_number}</strong><br/><small>{row.customer}</small></td><td><span className="status-pill">{stageLabel(row.stage)}</span><br/><small>{row.shipment_status?"Shipment: "+row.shipment_status.replaceAll("_"," "):"No shipment yet"}</small></td><td>{number(row.allocated_remaining_quantity)} allocated<br/><small>{number(row.remaining_quantity)} remaining{row.manifest_reference?" · "+row.manifest_reference:""}</small></td><td><strong>{row.estimated_gross_margin_pct==null?"—":row.estimated_gross_margin_pct.toFixed(1)+"%"}</strong><br/><small>{money(row.estimated_gross_margin_usd)} est. gross margin</small></td><td>{row.invoice_status?row.invoice_status.replaceAll("_"," "):"Not invoiced"}<br/><small>{row.invoice_balance_usd>0?money(row.invoice_balance_usd)+" open":row.payment_status.replaceAll("_"," ")}</small></td><td>{row.next_action}</td><td><button className="secondary" type="button" onClick={()=>onTab(target(row.stage))}>Open</button></td></tr>)}</tbody></table></div>:null}
  </section>;
}

function OrderToCashExceptions({snapshot,loading,error,onTab}:{snapshot:WholesaleIntelligence|undefined;loading:boolean;error:string;onTab:(tab:Tab)=>void}) {
  const rows=snapshot?.order_to_cash_exceptions??[];
  const target=(kind:string):Tab=>kind==="customer_ar_pending_order"||kind==="invoice_ar_handoff"?"accounting":kind==="low_margin_order"?"orders":"fulfillment";
  const label=(kind:string)=>({
    qa_hold:"QA hold",
    customer_ar_pending_order:"Customer A/R",
    low_margin_order:"Low margin",
    waiting_manifest:"Manifest",
    late_fulfillment:"Late fulfillment",
    invoice_ar_handoff:"Invoice / A/R",
  } as Record<string,string>)[kind]??kind.replaceAll("_"," ");
  return <section className="inventory-panel">
    <div className="page-heading" style={{marginBottom:12}}>
      <div><div className="eyebrow">DOOBIE CONTINUITY</div><h2>Order-to-cash exceptions</h2><p className="section-note">One view across approval, inventory, fulfillment, manifest readiness, invoicing, and A/R. These are deterministic operational checks, not model guesses.</p></div>
    </div>
    {loading?<div className="state">Checking order-to-cash continuity…</div>:null}
    {error?<div className="warning-banner">Order-to-cash continuity could not be loaded: {error}</div>:null}
    {!loading&&!error&&!rows.length?<div className="success-banner"><strong>No order-to-cash exceptions need attention.</strong><br/><span>Current sales orders are clear across the continuity checks.</span></div>:null}
    {rows.length?<div className="table-wrap"><table><thead><tr><th>Priority</th><th>Order / Customer</th><th>Exception</th><th>Next action</th><th></th></tr></thead><tbody>{rows.slice(0,12).map((row,index)=><tr key={`${row.kind}-${row.order_id||row.request_id||index}`}><td><span className={row.severity==="high"?"warning-text":"status-pill"}>{row.severity==="high"?"High":"Review"}</span></td><td><strong>{row.order_number||"Pending request"}</strong><br/><small>{row.customer||"Wholesale customer"}</small></td><td><strong>{label(row.kind)}</strong><br/><small>{row.message}</small></td><td>{row.next_action}</td><td><button className="secondary" type="button" onClick={()=>onTab(target(row.kind))}>Open</button></td></tr>)}</tbody></table></div>:null}
  </section>;
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

function Metric({label,value,meta}:{label:string;value:string|number;meta:string}){return <article className="metric"><span>{label}</span><strong>{value}</strong><small>{meta}</small></article>}
function Action({title,note,action,onClick}:{title:string;note:string;action:string;onClick:()=>void}){return <article className="inventory-panel wholesale-action"><div><h3>{title}</h3><p>{note}</p></div><button className="secondary" onClick={onClick}>{action}</button></article>}
function number(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:2})}
function money(value:number){return Number(value||0).toLocaleString(undefined,{style:"currency",currency:"USD",maximumFractionDigits:0})}
function dateTime(value:string|null|undefined){if(!value)return"—";const date=new Date(value);return Number.isNaN(date.getTime())?String(value):date.toLocaleString()}
