import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type Lot = {
  lot_id:string;
  lot_code:string;
  compliance_package_id:string;
  product_id:string;
  product_name:string;
  sku:string;
  balance:number;
  unit:string;
  location_code:string;
};
type Product = { product_id:string; name:string; sku:string; item_type:string; base_unit:string };
type Run = { id:string; run_number:string; action_type:string; status:string; source_quantity:number; source_unit:string; loss_quantity:number; external_sync_status:string; created_by:string; committed_at:string };
type Workspace = {
  lots:Lot[];
  products:Product[];
  runs:Run[];
  can_commit:boolean;
  operating_mode:string;
  metrc_enabled:boolean;
  tracked_metrc_lot_ids:string[];
};
type Preview = { action_type:string; total_input:number; total_output_source_equivalent:number; loss_quantity:number; source_unit:string; balanced:boolean; difference:number; output_count:number };
type CommitResult = { run_id:string; run_number:string; output_lot_ids:string[]; input_transactions:number; output_transactions:number };
type Output = { product_id:string; lot_code:string; compliance_package_id:string; inventory_quantity:number; inventory_unit:string; source_equivalent_quantity:number; purpose:string };
type Trail = { lot:{lot_id:string;lot_code:string;compliance_package_id:string;product_name:string;balance:number;unit:string}; created_by:null|{run_number:string;action_type:string;parents:{lot_id:string;lot_code:string;product_name:string;quantity:number;unit:string}[]}; used_by:{run_number:string;action_type:string;quantity_consumed:number;unit:string;outputs:{lot_id:string;lot_code:string;product_id:string;inventory_quantity:number;inventory_unit:string;purpose:string}[]}[] };
type MetrcStatus = { ready:boolean; message:string; environment:string; license_number:string; promoted_actions:string[] };
type MetrcLink = { entity_type:string; entity_id:string; provider_resource:string; provider_id:string; provider_label:string; status:string; mismatch_reason:string };
type MetrcIdentities = { products:MetrcLink[]; packages:MetrcLink[] };
type TagLookup = { items:string[]; truncated:boolean };
type TransformationSummary = {
  title:string;
  action:string;
  source_package:string;
  source_quantity:number;
  source_unit:string;
  source_remaining:number;
  output_count:number;
  outputs:{lot_code:string;metrc_tag:string;metrc_item:string;quantity:number;unit:string}[];
};
type TransformationPreview = {
  ready:boolean;
  operation_type:string;
  summary:TransformationSummary;
  confirmation_id:string;
  confirmation_token:string;
  compliance_evidence:Record<string,unknown>;
  message:string;
};
type TransformationResult = {
  ok:boolean;
  verified:boolean;
  status:string;
  transaction_id:string;
  external_reference:string;
  summary:TransformationSummary;
  verified_outputs:{position:number;provider_id:string;tag:string;item:string;quantity:number;unit:string}[];
  message:string;
  local_result?:{run_id:string;run_number:string;output_lot_ids:string[]};
};

const ACTIONS = [
  ["Breakdown","breakdown"], ["Pack Down","pack_down"], ["Build Run","build_run"],
  ["Multi-Build","multi_build"], ["Sample Pull","sample_pull"], ["Rework","rework"],
  ["Source Correction","correction"],
] as const;
const PURPOSES:Record<string,string> = {
  "Standard output":"standard",
  "Lab sample":"lab_sample",
  "Trade sample":"trade_sample",
  "Retail sample":"retail_sample",
  "Rework output":"rework",
  "Corrected output":"corrected",
};
const EMPTY_LOTS:Lot[]=[];
const EMPTY_PRODUCTS:Product[]=[];
const blankOutput = ():Output => ({product_id:"",lot_code:"",compliance_package_id:"",inventory_quantity:0,inventory_unit:"unit",source_equivalent_quantity:0,purpose:"standard"});
const title = (value:string) => value.replaceAll("_"," ").replace(/\b\w/g,letter=>letter.toUpperCase());
const fixed = (value:number) => value.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const today = () => new Date().toISOString().slice(0,10);

