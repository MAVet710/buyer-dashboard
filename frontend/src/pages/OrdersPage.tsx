import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { InventoryAudits } from "../components/InventoryAudits";
import { StreamlitDialog } from "../components/StreamlitDialog";
import { apiGet, apiPost } from "../lib/api";

type Tab = "command" | "new" | "execute" | "partners" | "audits" | "ledger";
type Partner = {id:string;name:string;partner_type:string;license_or_registration:string;contact_name:string;contact_email:string;contact_phone:string;payment_terms:string;active:boolean};
type Product = {id:string;sku:string;name:string;item_type:string;base_unit:string;unit_cost:number};
type Order = {id:string;partner_id:string;order_number:string;order_type:string;order_date:string;due_at:string|null;status:string;payment_status:string;external_reference:string;notes:string;partner_name:string;order_total:number;requested_quantity:number;fulfilled_quantity:number};
type Line = {id:string;commercial_order_id:string;product_id:string;position:number;description:string;sku_snapshot:string;quantity:number;unit:string;unit_price:number;fulfilled_quantity:number;notes:string};
type Lot = {id:string;product_id:string;lot_code:string;compliance_package_id:string;location_code:string;status:string;product_name:string;on_hand:number};
type Transaction = {id:string;occurred_at:string;order:string;type:string;product_name:string;lot:string;quantity:number;unit:string;reference:string;actor:string};
type Workspace = {facility_name:string;metrics:{inventory_value:number;open_sales_value:number;open_purchase_value:number;open_orders:number;overdue_orders:number;fill_rate_pct:number;tracked_lots:number;inventory_exceptions:number};partners:Partner[];orders:Order[];lines:Line[];products:Product[];lots:Lot[];inventory_exceptions:{lot_code:string;product_name:string;on_hand:number;status:string}[];transactions:Transaction[]};
type Detail = {order:Order;lines:Line[];allocations:{id:string;commercial_order_line_id:string;lot_id:string;quantity:number;fulfilled_quantity:number;status:string}[]};
type DraftLine = {product_id:string;quantity:number;unit_price:number;notes:string};
type Invoice = {id:string;invoice_number:string;status:string;issue_date:string;due_date:string;total_usd:number;balance_usd:number};
type Shipment = {id:string;shipment_number:string;status:string;manifest_reference:string;carrier:string;tracking_reference:string};
type FinanceDetail = Detail & {invoices:Invoice[];shipments:Shipment[]};
type Ar = {total_ar:number;buckets:{current:number;"1_30":number;"31_60":number;"61_90":number;"90_plus":number};invoices:Record<string,unknown>[]};

const OPEN = new Set(["draft","confirmed","allocated","partially_fulfilled"]);
const TAB_LABELS:[Tab,string][]=[["command","Command Center"],["new","New Order"],["execute","Allocate & Fulfill"],["partners","Trade Partners"],["audits","Inventory Audits"],["ledger","Inventory Ledger"]];

export function OrdersPage(){
  const [tab,setTab]=useState<Tab>("command");
  const [financeOpen,setFinanceOpen]=useState(false);
  const client=useQueryClient();
  const workspace=useQuery({queryKey:["commercial-workspace"],queryFn:({signal})=>apiGet<Workspace>("/api/v1/commercial/workspace",signal)});
  const refresh=()=>client.invalidateQueries({queryKey:["commercial-workspace"]});
  const data=workspace.data;
  return <div className="page commercial-workspace">
    <div className="heading-actions commercial-quick-action"><button className="primary" onClick={()=>setFinanceOpen(true)}>Wholesale + Finance</button></div>
    <div className="commercial-header"><div><div className="commercial-eyebrow">Commercial operations</div><h1 className="commercial-title">Orders, inventory, and fulfillment</h1><p className="commercial-subtitle">One durable flow from purchase order to receipt, reservation, shipment, and payment.</p></div><span className="commercial-live">{data?.facility_name??"Active facility"}</span></div>
    <div className="view-tabs parity-tabs" role="tablist">{TAB_LABELS.map(([key,label])=><button key={key} role="tab" aria-selected={tab===key} className={tab===key?"active":""} onClick={()=>setTab(key)}>{label}</button>)}</div>
    {workspace.isError?<div className="state error">Commercial data could not be loaded: {workspace.error.message}</div>:null}
    {!data&&!workspace.isError?<div className="state">Loading commercial operations…</div>:null}
    {data&&tab==="command"?<CommandCenter data={data}/>:null}
    {data&&tab==="new"?<NewOrder data={data} onSaved={refresh}/>:null}
    {data&&tab==="execute"?<Execution data={data} onSaved={refresh}/>:null}
    {data&&tab==="partners"?<TradePartners data={data} onSaved={refresh}/>:null}
    {data&&tab==="audits"?<InventoryAudits embedded operation="production"/>:null}
    {data&&tab==="ledger"?<Ledger rows={data.transactions}/>:null}
    {data?<WholesaleFinance open={financeOpen} onClose={()=>setFinanceOpen(false)} data={data}/>:null}
  </div>;
}

