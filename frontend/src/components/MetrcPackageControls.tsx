import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "../lib/api";

type Link = {
  id:string;
  entity_type:string;
  entity_id:string;
  provider_resource:string;
  provider_id:string;
  provider_label:string;
  status:string;
  mismatch_reason:string;
};
type Status = {
  ready:boolean;
  provider:string;
  jurisdiction_code:string;
  environment:string;
  license_number:string;
  promoted_actions:string[];
  message:string;
  execution_boundary:string;
};
type Identities = { products:Link[]; packages:Link[] };
type ItemLookup = { items:{provider_id:string;name:string;last_modified:string}[]; truncated:boolean };
type PackageLookup = { items:{provider_id:string;label:string;name:string;quantity:number|null;unit_of_measure:string;last_modified:string}[]; truncated:boolean };
type ReasonLookup = { items:string[] };
type ProductWorkspace = { products:{product_id:string;name:string;sku:string}[] };
type Operation = "package_adjust"|"package_item"|"package_finish"|"package_unfinish";
type Preview = {
  ready:boolean;
  operation_type:Operation;
  summary:Record<string,unknown>;
  confirmation_id:string;
  confirmation_token:string;
  compliance_evidence:Record<string,unknown>;
  message:string;
};
type ExecuteResult = {
  ok:boolean;
  verified:boolean;
  status:string;
  transaction_id:string;
  external_reference:string;
  summary:Record<string,unknown>;
  message:string;
};

type Props = {
  lotId:string;
  productId:string;
  lotCode:string;
  productName:string;
  packageLabel:string;
  localStatus:string;
};

const today = () => new Date().toISOString().slice(0,10);
const title = (value:string) => value.replaceAll("_"," ").replace(/\b\w/g,letter=>letter.toUpperCase());
const valueText = (value:unknown) => {
  if(value===null||value===undefined||value==="") return "—";
  if(typeof value==="boolean") return value?"Yes":"No";
  if(typeof value==="number") return value.toLocaleString();
  return String(value);
};