export function PackageStudioPage({initialLotId=""}:{initialLotId?:string}={}) {
  const client=useQueryClient();
  const workspace=useQuery({queryKey:["package-studio"],queryFn:({signal})=>apiGet<Workspace>("/api/v1/package-studio/workspace",signal)});
  const [tab,setTab]=useState<"New Run"|"Source Trail"|"Recent Runs">("New Run");
  const [actionLabel,setActionLabel]=useState<(typeof ACTIONS)[number][0]>("Breakdown");
  const [lotId,setLotId]=useState(initialLotId);
  const [outputCount,setOutputCount]=useState(2);
  const [loss,setLoss]=useState(0);
  const [reason,setReason]=useState("");
  const [outputs,setOutputs]=useState<Output[]>([blankOutput(),blankOutput()]);
  const [confirm,setConfirm]=useState(false);
  const [commitMessage,setCommitMessage]=useState("");
  const [actualDate,setActualDate]=useState(today());
  const [transformationPreview,setTransformationPreview]=useState<TransformationPreview|null>(null);
  const [transformationResult,setTransformationResult]=useState<TransformationResult|null>(null);

  const lots=workspace.data?.lots??EMPTY_LOTS;
  const products=workspace.data?.products??EMPTY_PRODUCTS;
  const effectiveLotId=lots.some(row=>row.lot_id===lotId)?lotId:lots.some(row=>row.lot_id===initialLotId)?initialLotId:(lots[0]?.lot_id??"");
  const source=lots.find(row=>row.lot_id===effectiveLotId);
  const actionType=ACTIONS.find(([label])=>label===actionLabel)?.[1]??"breakdown";
  const sourceTracked=Boolean(workspace.data?.metrc_enabled&&source&&workspace.data.tracked_metrc_lot_ids.includes(source.lot_id));

  const metrcStatus=useQuery({
    queryKey:["metrc-package-status"],
    enabled:Boolean(workspace.data?.metrc_enabled),
    queryFn:({signal})=>apiGet<MetrcStatus>("/api/v1/metrc-packages/status",signal),
    retry:false,
  });
  const identities=useQuery({
    queryKey:["metrc-package-identities"],
    enabled:Boolean(sourceTracked&&metrcStatus.data?.ready),
    queryFn:({signal})=>apiGet<MetrcIdentities>("/api/v1/metrc-packages/identities",signal),
    retry:false,
  });
  const availableTags=useQuery({
    queryKey:["metrc-package-available-tags"],
    enabled:Boolean(sourceTracked&&metrcStatus.data?.ready),
    queryFn:({signal})=>apiGet<TagLookup>("/api/v1/metrc-packages/available-tags",signal),
    retry:false,
  });

  useEffect(()=>{
    if(effectiveLotId&&lotId!==effectiveLotId)setLotId(effectiveLotId);
  },[effectiveLotId,lotId]);
  useEffect(()=>{
    setOutputs(current=>Array.from({length:outputCount},(_,index)=>current[index]??blankOutput()));
    setConfirm(false);
    setTransformationPreview(null);
    setTransformationResult(null);
  },[outputCount]);
  useEffect(()=>{
    setTransformationPreview(null);
    setTransformationResult(null);
    setConfirm(false);
  },[effectiveLotId]);

  const configuredOutputs=useMemo(()=>outputs.slice(0,outputCount).map(row=>{
    const locked=actionType==="breakdown"||actionType==="sample_pull";
    const productId=locked?(source?.product_id??""):(row.product_id||products[0]?.product_id||"");
    const product=products.find(item=>item.product_id===productId);
    const purpose=actionType==="sample_pull"
      ?(row.purpose==="lab_sample"||row.purpose==="trade_sample"||row.purpose==="retail_sample"?row.purpose:"lab_sample")
      :actionType==="rework"?"rework":actionType==="correction"?"corrected":row.purpose;
    return {...row,product_id:productId,inventory_unit:row.inventory_unit==="unit"&&product?.base_unit?product.base_unit:row.inventory_unit,purpose};
  }),[actionType,outputCount,outputs,products,source]);
  const sourceTotal=configuredOutputs.reduce((sum,row)=>sum+row.source_equivalent_quantity,0);
  const sourceToUse=sourceTotal+loss;
  const remaining=(source?.balance??0)-sourceToUse;
  const plan=useMemo(()=>({
    action_type:actionType,
    inputs:[{lot_id:source?.lot_id??"",quantity:sourceToUse,unit:source?.unit??"unit",purpose:"source"}],
    outputs:configuredOutputs.map(row=>({...row,source_equivalent_unit:source?.unit??"unit",location_code:"FINISHED-GOODS",notes:""})),
    loss_quantity:loss,
    source_unit:source?.unit??"unit",
    reason,
  }),[actionType,configuredOutputs,loss,reason,source,sourceToUse]);
  const transformationPayload=useMemo(()=>({
    ...plan,
    reason:reason.trim()||"Tracked Package Studio transformation",
    actual_date:actualDate,
  }),[actualDate,plan,reason]);
  const canPreview=Boolean(source&&sourceToUse>0&&sourceToUse<=source.balance+1e-9);
  const preview=useQuery({queryKey:["package-studio-preview",plan],enabled:canPreview,queryFn:()=>apiPost<Preview>("/api/v1/package-studio/preview",plan),retry:false});
  const localCommit=useMutation({
    mutationFn:()=>apiPost<CommitResult>("/api/v1/package-studio/commit",plan),
    onSuccess:result=>{
      setCommitMessage(`${result.run_number} committed with ${result.output_lot_ids.length} output package(s).`);
      setConfirm(false);
      client.invalidateQueries({queryKey:["package-studio"]});
    },
  });
  const reviewTransformation=useMutation({
    mutationFn:()=>apiPost<TransformationPreview>("/api/v1/metrc-packages/transformations/preview",transformationPayload),
    onSuccess:data=>{setTransformationPreview(data);setTransformationResult(null)},
  });
  const executeTransformation=useMutation({
    mutationFn:()=>apiPost<TransformationResult>("/api/v1/metrc-packages/transformations/execute",{
      ...transformationPayload,
      confirmation_id:transformationPreview?.confirmation_id??"",
      confirmation_token:transformationPreview?.confirmation_token??"",
    }),
    onSuccess:data=>{
      setTransformationResult(data);
      setTransformationPreview(null);
      setConfirm(false);
      if(data.local_result?.run_number)setCommitMessage(`${data.local_result.run_number} verified with ${data.local_result.output_lot_ids.length} Metrc-linked output package(s).`);
      client.invalidateQueries({queryKey:["package-studio"]});
      client.invalidateQueries({queryKey:["metrc-package-identities"]});
      client.invalidateQueries({queryKey:["metrc-package-available-tags"]});
      client.invalidateQueries({queryKey:["package-360"]});
    },
  });

  const changeAction=(label:(typeof ACTIONS)[number][0])=>{
    const type=ACTIONS.find(row=>row[0]===label)?.[1];
    const count=type==="breakdown"||type==="multi_build"?2:1;
    setActionLabel(label);
    setOutputCount(count);
    setOutputs(Array.from({length:count},blankOutput));
    setConfirm(false);
    setCommitMessage("");
    setTransformationPreview(null);
    setTransformationResult(null);
  };
  const updateOutput=(index:number,patch:Partial<Output>)=>{
    setOutputs(current=>current.map((row,rowIndex)=>rowIndex===index?{...row,...patch}:row));
    setConfirm(false);
    setTransformationPreview(null);
    setTransformationResult(null);
  };

  const linkedProductIds=useMemo(()=>new Set((identities.data?.products??[]).filter(row=>row.status==="verified").map(row=>row.entity_id)),[identities.data?.products]);
  const sourceLink=identities.data?.packages.find(row=>row.entity_id===source?.lot_id);
  const allOutputProductsLinked=configuredOutputs.every(row=>linkedProductIds.has(row.product_id));
  const selectedTags=configuredOutputs.map(row=>row.compliance_package_id.trim()).filter(Boolean);
  const availableTagSet=useMemo(()=>new Set(availableTags.data?.items??[]),[availableTags.data?.items]);
  const allTagsReady=configuredOutputs.length>0&&selectedTags.length===configuredOutputs.length&&new Set(selectedTags).size===selectedTags.length&&selectedTags.every(tag=>availableTagSet.has(tag));
  const hasLabSample=configuredOutputs.some(row=>row.purpose==="lab_sample");
  const metrcReady=Boolean(metrcStatus.data?.ready&&sourceLink?.status==="verified"&&allOutputProductsLinked&&allTagsReady&&loss===0&&!hasLabSample);

  return <div className="package-studio-workspace">
    <div className="ps-kicker">PACKAGE STUDIO</div>
    <h2>Package transformation</h2>
    <p className="ps-subtitle">Break down, pack down, build, sample, correct, and trace packages from one auditable work window.</p>
    <div className="view-tabs package-studio-tabs">{(["New Run","Source Trail","Recent Runs"] as const).map(value=><button className={tab===value?"active":""} key={value} onClick={()=>setTab(value)}>{value}</button>)}</div>
    {workspace.isLoading?<div className="state">Loading Package Studio…</div>:null}
    {workspace.isError?<div className="form-error">{workspace.error.message}</div>:null}
    {workspace.data&&tab==="New Run"?<NewRun
      lots={lots}
      products={products}
      source={source}
      lotId={effectiveLotId}
      setLotId={value=>{setLotId(value);setConfirm(false);setCommitMessage("")}}
      actionLabel={actionLabel}
      changeAction={changeAction}
      actionType={actionType}
      outputCount={outputCount}
      setOutputCount={setOutputCount}
      loss={loss}
      setLoss={value=>{setLoss(value);setConfirm(false);setTransformationPreview(null);setTransformationResult(null)}}
      reason={reason}
      setReason={value=>{setReason(value);setTransformationPreview(null);setTransformationResult(null)}}
      outputs={configuredOutputs}
      updateOutput={updateOutput}
      sourceTotal={sourceTotal}
      sourceToUse={sourceToUse}
      remaining={remaining}
      preview={preview}
      canCommit={workspace.data.can_commit}
      confirm={confirm}
      setConfirm={setConfirm}
      localCommit={()=>localCommit.mutate()}
      localCommitPending={localCommit.isPending}
      localCommitError={localCommit.isError?localCommit.error.message:""}
      commitMessage={commitMessage}
      operatingMode={workspace.data.operating_mode}
      sourceTracked={sourceTracked}
      metrcStatus={metrcStatus.data}
      metrcStatusError={metrcStatus.isError?metrcStatus.error.message:""}
      sourceLink={sourceLink}
      availableTags={availableTags.data?.items??[]}
      tagsLoading={availableTags.isLoading}
      tagsError={availableTags.isError?availableTags.error.message:""}
      tagsTruncated={Boolean(availableTags.data?.truncated)}
      linkedProductIds={linkedProductIds}
      allOutputProductsLinked={allOutputProductsLinked}
      allTagsReady={allTagsReady}
      hasLabSample={hasLabSample}
      metrcReady={metrcReady}
      actualDate={actualDate}
      setActualDate={value=>{setActualDate(value);setTransformationPreview(null);setTransformationResult(null)}}
      reviewTransformation={()=>reviewTransformation.mutate()}
      reviewPending={reviewTransformation.isPending}
      reviewError={reviewTransformation.isError?reviewTransformation.error.message:""}
      transformationPreview={transformationPreview}
      cancelTransformation={()=>setTransformationPreview(null)}
      executeTransformation={()=>executeTransformation.mutate()}
      executePending={executeTransformation.isPending}
      executeError={executeTransformation.isError?executeTransformation.error.message:""}
      transformationResult={transformationResult}
    />:null}
    {workspace.data&&tab==="Source Trail"?<SourceTrail lots={lots} initialLotId={effectiveLotId}/>:null}
    {workspace.data&&tab==="Recent Runs"?<RecentRuns runs={workspace.data.runs}/>:null}
  </div>;
}