function CommandCenter({data}:{data:Workspace}){
  const [search,setSearch]=useState("");
  const needle=search.trim().toLowerCase();
  const allOpen=data.orders.filter(row=>OPEN.has(row.status));
  const open=allOpen.filter(row=>!needle||[row.order_number,row.partner_name,row.external_reference,row.status].join(" ").toLowerCase().includes(needle));
  const incoming=open.filter(row=>row.order_type==="purchase");
  const outgoing=open.filter(row=>row.order_type==="sales");
  const overdue=open.filter(row=>row.due_at&&new Date(row.due_at).getTime()<startToday().getTime());
  return <>
    <section className="metrics commercial-metrics"><Metric label="Active inventory" value={money(data.metrics.inventory_value)} meta={`${data.metrics.tracked_lots} tracked lots`}/><Metric label="Open sales" value={money(data.metrics.open_sales_value)} meta={`${allOpen.filter(row=>row.order_type==="sales").length} orders`}/><Metric label="Open purchases" value={money(data.metrics.open_purchase_value)} meta={`${allOpen.filter(row=>row.order_type==="purchase").length} orders`}/><Metric label="Fill rate" value={`${data.metrics.fill_rate_pct.toFixed(1)}%`} meta="Across all order lines"/><Metric label="Exceptions" value={data.metrics.overdue_orders+data.metrics.inventory_exceptions} meta={`${data.metrics.overdue_orders} overdue`}/></section>
    <label className="inventory-search commercial-search"><span>Search orders</span><input value={search} placeholder="Order number, partner, reference, or status" onChange={event=>setSearch(event.target.value)}/></label>
    <section className="three-column-grid commercial-board"><OrderColumn title="Incoming purchase orders" note="Receipts expected from vendors" empty="No open purchase orders." rows={incoming}/><OrderColumn title="Outgoing sales orders" note="Customer demand awaiting shipment" empty="No open sales orders." rows={outgoing}/><div><h3>Inventory & due-date exceptions</h3><p className="section-note">Items needing an operator decision</p>{!overdue.length&&!data.inventory_exceptions.length?<div className="success-banner">No active exceptions.</div>:null}{overdue.slice(0,5).map(row=><OrderCard row={row} key={row.id}/>)}{data.inventory_exceptions.slice(0,5).map(row=><div className="warning-banner" key={row.lot_code}>{row.product_name} · lot {row.lot_code} · {number(row.on_hand)} on hand</div>)}</div></section>
  </>;
}

function OrderColumn({title:heading,note,empty,rows}:{title:string;note:string;empty:string;rows:Order[]}){return <div><h3>{heading}</h3><p className="section-note">{note}</p>{!rows.length?<div className="info-banner">{empty}</div>:null}{rows.slice(0,8).map(row=><OrderCard row={row} key={row.id}/>)}</div>}
function OrderCard({row}:{row:Order}){return <article className="commercial-order-card"><div><strong>{row.order_number}</strong><span className="status-pill">{title(row.status)}</span></div><p>{row.partner_name}</p><small>{money(row.order_total)} · Due {row.due_at?new Date(row.due_at).toLocaleDateString(undefined,{month:"short",day:"2-digit"}):"No due date"} · {number(row.fulfilled_quantity)} / {number(row.requested_quantity)} fulfilled</small></article>}

