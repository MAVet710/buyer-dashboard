import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type InvoiceRow = {
  id:string;invoice_number:string;customer:string;order_number:string;status:string;issue_date:string;due_date:string;
  total_usd:number;balance_usd:number;qbo_link_status:string;qbo_id:string;last_synced_at:string|null;
};
type PaymentRow = {id:string;invoice_number:string;customer:string;amount_usd:number;payment_date:string;method:string;reference:string;recorded_by:string};
type SalesOrderRow = {id:string;order_number:string;customer:string;status:string;payment_status:string;order_total:number;due_at:string|null};
type QboVendorRow = {partner_id:string;name:string;status:string;qbo_id:string;last_synced_at:string|null};
type QboPoRow = {order_id:string;order_number:string;order_status:string;sync_status:string;qbo_id:string;missing_item_mappings:number;last_synced_at:string|null};
type AccountingSnapshot = {
  read_only:boolean;
  summary:{total_ar:number;current_ar:number;overdue_ar:number;open_invoice_count:number;payments_30d:number;open_sales_order_value:number;qbo_connected:boolean;qbo_attention_count:number};
  ar:{total_ar:number;buckets:Record<string,number>;invoices:Array<Record<string,unknown>>};
  invoices:InvoiceRow[];
  recent_payments:PaymentRow[];
  sales_orders:SalesOrderRow[];
  sales_payment_status_counts:Record<string,number>;
  quickbooks:{
    connected:boolean;
    linked_entities:Record<string,number>;
    message:string;
    purchasing_reconciliation:{summary:{vendor_count:number;purchase_order_count:number;synced_vendor_count:number;synced_purchase_order_count:number;attention_count:number};vendors:QboVendorRow[];purchase_orders:QboPoRow[];message:string};
  };
};

