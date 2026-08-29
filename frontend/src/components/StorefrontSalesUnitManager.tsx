import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../lib/api";

type SalesUnitProduct = {
  product_id:string;
  sku:string;
  name:string;
  base_unit:string;
  sales_unit:string;
  compatible_sales_units:string[];
  price_usd:number;
  minimum_quantity:number;
  case_quantity:number;
  active:boolean;
};

type SalesUnitSnapshot = {
  storefront:{id:string;display_name:string}|null;
  products:SalesUnitProduct[];
};

const UNIT_LABELS:Record<string,string>={g:"Grams (g)",oz:"Ounces (oz)",lb:"Pounds (lb)",kg:"Kilograms (kg)",unit:"Units"};

export function StorefrontSalesUnitManager(){
  const client=useQueryClient();
  const query=useQuery({
    queryKey:["storefront-sales-units"],
    queryFn:({signal})=>apiGet<SalesUnitSnapshot>("/api/v1/storefronts/sales-units",signal),
  });
  const [drafts,setDrafts]=useState<Record<string,string>>({});
  useEffect(()=>{
    if(!query.data)return;
    setDrafts(Object.fromEntries(query.data.products.map(row=>[row.product_id,row.sales_unit])));
  },[query.data]);
  const mutation=useMutation({
    mutationFn:({productId,salesUnit}:{productId:string;salesUnit:string})=>apiPost<SalesUnitProduct>(`/api/v1/storefronts/sales-units/${encodeURIComponent(productId)}`,{sales_unit:salesUnit}),
    onSuccess:async()=>{
      await Promise.all([
        client.invalidateQueries({queryKey:["storefront-sales-units"]}),
        client.invalidateQueries({queryKey:["commerce-storefront"]}),
        client.invalidateQueries({queryKey:["commerce-storefront-options"]}),
      ]);
    },
  });
  const rows=useMemo(()=>query.data?.products.filter(row=>row.active&&row.compatible_sales_units.length>0)??[],[query.data]);
  if(query.isLoading)return <div className="state">Loading storefront sales units…</div>;
  if(query.isError)return <div className="warning-banner">Sales-unit controls are unavailable: {query.error.message}</div>;
  if(!query.data?.storefront)return null;
  return <section className="inventory-panel storefront-sales-unit-manager">
    <div className="eyebrow">STOREFRONT SALES UNITS</div>
    <h2>Sell bulk inventory in the unit customers actually buy.</h2>
    <p className="section-note">Inventory stays in its operational base unit. The storefront can sell compatible weight-based products in grams, ounces, pounds, or kilograms. When you switch units, DoobieLogic preserves the same physical minimums, case increments, volume thresholds, and equivalent pricing automatically.</p>
    {!rows.length?<div className="info-banner">Add products to the storefront catalog before choosing customer-facing sales units.</div>:<div className="table-wrap"><table>
      <thead><tr><th>Product</th><th>Inventory unit</th><th>Storefront sales unit</th><th>Current minimum</th><th>Order increment</th><th></th></tr></thead>
      <tbody>{rows.map(row=>{
        const draft=drafts[row.product_id]??row.sales_unit;
        const changed=draft!==row.sales_unit;
        return <tr key={row.product_id}>
          <td><strong>{row.name}</strong><br/><small>{row.sku}</small></td>
          <td>{UNIT_LABELS[row.base_unit]??row.base_unit}</td>
          <td><select aria-label={`Sales unit for ${row.name}`} value={draft} onChange={event=>setDrafts(current=>({...current,[row.product_id]:event.target.value}))}>{row.compatible_sales_units.map(unit=><option key={unit} value={unit}>{UNIT_LABELS[unit]??unit}</option>)}</select></td>
          <td>{number(row.minimum_quantity)} {row.sales_unit}</td>
          <td>{number(row.case_quantity)} {row.sales_unit}</td>
          <td><button className="secondary" type="button" disabled={!changed||mutation.isPending} onClick={()=>mutation.mutate({productId:row.product_id,salesUnit:draft})}>{mutation.isPending?"Saving…":"Apply unit"}</button></td>
        </tr>;
      })}</tbody>
    </table></div>}
    {mutation.isSuccess?<div className="success-banner">Storefront sales unit updated. Availability and order rules were converted without changing base inventory.</div>:null}
    {mutation.isError?<div className="form-error">Unable to change the storefront sales unit: {mutation.error.message}</div>:null}
  </section>;
}

function number(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:4})}