function NewOrder({data,onSaved}:{data:Workspace;onSaved:()=>void}){
  const today=dateValue(0), due=dateValue(7);
  const firstSalesPartner=data.partners.find(row=>["customer","both"].includes(row.partner_type))?.id??"";
  const [form,setForm]=useState({order_type:"sales",partner_id:firstSalesPartner,order_number:`SO-${compactDate(today)}-`,order_date:today,due_date:due,external_reference:"",notes:""});
  const [validation,setValidation]=useState("");
  const [lines,setLines]=useState<DraftLine[]>(()=>data.products[0]?[{product_id:data.products[0].id,quantity:1,unit_price:data.products[0].unit_cost,notes:""}]:[]);
  const eligible=data.partners.filter(row=>row.partner_type===(form.order_type==="sales"?"customer":"vendor")||row.partner_type==="both");
  const save=useMutation({mutationFn:()=>apiPost("/api/v1/commercial/orders",{...form,lines:lines.map(line=>{const product=data.products.find(row=>row.id===line.product_id);return{...line,unit:product?.base_unit??"unit",description:product?.name??""}})}),onSuccess:()=>{setForm({...form,partner_id:eligible[0]?.id??"",external_reference:"",notes:""});setLines(data.products[0]?[{product_id:data.products[0].id,quantity:1,unit_price:data.products[0].unit_cost,notes:""}]:[]);setValidation("");onSaved();}});
  function changeType(value:string){const prefix=value==="sales"?"SO":"PO";const relation=value==="sales"?"customer":"vendor";const first=data.partners.find(row=>row.partner_type===relation||row.partner_type==="both");setForm({...form,order_type:value,partner_id:first?.id??"",order_number:`${prefix}-${compactDate(today)}-`});setValidation("")}
  function changeLine(index:number,change:Partial<DraftLine>){setLines(rows=>rows.map((row,i)=>i===index?{...row,...change}:row))}
  return <section className="inventory-panel"><h2>Create an order</h2><p>Capture the header and line items together. The order remains a draft until you confirm it.</p>{!data.partners.length||!data.products.length?<div className="info-banner">Create at least one trade partner and one product before entering an order.</div>:<>
    <div className="form-grid three"><label>Order type<select value={form.order_type} onChange={event=>changeType(event.target.value)}><option value="sales">Sales</option><option value="purchase">Purchase</option></select></label>{eligible.length?<label>{form.order_type==="sales"?"Customer":"Vendor"}<select value={form.partner_id} onChange={event=>setForm({...form,partner_id:event.target.value})}>{eligible.map(row=><option value={row.id} key={row.id}>{row.name}</option>)}</select></label>:<div/>}<label>Order number<input value={form.order_number} onChange={event=>setForm({...form,order_number:event.target.value})}/></label><label>Order date<input type="date" value={form.order_date} onChange={event=>setForm({...form,order_date:event.target.value})}/></label><label>Due date<input type="date" value={form.due_date} onChange={event=>setForm({...form,due_date:event.target.value})}/></label><label>External reference<input value={form.external_reference} placeholder="METRC, vendor, or customer ref" onChange={event=>setForm({...form,external_reference:event.target.value})}/></label></div>
    <div className="table-wrap"><table><thead><tr><th>Product</th><th>Quantity</th><th>Unit Price</th><th>Line notes</th><th></th></tr></thead><tbody>{lines.map((line,index)=>{const product=data.products.find(row=>row.id===line.product_id);return <tr key={index}><td><select value={line.product_id} onChange={event=>{const next=data.products.find(row=>row.id===event.target.value);changeLine(index,{product_id:event.target.value,unit_price:next?.unit_cost??0})}}>{data.products.map(row=><option value={row.id} key={row.id}>{row.sku} · {row.name}</option>)}</select></td><td><input type="number" min="0.01" step="1" value={line.quantity} onChange={event=>changeLine(index,{quantity:Number(event.target.value)})}/></td><td><input type="number" min="0" step="0.01" value={line.unit_price} onChange={event=>changeLine(index,{unit_price:Number(event.target.value)})}/></td><td><input value={line.notes} onChange={event=>changeLine(index,{notes:event.target.value})}/></td><td><button className="secondary" aria-label={`Remove ${product?.name??"line"}`} onClick={()=>setLines(rows=>rows.filter((_,i)=>i!==index))}>Remove</button></td></tr>})}</tbody></table></div>
    <button className="secondary" onClick={()=>data.products[0]&&setLines(rows=>[...rows,{product_id:data.products[0].id,quantity:1,unit_price:data.products[0].unit_cost,notes:""}])}>Add row</button><label className="full-field">Order notes<textarea value={form.notes} placeholder="Shipping requirements, terms, or internal handoff notes" onChange={event=>setForm({...form,notes:event.target.value})}/></label><button className="primary submit" disabled={save.isPending} onClick={()=>{if(!eligible.length){setValidation(`No eligible ${form.order_type==="sales"?"customer":"vendor"} exists.`);return}save.mutate()}}>Create draft order</button>{validation?<div className="form-error">{validation}</div>:null}{save.isError?<div className="form-error">Order could not be created: {save.error.message}</div>:null}{save.isSuccess?<div className="success-banner">{form.order_number.trim().toUpperCase()} was created as a draft.</div>:null}
  </>}</section>;
}