export function WholesaleAccountingPanel({onNavigate}:{onNavigate:(page:string)=>void}) {
  const query=useQuery({queryKey:["wholesale-accounting"],queryFn:({signal})=>apiGet<AccountingSnapshot>("/api/v1/commercial/accounting",signal),staleTime:20_000});
  if(query.isLoading)return <div className="state">Building wholesale accounting…</div>;
  if(query.isError)return <div className="warning-banner">Wholesale accounting could not be loaded: {query.error.message}</div>;
  const data=query.data!;
  const aging=data.ar.buckets;
  return <div className="wholesale-accounting">
    <section className="inventory-panel">
      <div className="page-heading">
        <div><div className="eyebrow">WHOLESALE · ACCOUNTING</div><h2>Money tied to the wholesale operation.</h2><p className="section-note">A/R, invoice balances, payments, order payment state, and QuickBooks synchronization are pooled here from the same commercial records. This view never creates a second accounting ledger.</p></div>
        <div className="heading-actions"><button className="secondary" type="button" onClick={()=>query.refetch()}>Refresh</button><button className="secondary" type="button" onClick={()=>onNavigate("Integrations")}>QuickBooks settings</button></div>
      </div>
      <section className="metrics wholesale-metrics">
        <Metric label="Accounts receivable" value={money(data.summary.total_ar)} meta={`${data.summary.open_invoice_count} open invoice${data.summary.open_invoice_count===1?"":"s"}`}/>
        <Metric label="Overdue A/R" value={money(data.summary.overdue_ar)} meta="Past-due customer balances"/>
        <Metric label="Current A/R" value={money(data.summary.current_ar)} meta="Not yet past due"/>
        <Metric label="Payments · 30d" value={money(data.summary.payments_30d)} meta="Recorded against wholesale invoices"/>
        <Metric label="Open sales value" value={money(data.summary.open_sales_order_value)} meta="Unfulfilled wholesale sales orders"/>
        <Metric label="QuickBooks" value={data.summary.qbo_connected?"Connected":"Not connected"} meta={`${data.summary.qbo_attention_count} purchasing sync item${data.summary.qbo_attention_count===1?"":"s"} need attention`}/>
      </section>
    </section>

    <section className="inventory-panel">
      <div className="eyebrow">A/R AGING</div><h3>Outstanding customer balances</h3>
      <section className="metrics wholesale-metrics">
        <Metric label="Current" value={money(aging.current??0)} meta="Due now / not past due"/>
        <Metric label="1–30" value={money(aging["1_30"]??0)} meta="Days past due"/>
        <Metric label="31–60" value={money(aging["31_60"]??0)} meta="Days past due"/>
        <Metric label="61–90" value={money(aging["61_90"]??0)} meta="Days past due"/>
        <Metric label="90+" value={money(aging["90_plus"]??0)} meta="Days past due"/>
      </section>
    </section>

    <section className="inventory-panel">
      <div className="page-heading"><div><div className="eyebrow">INVOICES</div><h3>Wholesale invoices</h3><p className="section-note">Balances come from DoobieLogic Commercial Finance. QuickBooks columns show durable sync/link metadata, not a fresh provider readback.</p></div></div>
      {!data.invoices.length?<div className="info-banner">No wholesale invoices have been created yet.</div>:<div className="table-wrap"><table><thead><tr><th>Invoice</th><th>Customer</th><th>Order</th><th>Status</th><th>Due</th><th>Total</th><th>Balance</th><th>QuickBooks</th></tr></thead><tbody>{data.invoices.slice(0,75).map(row=><tr key={row.id}><td><strong>{row.invoice_number}</strong><br/><small>{date(row.issue_date)}</small></td><td>{row.customer}</td><td>{row.order_number||"—"}</td><td><span className="status-pill">{title(row.status)}</span></td><td>{date(row.due_date)}</td><td>{money(row.total_usd)}</td><td><strong>{money(row.balance_usd)}</strong></td><td>{row.qbo_id?<><span className="success-text">Linked</span><br/><small>{row.qbo_id}</small></>:<span className="source-caption">Not linked</span>}</td></tr>)}</tbody></table></div>}
    </section>

    <section className="inventory-panel">
      <div className="eyebrow">ORDER PAYMENT STATE</div><h3>Wholesale sales orders</h3><p className="section-note">This is the operational payment state attached to the sales order, alongside its commercial value and fulfillment status.</p>
      {!data.sales_orders.length?<div className="info-banner">No wholesale sales orders are available.</div>:<div className="table-wrap"><table><thead><tr><th>Order</th><th>Customer</th><th>Order status</th><th>Payment status</th><th>Value</th><th>Due</th></tr></thead><tbody>{data.sales_orders.slice(0,75).map(row=><tr key={row.id}><td><strong>{row.order_number}</strong></td><td>{row.customer}</td><td>{title(row.status)}</td><td><span className="status-pill">{title(row.payment_status)}</span></td><td>{money(row.order_total)}</td><td>{dateTime(row.due_at)}</td></tr>)}</tbody></table></div>}
    </section>

    <section className="inventory-panel">
      <div className="eyebrow">RECENT CASH</div><h3>Recorded payments</h3>
      {!data.recent_payments.length?<div className="info-banner">No invoice payments have been recorded yet.</div>:<div className="table-wrap"><table><thead><tr><th>Date</th><th>Customer</th><th>Invoice</th><th>Amount</th><th>Method</th><th>Reference</th></tr></thead><tbody>{data.recent_payments.slice(0,50).map(row=><tr key={row.id}><td>{date(row.payment_date)}</td><td>{row.customer}</td><td>{row.invoice_number}</td><td><strong>{money(row.amount_usd)}</strong></td><td>{title(row.method)}</td><td>{row.reference||"—"}</td></tr>)}</tbody></table></div>}
    </section>

    <section className="inventory-panel">
      <div className="page-heading"><div><div className="eyebrow">QUICKBOOKS ONLINE</div><h3>Accounting synchronization health</h3><p className="section-note">Customer/invoice/item links and purchasing reconciliation use the existing facility-scoped accounting-link ledger. Provider writes still require the governed admin sync routes.</p></div><span className="status-pill">{data.quickbooks.connected?"CONNECTED":"NOT CONNECTED"}</span></div>
      <div className="info-banner">{data.quickbooks.message}</div>
      <section className="metrics wholesale-metrics">
        <Metric label="Customers linked" value={data.quickbooks.linked_entities.customer??0} meta="QuickBooks Customer IDs"/>
        <Metric label="Invoices linked" value={data.quickbooks.linked_entities.invoice??0} meta="QuickBooks Invoice IDs"/>
        <Metric label="Items mapped" value={data.quickbooks.linked_entities.item??0} meta="Required for invoice and PO lines"/>
        <Metric label="Vendors linked" value={data.quickbooks.linked_entities.vendor??0} meta="QuickBooks Vendor IDs"/>
        <Metric label="POs linked" value={data.quickbooks.linked_entities.purchase_order??0} meta="QuickBooks Purchase Orders"/>
      </section>
      <details className="streamlit-expander" open={data.summary.qbo_attention_count>0}><summary>Purchasing reconciliation · {data.summary.qbo_attention_count} need attention</summary><div className="streamlit-expander-body">
        <p className="section-note">{data.quickbooks.purchasing_reconciliation.message}</p>
        <h4>Vendors</h4>{!data.quickbooks.purchasing_reconciliation.vendors.length?<div className="info-banner">No purchasing vendors are configured.</div>:<div className="table-wrap"><table><thead><tr><th>Vendor</th><th>Sync state</th><th>QuickBooks ID</th><th>Last sync</th></tr></thead><tbody>{data.quickbooks.purchasing_reconciliation.vendors.map(row=><tr key={row.partner_id}><td>{row.name}</td><td><span className="status-pill">{title(row.status)}</span></td><td>{row.qbo_id||"—"}</td><td>{dateTime(row.last_synced_at)}</td></tr>)}</tbody></table></div>}
        <h4>Purchase orders</h4>{!data.quickbooks.purchasing_reconciliation.purchase_orders.length?<div className="info-banner">No purchase orders are available for reconciliation.</div>:<div className="table-wrap"><table><thead><tr><th>PO</th><th>Doobie status</th><th>Sync state</th><th>Missing item maps</th><th>QuickBooks ID</th></tr></thead><tbody>{data.quickbooks.purchasing_reconciliation.purchase_orders.map(row=><tr key={row.order_id}><td><strong>{row.order_number}</strong></td><td>{title(row.order_status)}</td><td><span className="status-pill">{title(row.sync_status)}</span></td><td>{row.missing_item_mappings}</td><td>{row.qbo_id||"—"}</td></tr>)}</tbody></table></div>}
      </div></details>
    </section>
  </div>;
}

function Metric({label,value,meta}:{label:string;value:string|number;meta:string}){return <article className="metric"><span>{label}</span><strong>{value}</strong><small>{meta}</small></article>}
function money(value:number){return Number(value||0).toLocaleString(undefined,{style:"currency",currency:"USD",maximumFractionDigits:0})}
function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function date(value:string|null|undefined){if(!value)return"—";const parsed=new Date(`${value}T00:00:00`);return Number.isNaN(parsed.getTime())?String(value):parsed.toLocaleDateString()}
function dateTime(value:string|null|undefined){if(!value)return"—";const parsed=new Date(value);return Number.isNaN(parsed.getTime())?String(value):parsed.toLocaleString()}