export function MetrcPackageControls({lotId,productId,lotCode,productName,packageLabel,localStatus}:Props){
  const client=useQueryClient();
  const status=useQuery({queryKey:["metrc-package-status"],queryFn:({signal})=>apiGet<Status>("/api/v1/metrc-packages/status",signal),retry:false});
  const identities=useQuery({queryKey:["metrc-package-identities"],enabled:Boolean(status.data?.ready),queryFn:({signal})=>apiGet<Identities>("/api/v1/metrc-packages/identities",signal),retry:false});
  const productLink=identities.data?.products.find(row=>row.entity_id===productId);
  const packageLink=identities.data?.packages.find(row=>row.entity_id===lotId);
  const [linkMode,setLinkMode]=useState<""|"product"|"package">("");
  const [selectedItem,setSelectedItem]=useState("");
  const [selectedPackage,setSelectedPackage]=useState("");
  const [operation,setOperation]=useState<Operation>(localStatus.toLowerCase()==="finished"?"package_unfinish":"package_adjust");
  const [actualDate,setActualDate]=useState(today());
  const [quantityDelta,setQuantityDelta]=useState(0);
  const [adjustmentReason,setAdjustmentReason]=useState("");
  const [reasonNote,setReasonNote]=useState("");
  const [targetProductId,setTargetProductId]=useState("");
  const [preview,setPreview]=useState<Preview|null>(null);
  const [result,setResult]=useState<ExecuteResult|null>(null);

  const itemLookup=useQuery({
    queryKey:["metrc-package-items"],
    enabled:Boolean(status.data?.ready&&linkMode==="product"),
    queryFn:({signal})=>apiGet<ItemLookup>("/api/v1/metrc-packages/items",signal),
    retry:false,
  });
  const packageLookup=useQuery({
    queryKey:["metrc-package-list"],
    enabled:Boolean(status.data?.ready&&linkMode==="package"&&productLink?.status==="verified"),
    queryFn:({signal})=>apiGet<PackageLookup>("/api/v1/metrc-packages/packages",signal),
    retry:false,
  });
  const reasons=useQuery({
    queryKey:["metrc-package-adjustment-reasons"],
    enabled:Boolean(status.data?.ready&&packageLink?.status==="verified"&&operation==="package_adjust"),
    queryFn:({signal})=>apiGet<ReasonLookup>("/api/v1/metrc-packages/adjustment-reasons",signal),
    retry:false,
  });
  const workspace=useQuery({
    queryKey:["package-studio","metrc-products"],
    enabled:Boolean(status.data?.ready&&packageLink?.status==="verified"&&operation==="package_item"),
    queryFn:({signal})=>apiGet<ProductWorkspace>("/api/v1/package-studio/workspace",signal),
  });
  const linkedProductIds=useMemo(()=>new Set((identities.data?.products??[]).filter(row=>row.status==="verified").map(row=>row.entity_id)),[identities.data?.products]);
  const targetProducts=(workspace.data?.products??[]).filter(row=>row.product_id!==productId&&linkedProductIds.has(row.product_id));

  const refreshIdentities=()=>client.invalidateQueries({queryKey:["metrc-package-identities"]});
  const linkProduct=useMutation({
    mutationFn:()=>apiPost(`/api/v1/metrc-packages/products/${encodeURIComponent(productId)}/link`,{provider_item_id:selectedItem}),
    onSuccess:()=>{setLinkMode("");setSelectedItem("");refreshIdentities()},
  });
  const linkPackage=useMutation({
    mutationFn:()=>apiPost(`/api/v1/metrc-packages/lots/${encodeURIComponent(lotId)}/link`,{provider_package_id:selectedPackage}),
    onSuccess:()=>{setLinkMode("");setSelectedPackage("");refreshIdentities()},
  });

  const actionPayload={
    operation_type:operation,
    lot_id:lotId,
    actual_date:actualDate,
    quantity_delta:quantityDelta,
    adjustment_reason:adjustmentReason,
    reason_note:reasonNote,
    target_product_id:targetProductId,
    reason:"Package 360 controlled Metrc action",
  };
  const review=useMutation({
    mutationFn:()=>apiPost<Preview>("/api/v1/metrc-packages/actions/preview",actionPayload),
    onSuccess:data=>{setPreview(data);setResult(null)},
  });
  const execute=useMutation({
    mutationFn:()=>apiPost<ExecuteResult>("/api/v1/metrc-packages/actions/execute",{...actionPayload,confirmation_id:preview?.confirmation_id??"",confirmation_token:preview?.confirmation_token??""}),
    onSuccess:data=>{setResult(data);setPreview(null);refreshIdentities();client.invalidateQueries({queryKey:["package-360"]});client.invalidateQueries({queryKey:["package-studio"]})},
  });
  const resetReview=()=>{setPreview(null);setResult(null)};

  if(status.isLoading) return <section className="inventory-panel"><div className="state">Checking package traceability mode…</div></section>;
  if(status.isError) return <section className="inventory-panel"><div className="warning-banner">{status.error.message}</div></section>;
  if(!status.data?.ready) return <section className="inventory-panel"><div className="eyebrow">METRC PACKAGE ACTIONS</div><h2>DoobieLogic Sandbox</h2><div className="info-banner">{status.data?.message||"Metrc package actions are disabled for this facility mode."}</div><p className="section-note">Package workflows remain local. No state-system write is attempted.</p></section>;

  return <section className="inventory-panel">
    <div className="eyebrow">METRC PACKAGE ACTIONS · MA SANDBOX</div>
    <h2>{packageLink?.status==="verified"?"Package identity verified":"Link the exact package identity"}</h2>
    <p className="section-note">Operators work with package labels and business actions. DoobieLogic holds provider IDs, confirmation fingerprints, readback evidence, and reconciliation underneath.</p>
    <div className="two-column-grid">
      <div><Row label="DoobieLogic product" value={productName}/><Row label="Metrc item" value={productLink?.provider_label||"Not linked"}/></div>
      <div><Row label="DoobieLogic lot" value={lotCode}/><Row label="Metrc package" value={packageLink?.provider_label||packageLabel||"Not linked"}/></div>
    </div>

    {!productLink||productLink.status!=="verified"?<>
      <div className="warning-banner">Link this Product to one exact active Metrc Item before the package can be governed.</div>
      <button className="secondary" onClick={()=>setLinkMode(linkMode==="product"?"":"product")}>Choose Metrc Item</button>
      {linkMode==="product"?<div className="inventory-panel compact"><label>Exact Metrc Item<select value={selectedItem} onChange={event=>setSelectedItem(event.target.value)}><option value="">Select item…</option>{(itemLookup.data?.items??[]).map(item=><option key={item.provider_id} value={item.provider_id}>{item.name} · ID {item.provider_id}</option>)}</select></label>{itemLookup.data?.truncated?<div className="warning-banner">Item lookup reached the bounded paging limit. Refine facility master data before linking.</div>:null}<button className="primary" disabled={!selectedItem||linkProduct.isPending} onClick={()=>linkProduct.mutate()}>{linkProduct.isPending?"Verifying…":"Verify & link item"}</button>{linkProduct.isError?<div className="form-error">{linkProduct.error.message}</div>:null}</div>:null}
    </>:!packageLink||packageLink.status!=="verified"?<>
      <div className="warning-banner">The Product link is verified. Now select the exact Metrc Package whose item, quantity, and unit match this local lot.</div>
      <button className="secondary" onClick={()=>setLinkMode(linkMode==="package"?"":"package")}>Choose Metrc Package</button>
      {linkMode==="package"?<div className="inventory-panel compact"><label>Exact Metrc Package<select value={selectedPackage} onChange={event=>setSelectedPackage(event.target.value)}><option value="">Select package…</option>{(packageLookup.data?.items??[]).map(item=><option key={item.provider_id} value={item.provider_id}>{item.label||item.name} · {item.quantity??"—"} {item.unit_of_measure} · ID {item.provider_id}</option>)}</select></label>{packageLookup.data?.truncated?<div className="warning-banner">Package lookup reached the bounded paging limit. Use current facility package data before linking.</div>:null}<button className="primary" disabled={!selectedPackage||linkPackage.isPending} onClick={()=>linkPackage.mutate()}>{linkPackage.isPending?"Verifying…":"Verify & link package"}</button>{linkPackage.isError?<div className="form-error">{linkPackage.error.message}</div>:null}</div>:null}
    </>:<>
      {packageLink.mismatch_reason?<div className="warning-banner">{packageLink.mismatch_reason}</div>:null}
      <div className="view-tabs">
        {(["package_adjust","package_item","package_finish","package_unfinish"] as Operation[]).map(value=><button key={value} className={operation===value?"active":""} onClick={()=>{setOperation(value);resetReview()}}>{value==="package_item"?"Change item":value==="package_unfinish"?"Reopen":title(value.replace("package_",""))}</button>)}
      </div>
      <div className="two-column-grid">
        <label>Action date<input type="date" value={actualDate} onChange={event=>{setActualDate(event.target.value);resetReview()}}/></label>
        {operation==="package_adjust"?<label>Quantity change<input type="number" step="0.01" value={quantityDelta} onChange={event=>{setQuantityDelta(Number(event.target.value));resetReview()}}/></label>:null}
        {operation==="package_adjust"?<label>Metrc adjustment reason<select value={adjustmentReason} onChange={event=>{setAdjustmentReason(event.target.value);resetReview()}}><option value="">Select reason…</option>{(reasons.data?.items??[]).map(reason=><option key={reason}>{reason}</option>)}</select></label>:null}
        {operation==="package_adjust"?<label>Reason note<input value={reasonNote} onChange={event=>{setReasonNote(event.target.value);resetReview()}} placeholder="Optional provider note"/></label>:null}
        {operation==="package_item"?<label>New Product / Metrc Item<select value={targetProductId} onChange={event=>{setTargetProductId(event.target.value);resetReview()}}><option value="">Select linked product…</option>{targetProducts.map(product=><option key={product.product_id} value={product.product_id}>{product.name} · {product.sku}</option>)}</select></label>:null}
      </div>
      {operation==="package_item"&&!targetProducts.length?<div className="info-banner">No other active Product currently has a verified Metrc Item identity. Link the Product first, then return here.</div>:null}
      <button className="primary" disabled={review.isPending||(operation==="package_adjust"&&(!quantityDelta||!adjustmentReason))||(operation==="package_item"&&!targetProductId)} onClick={()=>review.mutate()}>{review.isPending?"Checking fresh Metrc state…":"Review Metrc change"}</button>
      {review.isError?<div className="form-error">{review.error.message}</div>:null}

      {preview?<div className="inventory-panel compact"><div className="eyebrow">CONFIRM PACKAGE CHANGE</div><h3>{valueText(preview.summary.title)}</h3><div className="detail-facts">{Object.entries(preview.summary).filter(([key])=>key!=="title").map(([key,value])=><Row key={key} label={title(key)} value={valueText(value)}/>)}</div><div className="warning-banner">Metrc has not been changed yet. Confirming submits exactly these reviewed values. HTTP 200 will still require fresh semantic readback before this becomes Verified.</div><details><summary>Compliance evidence details</summary><pre>{JSON.stringify(preview.compliance_evidence,null,2)}</pre></details><div className="heading-actions"><button className="secondary" onClick={()=>setPreview(null)}>Cancel</button><button className="primary" disabled={execute.isPending} onClick={()=>execute.mutate()}>{execute.isPending?"Submitting & verifying…":"Confirm Metrc change"}</button></div>{execute.isError?<div className="form-error">{execute.error.message}</div>:null}</div>:null}
      {result?<div className={result.verified?"success-banner":"warning-banner"}><strong>{result.verified?"Verified":"Reconciliation required"}</strong><br/>{result.message}<br/><small>Transaction {result.transaction_id}{result.external_reference?` · Provider ${result.external_reference}`:""}</small></div>:null}
    </>}
  </section>;
}

function Row({label,value}:{label:string;value:string}){return <div className="catalog-row"><strong>{label}</strong><span>{value||"—"}</span></div>}