function Execution({data,onSaved}:{data:Workspace;onSaved:()=>void}){
  const open=data.orders.filter(row=>OPEN.has(row.status));
  const [selected,setSelected]=useState("");
  const orderId=selected||open[0]?.id||"";
  const detail=useQuery({queryKey:["commercial-order",orderId],queryFn:({signal})=>apiGet<Detail>(`/api/v1/commercial/orders/${orderId}`,signal),enabled:Boolean(orderId)});
  const refresh=()=>{detail.refetch();onSaved()};
  if(!open.length)return <div className="info-banner">There are no open orders to fulfill.</div>;
  return <section className="inventory-panel"><label>Open order<select value={orderId} onChange={event=>setSelected(event.target.value)}>{open.map(row=><option value={row.id} key={row.id}>{row.order_number} · {title(row.order_type)} · {title(row.status)}</option>)}</select></label>{detail.isError?<div className="form-error">Order could not be loaded: {detail.error.message}</div>:detail.data?<ExecutionDetail key={`${orderId}-${detail.data.order.status}`} data={data} detail={detail.data} onSaved={refresh}/>:<div className="state">Loading order…</div>}</section>;
}

function ExecutionDetail({data,detail,onSaved}:{data:Workspace;detail:Detail;onSaved:()=>void}){
  const order=detail.order;
  const [payment,setPayment]=useState(order.payment_status);
  const action=useMutation({mutationFn:(name:string)=>apiPost(`/api/v1/commercial/orders/${order.id}/actions/${name}`,{}),onSuccess:onSaved});
  const updatePayment=useMutation({mutationFn:()=>apiPost(`/api/v1/commercial/orders/${order.id}/payment`,{payment_status:payment}),onSuccess:onSaved});
  return <><DataTable rows={detail.lines.map(line=>({Line:line.position,Product:data.products.find(row=>row.id===line.product_id)?.name??line.description,Ordered:line.quantity,Fulfilled:line.fulfilled_quantity,Remaining:Math.max(0,line.quantity-line.fulfilled_quantity),Unit:line.unit,Price:line.unit_price}))}/><div className="form-grid three commercial-order-actions"><div>{order.status==="draft"?<button className="primary" onClick={()=>action.mutate("confirm")}>Confirm order</button>:null}</div><div><label>Payment<select value={payment} onChange={event=>setPayment(event.target.value)}>{["not_invoiced","draft","sent","partial","paid","overdue"].map(value=><option value={value} key={value}>{title(value)}</option>)}</select></label>{payment!==order.payment_status?<button className="secondary" onClick={()=>updatePayment.mutate()}>Update payment</button>:null}</div><button className="secondary" onClick={()=>action.mutate("cancel")}>Cancel order</button></div>{action.isError||updatePayment.isError?<div className="form-error">{action.error?.message??updatePayment.error?.message}</div>:null}{order.status==="draft"?<div className="info-banner">Confirm this order to allocate or fulfill it.</div>:<Fulfillment data={data} detail={detail} onSaved={onSaved}/>}</>;
}