type NewRunProps={
  lots:Lot[];
  products:Product[];
  source?:Lot;
  lotId:string;
  setLotId:(value:string)=>void;
  actionLabel:(typeof ACTIONS)[number][0];
  changeAction:(value:(typeof ACTIONS)[number][0])=>void;
  actionType:string;
  outputCount:number;
  setOutputCount:(value:number)=>void;
  loss:number;
  setLoss:(value:number)=>void;
  reason:string;
  setReason:(value:string)=>void;
  outputs:Output[];
  updateOutput:(index:number,patch:Partial<Output>)=>void;
  sourceTotal:number;
  sourceToUse:number;
  remaining:number;
  preview:ReturnType<typeof useQuery<Preview>>;
  canCommit:boolean;
  confirm:boolean;
  setConfirm:(value:boolean)=>void;
  localCommit:()=>void;
  localCommitPending:boolean;
  localCommitError:string;
  commitMessage:string;
  operatingMode:string;
  sourceTracked:boolean;
  metrcStatus?:MetrcStatus;
  metrcStatusError:string;
  sourceLink?:MetrcLink;
  availableTags:string[];
  tagsLoading:boolean;
  tagsError:string;
  tagsTruncated:boolean;
  linkedProductIds:Set<string>;
  allOutputProductsLinked:boolean;
  allTagsReady:boolean;
  hasLabSample:boolean;
  metrcReady:boolean;
  actualDate:string;
  setActualDate:(value:string)=>void;
  reviewTransformation:()=>void;
  reviewPending:boolean;
  reviewError:string;
  transformationPreview:TransformationPreview|null;
  cancelTransformation:()=>void;
  executeTransformation:()=>void;
  executePending:boolean;
  executeError:string;
  transformationResult:TransformationResult|null;
};