function Fulfillment({data,detail,onSaved}:{data:Workspace;detail:Detail;onSaved:()=>void}){
  const remaining=detail.lines.filter(row=>row.fulfilled_quantity<row.quantity-1e-9);
  const [lineId,setLineId]=useState(remaining[0]?.id??"");
  const line=remaining.find(row=>row.id===lineId)??remaining[0];
  const lots=data.lots.filter(row=>row.product_id===line?.product_id);
  const [lotId,setLotId]=useState(lots[0]?.id??"");
  const [quantity,setQuantity]=useState(line?Math.min(1,line.quantity-line.fulfilled_quantity):0);
  const [reference,setReference]=useState(detail.order.external_reference||detail.order.order_number);
  const [lotForm,setLotForm]=useState({lot_code:"",location:"RECEIVING"});
  const createLot=useMutation({mutationFn:()=>apiPost("/api/v1/commercial/inventory-lots",{...lotForm,product_id:line?.product_id,unit:line?.unit}),onSuccess:onSaved});
  const reserve=useMutation({mutationFn:()=>apiPost(`/api/v1/commercial/order-lines/${line?.id}/allocations`,{lot_id:lotId||lots[0]?.id,quantity}),onSuccess:onSaved});
  const post=useMutation({mutationFn:()=>apiPost(`/api/v1/commercial/order-lines/${line?.id}/fulfill`,{lot_id:lotId||lots[0]?.id,quantity,reference}),onSuccess:onSaved});
  if(!remaining.length)return <div className="success-banner">All order lines are fulfilled.</div>;
  if(detail.order.order_type==="purchase"&&!lots.length)return <div className="streamlit-form"><strong>Create the receiving lot</strong><label>Lot / package code<input value={lotForm.lot_code} onChange={event=>setLotForm({...lotForm,lot_code:event.target.value})}/></label><label>Location<input value={lotForm.location} onChange={event=>setLotForm({...lotForm,location:event.target.value})}/></label><button className="secondary" onClick={()=>createLot.mutate()}>Create receiving lot</button>{createLot.isSuccess?<div className="success-banner">Receiving lot created.</div>:null}{createLot.isError?<div className="form-error">{createLot.error.message}</div>:null}</div>;
  if(!lots.length)return <div className="warning-banner">No matching inventory lot is available for this product.</div>;
  const selectedLot=lotId||lots[0].id;
  const reserved=detail.allocations.filter(row=>row.commercial_order_line_id===line.id&&row.lot_id===selectedLot&&["reserved","partial"].includes(row.status)).reduce((sum,row)=>sum+row.quantity-row.fulfilled_quantity,0);
  return <div className="production-controls"><label>Line to process<select value={line.id} onChange={event=>{const next=remaining.find(row=>row.id===event.target.value);setLineId(event.target.value);setLotId("");setQuantity(next?Math.min(1,next.quantity-next.fulfilled_quantity):0)}}>{remaining.map(row=><option value={row.id} key={row.id}>{row.position}. {data.products.find(product=>product.id===row.product_id)?.name??row.description} · {number(row.quantity-row.fulfilled_quantity)} remaining</option>)}</select></label><label>Inventory lot<select value={selectedLot} onChange={event=>setLotId(event.target.value)}>{lots.map(row=><option value={row.id} key={row.id}>{row.lot_code} · {number(row.on_hand)} {line.unit} on hand</option>)}</select></label><label>Quantity<input type="number" min="0.0001" max={Math.max(.0001,line.quantity-line.fulfilled_quantity)} value={quantity} onChange={event=>setQuantity(Number(event.target.value))}/></label><label>Fulfillment reference<input value={reference} onChange={event=>setReference(event.target.value)}/></label>{detail.order.order_type==="sales"?<><div className="audit-actions"><button className="primary" onClick={()=>reserve.mutate()}>Reserve lot</button><button className="secondary" disabled={reserved+1e-9<quantity} onClick={()=>post.mutate()}>Post shipment</button></div><p className="section-note">{number(reserved)} {line.unit} currently reserved from this lot.</p></>:<button className="primary submit" onClick={()=>post.mutate()}>Post receipt</button>}{reserve.isSuccess?<div className="success-banner">Inventory reserved.</div>:null}{post.isSuccess?<div className="success-banner">{detail.order.order_type==="sales"?"Shipment posted to the immutable inventory ledger.":"Receipt posted to inventory."}</div>:null}{reserve.isError||post.isError?<div className="form-error">{reserve.error?.message??post.error?.message}</div>:null}</div>;
}

function TradePartners({data,onSaved}:{data:Workspace;onSaved:()=>void}){
  const [form,setForm]=useState({name:"",partner_type:"customer",license_or_registration:"",contact_name:"",contact_email:"",contact_phone:"",payment_terms:"Due on receipt"});
  const save=useMutation({mutationFn:()=>apiPost<Partner>("/api/v1/commercial/partners",form),onSuccess:()=>{setForm({...form,name:"",license_or_registration:"",contact_name:"",contact_email:"",contact_phone:""});onSaved()}});
  return <section className="two-column-grid"><div className="inventory-panel"><h2>Add trade partner</h2><label>Business name<input value={form.name} onChange={event=>setForm({...form,name:event.target.value})}/></label><label>Relationship<select value={form.partner_type} onChange={event=>setForm({...form,partner_type:event.target.value})}><option value="customer">Customer</option><option value="vendor">Vendor</option><option value="both">Both</option></select></label><Field label="License / registration" value={form.license_or_registration} onChange={value=>setForm({...form,license_or_registration:value})}/><Field label="Primary contact" value={form.contact_name} onChange={value=>setForm({...form,contact_name:value})}/><Field label="Email" value={form.contact_email} onChange={value=>setForm({...form,contact_email:value})}/><Field label="Phone" value={form.contact_phone} onChange={value=>setForm({...form,contact_phone:value})}/><label>Default terms<select value={form.payment_terms} onChange={event=>setForm({...form,payment_terms:event.target.value})}>{["Due on receipt","Net 7","Net 15","Net 30","Net 45","Net 60"].map(value=><option key={value}>{value}</option>)}</select></label><button className="primary submit" disabled={save.isPending} onClick={()=>save.mutate()}>Create partner</button>{save.isError?<div className="form-error">{save.error.message}</div>:null}{save.data?<div className="success-banner">{save.data.name} was added.</div>:null}</div><div className="inventory-panel"><h2>Partner directory</h2><DataTable rows={data.partners.map(row=>({Business:row.name,Type:title(row.partner_type),License:row.license_or_registration,Contact:row.contact_name,Email:row.contact_email,Phone:row.contact_phone,Terms:row.payment_terms}))}/></div></section>;
}

function WholesaleFinance({open,onClose,data}:{open:boolean;onClose:()=>void;data:Workspace}){
  const sales=data.orders.filter(row=>row.order_type==="sales");
  const [selected,setSelected]=useState("");
  const orderId=selected||sales[0]?.id||"";
  const ar=useQuery({queryKey:["commercial-ar"],queryFn:({signal})=>apiGet<Ar>("/api/v1/commercial/ar",signal),enabled:open});
  const detail=useQuery({queryKey:["commercial-finance-order",orderId],queryFn:({signal})=>apiGet<FinanceDetail>(`/api/v1/commercial/orders/${orderId}`,signal),enabled:open&&Boolean(orderId)});
  const client=useQueryClient();
  const refresh=()=>{detail.refetch();ar.refetch();client.invalidateQueries({queryKey:["commercial-workspace"]})};
  const selectedOrder=sales.find(row=>row.id===orderId);
  return <StreamlitDialog open={open} onClose={onClose} title="Wholesale + Finance">
    <div className="finance-workspace"><h2>Wholesale + Finance</h2><p>Order → allocation → shipment → invoice → payment, without leaving the commercial workflow.</p>
    <section className="metrics five"><Metric label="Sales Orders" value={sales.length} meta="Current facility"/><Metric label="A/R" value={money0(ar.data?.total_ar??0)} meta="Open balance"/><Metric label="Current" value={money0(ar.data?.buckets.current??0)} meta="Not past due"/><Metric label="1–30" value={money0(ar.data?.buckets["1_30"]??0)} meta="Days past due"/><Metric label="31+" value={money0((ar.data?.buckets["31_60"]??0)+(ar.data?.buckets["61_90"]??0)+(ar.data?.buckets["90_plus"]??0))} meta="Days past due"/></section>
    {ar.isError?<div className="form-error">Finance summary could not be loaded: {ar.error.message}</div>:null}{ar.data?.invoices.length?<DataTable rows={ar.data.invoices}/>:null}
    {!sales.length?<div className="info-banner">Create a sales order first.</div>:<><label>Open order finance<select value={orderId} onChange={event=>setSelected(event.target.value)}>{sales.map(row=><option value={row.id} key={row.id}>{row.order_number} · {title(row.status)} · {title(row.payment_status)}</option>)}</select></label>{detail.isError?<div className="form-error">Order finance could not be loaded: {detail.error.message}</div>:selectedOrder&&detail.data?<FinanceOrder key={orderId} order={selectedOrder} detail={detail.data} data={data} onSaved={refresh}/>:<div className="state">Loading order finance…</div>}</>}
    </div>
  </StreamlitDialog>;
}