function NewRun(props:NewRunProps){
  const {
    lots,products,source,lotId,setLotId,actionLabel,changeAction,actionType,outputCount,setOutputCount,
    loss,setLoss,reason,setReason,outputs,updateOutput,sourceTotal,sourceToUse,remaining,preview,canCommit,
    confirm,setConfirm,localCommit,localCommitPending,localCommitError,commitMessage,operatingMode,sourceTracked,
    metrcStatus,metrcStatusError,sourceLink,availableTags,tagsLoading,tagsError,tagsTruncated,linkedProductIds,
    allOutputProductsLinked,allTagsReady,hasLabSample,metrcReady,actualDate,setActualDate,reviewTransformation,
    reviewPending,reviewError,transformationPreview,cancelTransformation,executeTransformation,executePending,
    executeError,transformationResult,
  }=props;
  if(!lots.length)return <><div className="info-banner">No durable available packages were found for this facility.</div><p className="ps-subtitle">Package Studio works from Supabase-backed inventory lots so Source Trail remains auditable.</p></>;
  if(!products.length)return <div className="info-banner">No active products are available for Package Studio outputs.</div>;
  return <section className="package-studio-new-run">
    <div className={sourceTracked?"warning-banner":"info-banner"}>{sourceTracked?"Metrc Sandbox · this source has a governed Metrc Package identity. Provider outputs must verify before the local ledger commits.":operatingMode==="doobielogic_sandbox"?"DoobieLogic Sandbox · this Package Studio run is local-only and does not call Metrc.":"Metrc Sandbox · this source is not currently a governed Metrc Package, so the run remains local-only."}</div>
    <label>Package action<select value={actionLabel} onChange={event=>changeAction(event.target.value as (typeof ACTIONS)[number][0])}>{ACTIONS.map(([label])=><option key={label}>{label}</option>)}</select></label>
    <label>Source package<select value={lotId} onChange={event=>setLotId(event.target.value)}>{lots.map(row=><option value={row.lot_id} key={row.lot_id}>{lotLabel(row)}</option>)}</select></label>
    {source?<div className="metrics four"><Metric label="Available" value={`${fixed(source.balance)} ${source.unit}`}/><Metric label="Source" value={source.lot_code}/><Metric label="Product" value={source.product_name.slice(0,24)}/><Metric label="Location" value={source.location_code||"—"}/></div>:null}
    <label>Number of outputs<input type="number" min={1} max={8} step={1} disabled={actionType==="sample_pull"} value={outputCount} onChange={event=>setOutputCount(Math.max(1,Math.min(8,Number(event.target.value)||1)))}/></label>
    <label>Recorded loss / waste ({source?.unit??"unit"})<input type="number" min={0} step={.01} value={loss} onChange={event=>setLoss(Number(event.target.value))}/></label>
    <label>Reason / work note<input value={reason} placeholder="Optional operational reason" onChange={event=>setReason(event.target.value)}/></label>
    {sourceTracked?<label>Metrc action date<input type="date" value={actualDate} onChange={event=>setActualDate(event.target.value)}/></label>:null}
    <h4>Outputs</h4>
    {outputs.map((row,index)=><OutputCard
      key={index}
      index={index}
      row={row}
      actionType={actionType}
      products={products}
      source={source}
      update={patch=>updateOutput(index,patch)}
      metrcTracked={sourceTracked}
      availableTags={availableTags}
      tagsLoading={tagsLoading}
      linkedProductIds={linkedProductIds}
    />)}
    <div className="ps-balance"><strong>Mass balance preview</strong><br/><span>Source selected: {fixed(sourceToUse)} {source?.unit} · Outputs: {fixed(sourceTotal)} {source?.unit} · Loss: {fixed(loss)} {source?.unit} · Remaining source: {fixed(remaining)} {source?.unit}</span></div>

    {sourceTracked&&!metrcStatus?.ready?<div className="warning-banner">{metrcStatusError||metrcStatus?.message||"Metrc Sandbox is selected, but the exact trusted facility connection is not ready. Local commit stays blocked for this tracked source."}</div>:null}
    {sourceTracked&&metrcStatus?.ready&&sourceLink?.status!=="verified"?<div className="warning-banner">The source Package identity is {sourceLink?.status||"unavailable"}. Reconcile it in Package 360 before creating provider outputs.</div>:null}
    {sourceTracked&&loss>0?<div className="warning-banner">Tracked loss cannot be hidden inside package creation. Record the loss through a governed Metrc adjustment/waste reason, then run this transformation with zero unreported loss.</div>:null}
    {sourceTracked&&hasLabSample?<div className="warning-banner">Lab sample creation belongs to Metrc's dedicated testing-package workflow and is intentionally blocked from generic package creation.</div>:null}
    {sourceTracked&&!allOutputProductsLinked&&metrcStatus?.ready?<div className="warning-banner">Every output Product needs an exact verified Metrc Item link. Open a package using that Product in Package 360 and link its Item before continuing.</div>:null}
    {sourceTracked&&tagsError?<div className="form-error">{tagsError}</div>:null}
    {sourceTracked&&tagsTruncated?<div className="warning-banner">The available-tag lookup reached its bounded page limit. Confirm facility tag inventory before using a tag not shown here.</div>:null}

    {sourceToUse<=0?<div className="info-banner">Enter the source material used by at least one output to preview the run.</div>
      :source&&sourceToUse>source.balance+1e-9?<div className="form-error">This run consumes more material than the source package currently contains.</div>
      :preview.isLoading?<div className="state">Checking mass balance…</div>
      :preview.isError?<div className="warning-banner">{preview.error.message}</div>
      :preview.data?<>
        <div className="success-banner">Balanced · {fixed(preview.data.total_input)} {preview.data.source_unit} in · {fixed(preview.data.total_output_source_equivalent)} out · {fixed(preview.data.loss_quantity)} loss</div>
        {sourceTracked?<>
          <div className="ps-sync-note">Governed Metrc flow: create and semantically verify every child Package, verify the remaining source quantity, then commit the matching DoobieLogic lineage. A partial or unknown provider outcome stops in reconciliation and is never retried blindly.</div>
          {!canCommit?<div className="info-banner">Your current role can review Package Studio but cannot submit controlled package transformations.</div>:<button className="primary package-commit" disabled={!metrcReady||reviewPending} onClick={reviewTransformation}>{reviewPending?"Checking fresh Metrc state…":`Review Metrc ${actionLabel}`}</button>}
          {!allTagsReady&&metrcStatus?.ready?<div className="info-banner">Choose one different currently available Metrc package tag for every output.</div>:null}
        </>:<>
          <div className="ps-sync-note">This source is not on the governed Metrc path for the current operating mode. The commit stays inside DoobieLogic and records no provider write.</div>
          <label className="toggle"><input type="checkbox" checked={confirm} onChange={event=>setConfirm(event.target.checked)}/> I reviewed the source, outputs, and mass balance.</label>
          {!canCommit?<div className="info-banner">Your current role can review Package Studio but cannot commit inventory transformations.</div>:<button className="primary package-commit" disabled={!confirm||localCommitPending} onClick={localCommit}>{localCommitPending?"Committing…":`Commit ${actionLabel}`}</button>}
        </>}
      </>:null}

    {reviewError?<div className="form-error">{reviewError}</div>:null}
    {transformationPreview?<TransformationReview preview={transformationPreview} cancel={cancelTransformation} execute={executeTransformation} pending={executePending} error={executeError}/>:null}
    {transformationResult?<div className={transformationResult.verified?"success-banner":"warning-banner"}><strong>{transformationResult.verified?"Verified":"Reconciliation required"}</strong><br/>{transformationResult.message}<br/><small>Transaction {transformationResult.transaction_id}{transformationResult.external_reference?` · Provider ${transformationResult.external_reference}`:""}</small></div>:null}
    {localCommitError?<div className="form-error">{localCommitError}</div>:null}
    {commitMessage?<div className="success-banner">{commitMessage}</div>:null}
  </section>;
}

function OutputCard({index,row,actionType,products,source,update,metrcTracked,availableTags,tagsLoading,linkedProductIds}:{index:number;row:Output;actionType:string;products:Product[];source?:Lot;update:(patch:Partial<Output>)=>void;metrcTracked:boolean;availableTags:string[];tagsLoading:boolean;linkedProductIds:Set<string>}){
  const locked=actionType==="breakdown"||actionType==="sample_pull";
  const productId=locked?(source?.product_id??""):row.product_id;
  const product=products.find(item=>item.product_id===productId);
  const purposeOptions=actionType==="sample_pull"?["Lab sample","Trade sample","Retail sample"]:["Standard output","Trade sample","Retail sample"];
  const purposeLabel=Object.entries(PURPOSES).find(([,value])=>value===row.purpose)?.[0]??purposeOptions[0];
  return <article className="inventory-panel package-output-card">
    <div className="ps-output-caption">OUTPUT {index+1}</div>
    <div className="package-output-grid">
      <label>Output product{locked?<input value={product?.name??""} disabled/>:<select value={productId} onChange={event=>{const next=products.find(item=>item.product_id===event.target.value);update({product_id:event.target.value,inventory_unit:next?.base_unit||"unit"})}}>{products.map(item=><option value={item.product_id} key={item.product_id}>{productLabel(item)}</option>)}</select>}</label>
      <label>Lot / package code<input value={row.lot_code} placeholder={`PS-${String(index+1).padStart(2,"0")}`} onChange={event=>update({lot_code:event.target.value})}/></label>
      {metrcTracked?<label>Metrc package tag<select value={row.compliance_package_id} disabled={tagsLoading} onChange={event=>update({compliance_package_id:event.target.value})}><option value="">{tagsLoading?"Loading current tags…":"Select available tag…"}</option>{availableTags.map(tag=><option key={tag} value={tag}>{tag}</option>)}</select></label>:<label>Compliance package reference<input value={row.compliance_package_id} placeholder="Optional local reference" onChange={event=>update({compliance_package_id:event.target.value})}/></label>}
      <label>Finished quantity<input type="number" min={0} step={1} value={row.inventory_quantity} onChange={event=>update({inventory_quantity:Number(event.target.value)})}/></label>
      <label>Finished unit<input value={row.inventory_unit||product?.base_unit||"unit"} onChange={event=>update({inventory_unit:event.target.value})}/></label>
      <label>Source used ({source?.unit??"unit"})<input type="number" min={0} step={.01} value={row.source_equivalent_quantity} onChange={event=>update({source_equivalent_quantity:Number(event.target.value)})}/></label>
      {actionType==="rework"||actionType==="correction"?null:<label>{actionType==="sample_pull"?"Sample type":"Output purpose"}<select value={purposeLabel} onChange={event=>update({purpose:PURPOSES[event.target.value]})}>{purposeOptions.map(value=><option key={value}>{value}</option>)}</select></label>}
    </div>
    {metrcTracked&&productId&&!linkedProductIds.has(productId)?<div className="warning-banner">This Product is not linked to a verified Metrc Item yet.</div>:null}
  </article>;
}

function TransformationReview({preview,cancel,execute,pending,error}:{preview:TransformationPreview;cancel:()=>void;execute:()=>void;pending:boolean;error:string}){
  return <div className="inventory-panel compact">
    <div className="eyebrow">CONFIRM TRACKED PACKAGE TRANSFORMATION</div>
    <h3>{preview.summary.title}</h3>
    <div className="two-column-grid">
      <div><Row label="Action" value={preview.summary.action}/><Row label="Source Package" value={preview.summary.source_package}/><Row label="Source used" value={`${fixed(preview.summary.source_quantity)} ${preview.summary.source_unit}`}/></div>
      <div><Row label="Source remaining" value={`${fixed(preview.summary.source_remaining)} ${preview.summary.source_unit}`}/><Row label="Output packages" value={String(preview.summary.output_count)}/></div>
    </div>
    <h4>Provider outputs</h4>
    {preview.summary.outputs.map((row,index)=><div className="catalog-row" key={`${row.metrc_tag}-${index}`}><strong>{row.lot_code} · {row.metrc_item}</strong><span>{row.metrc_tag}</span><small>{fixed(row.quantity)} {row.unit}</small></div>)}
    <div className="warning-banner">No local inventory has been committed yet. Confirming creates the reviewed Metrc children first. HTTP 200 is only Accepted; every child and the source balance must pass fresh semantic readback before DoobieLogic commits lineage.</div>
    <details><summary>Compliance evidence details</summary><pre>{JSON.stringify(preview.compliance_evidence,null,2)}</pre></details>
    <div className="heading-actions"><button className="secondary" onClick={cancel}>Cancel</button><button className="primary" disabled={pending} onClick={execute}>{pending?"Creating & verifying…":"Confirm Metrc transformation"}</button></div>
    {error?<div className="form-error">{error}</div>:null}
  </div>;
}

function SourceTrail({lots,initialLotId}:{lots:Lot[];initialLotId:string}){
  const [lotId,setLotId]=useState(initialLotId||lots[0]?.lot_id||"");
  const effective=lots.some(row=>row.lot_id===lotId)?lotId:(lots[0]?.lot_id??"");
  const trail=useQuery({queryKey:["package-studio-trail",effective],enabled:!!effective,queryFn:({signal})=>apiGet<Trail>(`/api/v1/package-studio/source-trail/${effective}`,signal)});
  if(!lots.length)return <div className="info-banner">No available durable packages are present in this facility.</div>;
  return <section className="package-source-trail">
    <label>Package<select value={effective} onChange={event=>setLotId(event.target.value)}>{lots.map(row=><option value={row.lot_id} key={row.lot_id}>{lotLabel(row)}</option>)}</select></label>
    {trail.isLoading?<div className="state">Loading Source Trail…</div>:null}
    {trail.isError?<div className="form-error">{trail.error.message}</div>:null}
    {trail.data?<><div className="metrics three"><Metric label="Current balance" value={`${fixed(trail.data.lot.balance)} ${trail.data.lot.unit}`}/><Metric label="Package" value={trail.data.lot.lot_code}/><Metric label="Product" value={trail.data.lot.product_name.slice(0,24)}/></div><h4>Parent source</h4>{trail.data.created_by?<><strong>{trail.data.created_by.run_number} · {title(trail.data.created_by.action_type)}</strong><DataTable rows={trail.data.created_by.parents}/></>:<p className="ps-subtitle">This package does not have a Package Studio parent event yet.</p>}<h4>Downstream use</h4>{trail.data.used_by.length?trail.data.used_by.map(run=><details className="streamlit-expander" key={`${run.run_number}-${run.quantity_consumed}`}><summary>{run.run_number} · {title(run.action_type)}</summary><div className="streamlit-expander-body"><p className="ps-subtitle">Consumed {fixed(run.quantity_consumed)} {run.unit}</p><DataTable rows={run.outputs}/></div></details>):<p className="ps-subtitle">No downstream Package Studio transformations are recorded from this package.</p>}</>:null}
  </section>;
}

function RecentRuns({runs}:{runs:Run[]}){
  if(!runs.length)return <div className="info-banner">No Package Studio runs have been committed in this facility yet.</div>;
  const rows=runs.map(row=>({...row,action_type:title(row.action_type),external_sync_status:title(row.external_sync_status)}));
  return <DataTable rows={rows}/>;
}
function DataTable({rows}:{rows:Record<string,unknown>[]}){const columns=rows.length?Object.keys(rows[0]):[];return <div className="table-wrap"><table><thead><tr>{columns.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{columns.map(column=><td key={column}>{String(row[column]??"")}</td>)}</tr>)}</tbody></table></div>}
function Metric({label,value}:{label:string;value:string}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function Row({label,value}:{label:string;value:string}){return <div className="catalog-row"><strong>{label}</strong><span>{value||"—"}</span></div>}
function lotLabel(lot:Lot){return `${lot.product_name} · ${lot.lot_code}${lot.compliance_package_id?` · ${lot.compliance_package_id}`:""} · ${fixed(lot.balance)} ${lot.unit}`}
function productLabel(product:Product){return `${product.name}${product.sku?` · ${product.sku}`:""}`}