function FinanceOrder({order,detail,data,onSaved}:{order:Order;detail:FinanceDetail;data:Workspace;onSaved:()=>void}){
  const [shipment,setShipment]=useState({shipment_number:`SHP-${order.order_number}`,manifest_reference:"",carrier:""});
  const firstShipment=detail.shipments[0];
  const [shipmentStatus,setShipmentStatus]=useState(firstShipment?.status??"planned");
  const [invoiceNumber,setInvoiceNumber]=useState(`INV-${order.order_number}`);
  const [terms,setTerms]=useState(30);
  const firstInvoice=detail.invoices[0];
  const [payment,setPayment]=useState(firstInvoice?.balance_usd??0);
  const [method,setMethod]=useState("ach");
  const [reference,setReference]=useState("");
  const customerOptions=data.partners.filter(row=>["customer","both"].includes(row.partner_type));
  const productIds=new Set(detail.lines.map(row=>row.product_id));
  const productOptions=data.products.filter(row=>productIds.has(row.id));
  const [price,setPrice]=useState({partner_id:customerOptions[0]?.id??"",product_id:productOptions[0]?.id??"",price_usd:0,discount_pct:0});
  const createShipment=useMutation({mutationFn:()=>apiPost(`/api/v1/commercial/orders/${order.id}/shipments`,shipment),onSuccess:onSaved});
  const updateShipment=useMutation({mutationFn:()=>apiPost(`/api/v1/commercial/shipments/${firstShipment?.id}/status`,{status:shipmentStatus}),onSuccess:onSaved});
  const createInvoice=useMutation({mutationFn:()=>apiPost(`/api/v1/commercial/orders/${order.id}/invoices`,{invoice_number:invoiceNumber,due_days:terms}),onSuccess:onSaved});
  const sendInvoice=useMutation({mutationFn:()=>apiPost(`/api/v1/commercial/invoices/${firstInvoice?.id}/send`,{}),onSuccess:onSaved});
  const postPayment=useMutation({mutationFn:()=>apiPost(`/api/v1/commercial/invoices/${firstInvoice?.id}/payments`,{amount_usd:payment,method,reference,payment_date:dateValue(0)}),onSuccess:onSaved});
  const savePrice=useMutation({mutationFn:()=>apiPost("/api/v1/commercial/customer-prices",price)});
  return <div className="finance-order"><h3>{order.order_number}</h3><div className="two-column-grid finance-popovers"><details className="streamlit-expander inline-popover"><summary>Shipment / manifest</summary><div className="streamlit-expander-body">{detail.shipments.length?<DataTable rows={detail.shipments.map(row=>({Shipment:row.shipment_number,Status:row.status,Manifest:row.manifest_reference,Carrier:row.carrier,Tracking:row.tracking_reference}))}/>:null}<Field label="Shipment number" value={shipment.shipment_number} onChange={value=>setShipment({...shipment,shipment_number:value})}/><Field label="State manifest reference" value={shipment.manifest_reference} onChange={value=>setShipment({...shipment,manifest_reference:value})}/><Field label="Carrier / route" value={shipment.carrier} onChange={value=>setShipment({...shipment,carrier:value})}/><button className="primary" onClick={()=>createShipment.mutate()}>Create shipment</button>{firstShipment?<><label>Shipment status<select value={shipmentStatus} onChange={event=>setShipmentStatus(event.target.value)}>{["planned","picking","packed","manifested","shipped","delivered","cancelled"].map(value=><option key={value}>{value}</option>)}</select></label><button className="secondary" onClick={()=>updateShipment.mutate()}>Update shipment</button></>:null}<MutationMessage mutations={[createShipment,updateShipment]}/></div></details><details className="streamlit-expander inline-popover"><summary>Invoice / payment</summary><div className="streamlit-expander-body">{detail.invoices.length?<DataTable rows={detail.invoices.map(row=>({Invoice:row.invoice_number,Status:row.status,Total:row.total_usd,Balance:row.balance_usd,Due:row.due_date}))}/>:null}<Field label="Invoice number" value={invoiceNumber} onChange={setInvoiceNumber}/><label>Due in days<input type="number" min="0" max="180" step="1" value={terms} onChange={event=>setTerms(Number(event.target.value))}/></label><button className="primary" onClick={()=>createInvoice.mutate()}>Create invoice from order</button>{firstInvoice?.status==="draft"?<button className="secondary" onClick={()=>sendInvoice.mutate()}>Mark invoice sent</button>:null}{firstInvoice&&firstInvoice.balance_usd>0?<><label>Payment<input type="number" min="0" max={firstInvoice.balance_usd} step="1" value={payment} onChange={event=>setPayment(Number(event.target.value))}/></label><label>Method<select value={method} onChange={event=>setMethod(event.target.value)}>{["ach","check","cash","card","other"].map(value=><option key={value}>{value}</option>)}</select></label><Field label="Reference" value={reference} onChange={setReference}/><button className="primary" onClick={()=>postPayment.mutate()}>Post payment</button></>:null}<MutationMessage mutations={[createInvoice,sendInvoice,postPayment]}/></div></details></div><details className="streamlit-expander inline-popover"><summary>Customer-specific pricing</summary>{customerOptions.length&&productOptions.length?<div className="streamlit-expander-body"><label>Customer<select value={price.partner_id} onChange={event=>setPrice({...price,partner_id:event.target.value})}>{customerOptions.map(row=><option value={row.id} key={row.id}>{row.name}</option>)}</select></label><label>Product<select value={price.product_id} onChange={event=>setPrice({...price,product_id:event.target.value})}>{productOptions.map(row=><option value={row.id} key={row.id}>{row.name} · {row.sku}</option>)}</select></label><label>Fixed wholesale price<input type="number" min="0" step="0.5" value={price.price_usd} onChange={event=>setPrice({...price,price_usd:Number(event.target.value)})}/></label><label>Or discount %<input type="number" min="0" max="100" step="0.5" value={price.discount_pct} onChange={event=>setPrice({...price,discount_pct:Number(event.target.value)})}/></label><button className="primary" onClick={()=>savePrice.mutate()}>Save price rule</button>{savePrice.isSuccess?<div className="success-banner">Customer pricing saved.</div>:null}<MutationMessage mutations={[savePrice]}/></div>:null}</details></div>;
}

function MutationMessage({mutations}:{mutations:{isError:boolean;error:Error|null}[]}){const failed=mutations.find(row=>row.isError);return failed?<div className="form-error">{failed.error?.message}</div>:null}

function Ledger({rows}:{rows:Transaction[]}){return <section className="inventory-panel"><h2>Commercial inventory ledger</h2><p>Receipts and shipments are append-only. Inventory is derived from these signed movements.</p>{rows.length?<><DataTable rows={rows.map(row=>({Occurred:row.occurred_at,Order:row.order,Type:row.type,"Product Name":row.product_name,Lot:row.lot,Quantity:row.quantity,Unit:row.unit,Reference:row.reference,Actor:row.actor}))}/><button className="secondary" onClick={()=>downloadCsv(rows)}>Export ledger CSV</button></>:<div className="info-banner">No commercial receipts or shipments have been posted yet.</div>}</section>}
function DataTable({rows}:{rows:Record<string,unknown>[]}){const columns=rows[0]?Object.keys(rows[0]):[];return <div className="table-wrap"><table><thead><tr>{columns.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{columns.map(column=><td key={column}>{show(row[column])}</td>)}</tr>)}</tbody></table></div>}
function Metric({label,value,meta}:{label:string;value:string|number;meta:string}){return <article className="metric commercial-kpi"><span>{label}</span><strong>{value}</strong><small>{meta}</small></article>}
function Field({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}){return <label>{label}<input value={value} onChange={event=>onChange(event.target.value)}/></label>}
function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function money(value:number){return Number(value||0).toLocaleString(undefined,{style:"currency",currency:"USD",minimumFractionDigits:2,maximumFractionDigits:2})}
function money0(value:number){return Number(value||0).toLocaleString(undefined,{style:"currency",currency:"USD",minimumFractionDigits:0,maximumFractionDigits:0})}
function number(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:2})}
function show(value:unknown){if(value==null||value==="")return "—";if(typeof value==="number")return number(value);return String(value)}
function startToday(){const now=new Date();return new Date(now.getFullYear(),now.getMonth(),now.getDate())}
function dateValue(offset:number){const value=startToday();value.setDate(value.getDate()+offset);return `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,"0")}-${String(value.getDate()).padStart(2,"0")}`}
function compactDate(value:string){return value.slice(2).replaceAll("-","")}
function downloadCsv(rows:Transaction[]){const columns=["occurred_at","order","type","product_name","lot","quantity","unit","reference","actor"] as const;const csv=[columns.join(","),...rows.map(row=>columns.map(column=>`"${String(row[column]??"").replaceAll('"','""')}"`).join(","))].join("\r\n");const url=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));const link=document.createElement("a");link.href=url;link.download=`commercial_ledger_${dateValue(0)}.csv`;link.click();URL.revokeObjectURL(url)}
