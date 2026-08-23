import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type Lot = { lot_id:string; lot_code:string; compliance_package_id:string; product_id:string; product_name:string; sku:string; balance:number; unit:string; location_code:string };
type Product = { product_id:string; name:string; sku:string; item_type:string; base_unit:string };
type Run = { id:string; run_number:string; action_type:string; status:string; source_quantity:number; source_unit:string; loss_quantity:number; external_sync_status:string; created_by:string; committed_at:string };
type Workspace = { lots:Lot[]; products:Product[]; runs:Run[]; can_commit:boolean };
type Preview = { action_type:string; total_input:number; total_output_source_equivalent:number; loss_quantity:number; source_unit:string; balanced:boolean; difference:number; output_count:number };
type CommitResult = { run_id:string; run_number:string; output_lot_ids:string[]; input_transactions:number; output_transactions:number };
type Output = { product_id:string; lot_code:string; compliance_package_id:string; inventory_quantity:number; inventory_unit:string; source_equivalent_quantity:number; purpose:string };
type Trail = { lot:{lot_id:string;lot_code:string;compliance_package_id:string;product_name:string;balance:number;unit:string}; created_by:null|{run_number:string;action_type:string;parents:{lot_id:string;lot_code:string;product_name:string;quantity:number;unit:string}[]}; used_by:{run_number:string;action_type:string;quantity_consumed:number;unit:string;outputs:{lot_id:string;lot_code:string;product_id:string;inventory_quantity:number;inventory_unit:string;purpose:string}[]}[] };

const ACTIONS = [
  ["Breakdown","breakdown"], ["Pack Down","pack_down"], ["Build Run","build_run"],
  ["Multi-Build","multi_build"], ["Sample Pull","sample_pull"], ["Rework","rework"],
  ["Source Correction","correction"],
] as const;
const PURPOSES:Record<string,string> = {"Standard output":"standard","Lab sample":"lab_sample","Trade sample":"trade_sample","Retail sample":"retail_sample","Rework output":"rework","Corrected output":"corrected"};
const EMPTY_LOTS:Lot[]=[]; const EMPTY_PRODUCTS:Product[]=[];

const blankOutput = ():Output => ({product_id:"",lot_code:"",compliance_package_id:"",inventory_quantity:0,inventory_unit:"unit",source_equivalent_quantity:0,purpose:"standard"});
const title = (value:string) => value.replaceAll("_"," ").replace(/\b\w/g,letter=>letter.toUpperCase());
const fixed = (value:number) => value.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});

export function PackageStudioPage({initialLotId=""}:{initialLotId?:string}={}) {
  const client=useQueryClient();
  const workspace=useQuery({queryKey:["package-studio"],queryFn:({signal})=>apiGet<Workspace>("/api/v1/package-studio/workspace",signal)});
  const [tab,setTab]=useState<"New Run"|"Source Trail"|"Recent Runs">("New Run");
  const [actionLabel,setActionLabel]=useState<(typeof ACTIONS)[number][0]>("Breakdown");
  const [lotId,setLotId]=useState(initialLotId); const [outputCount,setOutputCount]=useState(2);
  const [loss,setLoss]=useState(0); const [reason,setReason]=useState(""); const [outputs,setOutputs]=useState<Output[]>([blankOutput(),blankOutput()]);
  const [confirm,setConfirm]=useState(false); const [commitMessage,setCommitMessage]=useState("");
  const lots=workspace.data?.lots??EMPTY_LOTS; const products=workspace.data?.products??EMPTY_PRODUCTS;
  const effectiveLotId=lots.some(row=>row.lot_id===lotId)?lotId:lots.some(row=>row.lot_id===initialLotId)?initialLotId:(lots[0]?.lot_id??"");
  const source=lots.find(row=>row.lot_id===effectiveLotId); const actionType=ACTIONS.find(([label])=>label===actionLabel)?.[1]??"breakdown";

  useEffect(()=>{if(effectiveLotId&&lotId!==effectiveLotId)setLotId(effectiveLotId)},[effectiveLotId,lotId]);
  useEffect(()=>{setOutputs(current=>Array.from({length:outputCount},(_,index)=>current[index]??blankOutput()));setConfirm(false)},[outputCount]);

  const configuredOutputs=useMemo(()=>outputs.slice(0,outputCount).map(row=>{
    const locked=actionType==="breakdown"||actionType==="sample_pull";
    const productId=locked?(source?.product_id??""):(row.product_id||products[0]?.product_id||"");
    const product=products.find(item=>item.product_id===productId);
    const purpose=actionType==="sample_pull"?(row.purpose==="lab_sample"||row.purpose==="trade_sample"||row.purpose==="retail_sample"?row.purpose:"lab_sample"):actionType==="rework"?"rework":actionType==="correction"?"corrected":row.purpose;
    return {...row,product_id:productId,inventory_unit:row.inventory_unit==="unit"&&product?.base_unit?product.base_unit:row.inventory_unit,purpose};
  }),[actionType,outputCount,outputs,products,source]);
  const sourceTotal=configuredOutputs.reduce((sum,row)=>sum+row.source_equivalent_quantity,0); const sourceToUse=sourceTotal+loss; const remaining=(source?.balance??0)-sourceToUse;
  const plan=useMemo(()=>({action_type:actionType,inputs:[{lot_id:source?.lot_id??"",quantity:sourceToUse,unit:source?.unit??"unit",purpose:"source"}],outputs:configuredOutputs.map(row=>({...row,source_equivalent_unit:source?.unit??"unit",location_code:"FINISHED-GOODS",notes:""})),loss_quantity:loss,source_unit:source?.unit??"unit",reason}),[actionType,configuredOutputs,loss,reason,source,sourceToUse]);
  const canPreview=Boolean(source&&sourceToUse>0&&sourceToUse<=source.balance+1e-9);
  const preview=useQuery({queryKey:["package-studio-preview",plan],enabled:canPreview,queryFn:()=>apiPost<Preview>("/api/v1/package-studio/preview",plan),retry:false});
  const commit=useMutation({mutationFn:()=>apiPost<CommitResult>("/api/v1/package-studio/commit",plan),onSuccess:result=>{setCommitMessage(`${result.run_number} committed with ${result.output_lot_ids.length} output package(s).`);setConfirm(false);client.invalidateQueries({queryKey:["package-studio"]})}});
  const changeAction=(label:(typeof ACTIONS)[number][0])=>{const type=ACTIONS.find(row=>row[0]===label)?.[1];const count=type==="breakdown"||type==="multi_build"?2:1;setActionLabel(label);setOutputCount(count);setOutputs(Array.from({length:count},blankOutput));setConfirm(false);setCommitMessage("")};
  const updateOutput=(index:number,patch:Partial<Output>)=>{setOutputs(current=>current.map((row,rowIndex)=>rowIndex===index?{...row,...patch}:row));setConfirm(false)};

  return <div className="package-studio-workspace">
    <div className="ps-kicker">PACKAGE STUDIO</div><h2>Package transformation</h2><p className="ps-subtitle">Break down, pack down, build, sample, correct, and trace packages from one auditable work window.</p>
    <div className="view-tabs package-studio-tabs">{(["New Run","Source Trail","Recent Runs"] as const).map(value=><button className={tab===value?"active":""} key={value} onClick={()=>setTab(value)}>{value}</button>)}</div>
    {workspace.isLoading?<div className="state">Loading Package Studio…</div>:null}{workspace.isError?<div className="form-error">{workspace.error.message}</div>:null}
    {workspace.data&&tab==="New Run"?<NewRun lots={lots} products={products} source={source} lotId={effectiveLotId} setLotId={value=>{setLotId(value);setConfirm(false)}} actionLabel={actionLabel} changeAction={changeAction} actionType={actionType} outputCount={outputCount} setOutputCount={setOutputCount} loss={loss} setLoss={value=>{setLoss(value);setConfirm(false)}} reason={reason} setReason={setReason} outputs={configuredOutputs} updateOutput={updateOutput} sourceTotal={sourceTotal} sourceToUse={sourceToUse} remaining={remaining} preview={preview} canCommit={workspace.data.can_commit} confirm={confirm} setConfirm={setConfirm} commit={()=>commit.mutate()} commitPending={commit.isPending} commitError={commit.isError?commit.error.message:""} commitMessage={commitMessage}/>:null}
    {workspace.data&&tab==="Source Trail"?<SourceTrail lots={lots} initialLotId={effectiveLotId}/>:null}
    {workspace.data&&tab==="Recent Runs"?<RecentRuns runs={workspace.data.runs}/>:null}
  </div>;
}

type NewRunProps={lots:Lot[];products:Product[];source?:Lot;lotId:string;setLotId:(value:string)=>void;actionLabel:(typeof ACTIONS)[number][0];changeAction:(value:(typeof ACTIONS)[number][0])=>void;actionType:string;outputCount:number;setOutputCount:(value:number)=>void;loss:number;setLoss:(value:number)=>void;reason:string;setReason:(value:string)=>void;outputs:Output[];updateOutput:(index:number,patch:Partial<Output>)=>void;sourceTotal:number;sourceToUse:number;remaining:number;preview:ReturnType<typeof useQuery<Preview>>;canCommit:boolean;confirm:boolean;setConfirm:(value:boolean)=>void;commit:()=>void;commitPending:boolean;commitError:string;commitMessage:string};
function NewRun({lots,products,source,lotId,setLotId,actionLabel,changeAction,actionType,outputCount,setOutputCount,loss,setLoss,reason,setReason,outputs,updateOutput,sourceTotal,sourceToUse,remaining,preview,canCommit,confirm,setConfirm,commit,commitPending,commitError,commitMessage}:NewRunProps){
  if(!lots.length)return <><div className="info-banner">No durable available packages were found for this facility.</div><p className="ps-subtitle">Package Studio works from Supabase-backed inventory lots so Source Trail remains auditable.</p></>;
  if(!products.length)return <div className="info-banner">No active products are available for Package Studio outputs.</div>;
  return <section className="package-studio-new-run">
    <label>Package action<select value={actionLabel} onChange={event=>changeAction(event.target.value as (typeof ACTIONS)[number][0])}>{ACTIONS.map(([label])=><option key={label}>{label}</option>)}</select></label>
    <label>Source package<select value={lotId} onChange={event=>setLotId(event.target.value)}>{lots.map(row=><option value={row.lot_id} key={row.lot_id}>{lotLabel(row)}</option>)}</select></label>
    {source?<div className="metrics four"><Metric label="Available" value={`${fixed(source.balance)} ${source.unit}`}/><Metric label="Source" value={source.lot_code}/><Metric label="Product" value={source.product_name.slice(0,24)}/><Metric label="Location" value={source.location_code||"—"}/></div>:null}
    <label>Number of outputs<input type="number" min={1} max={8} step={1} disabled={actionType==="sample_pull"} value={outputCount} onChange={event=>setOutputCount(Math.max(1,Math.min(8,Number(event.target.value)||1)))}/></label>
    <label>Recorded loss / waste ({source?.unit??"unit"})<input type="number" min={0} step={.01} value={loss} onChange={event=>setLoss(Number(event.target.value))}/></label>
    <label>Reason / work note<input value={reason} placeholder="Optional operational reason" onChange={event=>setReason(event.target.value)}/></label>
    <h4>Outputs</h4>{outputs.map((row,index)=><OutputCard key={index} index={index} row={row} actionType={actionType} products={products} source={source} update={patch=>updateOutput(index,patch)}/>) }
    <div className="ps-balance"><strong>Mass balance preview</strong><br/><span>Source selected: {fixed(sourceToUse)} {source?.unit} · Outputs: {fixed(sourceTotal)} {source?.unit} · Loss: {fixed(loss)} {source?.unit} · Remaining source: {fixed(remaining)} {source?.unit}</span></div>
    {sourceToUse<=0?<div className="info-banner">Enter the source material used by at least one output to preview the run.</div>:source&&sourceToUse>source.balance+1e-9?<div className="form-error">This run consumes more material than the source package currently contains.</div>:preview.isLoading?<div className="state">Checking mass balance…</div>:preview.isError?<div className="warning-banner">{preview.error.message}</div>:preview.data?<><div className="success-banner">Balanced · {fixed(preview.data.total_input)} {preview.data.source_unit} in · {fixed(preview.data.total_output_source_equivalent)} out · {fixed(preview.data.loss_quantity)} loss</div><div className="ps-sync-note">Phase 1 records the package operation and METRC references in Buyer Dash, but it does not silently create or adjust packages in METRC. External sync remains explicitly Not requested.</div><label className="toggle"><input type="checkbox" checked={confirm} onChange={event=>setConfirm(event.target.checked)}/> I reviewed the source, outputs, and mass balance.</label>{!canCommit?<div className="info-banner">Your current role can review Package Studio but cannot commit inventory transformations.</div>:<button className="primary package-commit" disabled={!confirm||commitPending} onClick={commit}>{commitPending?"Committing…":`Commit ${actionLabel}`}</button>}</>:null}
    {commitError?<div className="form-error">{commitError}</div>:null}{commitMessage?<div className="success-banner">{commitMessage}</div>:null}
  </section>;
}

function OutputCard({index,row,actionType,products,source,update}:{index:number;row:Output;actionType:string;products:Product[];source?:Lot;update:(patch:Partial<Output>)=>void}){
  const locked=actionType==="breakdown"||actionType==="sample_pull"; const productId=locked?(source?.product_id??""):row.product_id; const product=products.find(item=>item.product_id===productId);
  const purposeOptions=actionType==="sample_pull"?["Lab sample","Trade sample","Retail sample"]:["Standard output","Trade sample","Retail sample"];
  const purposeLabel=Object.entries(PURPOSES).find(([,value])=>value===row.purpose)?.[0]??purposeOptions[0];
  return <article className="inventory-panel package-output-card"><div className="ps-output-caption">OUTPUT {index+1}</div><div className="package-output-grid">
    <label>Output product{locked?<input value={product?.name??""} disabled/>:<select value={productId} onChange={event=>{const next=products.find(item=>item.product_id===event.target.value);update({product_id:event.target.value,inventory_unit:next?.base_unit||"unit"})}}>{products.map(item=><option value={item.product_id} key={item.product_id}>{productLabel(item)}</option>)}</select>}</label>
    <label>Lot / package code<input value={row.lot_code} placeholder={`PS-${String(index+1).padStart(2,"0")}`} onChange={event=>update({lot_code:event.target.value})}/></label>
    <label>METRC package tag<input value={row.compliance_package_id} placeholder="Optional in Phase 1" onChange={event=>update({compliance_package_id:event.target.value})}/></label>
    <label>Finished quantity<input type="number" min={0} step={1} value={row.inventory_quantity} onChange={event=>update({inventory_quantity:Number(event.target.value)})}/></label>
    <label>Finished unit<input value={row.inventory_unit||product?.base_unit||"unit"} onChange={event=>update({inventory_unit:event.target.value})}/></label>
    <label>Source used ({source?.unit??"unit"})<input type="number" min={0} step={.01} value={row.source_equivalent_quantity} onChange={event=>update({source_equivalent_quantity:Number(event.target.value)})}/></label>
    {actionType==="rework"||actionType==="correction"?null:<label>{actionType==="sample_pull"?"Sample type":"Output purpose"}<select value={purposeLabel} onChange={event=>update({purpose:PURPOSES[event.target.value]})}>{purposeOptions.map(value=><option key={value}>{value}</option>)}</select></label>}
  </div></article>;
}

function SourceTrail({lots,initialLotId}:{lots:Lot[];initialLotId:string}){const [lotId,setLotId]=useState(initialLotId||lots[0]?.lot_id||"");const effective=lots.some(row=>row.lot_id===lotId)?lotId:(lots[0]?.lot_id??"");const trail=useQuery({queryKey:["package-studio-trail",effective],enabled:!!effective,queryFn:({signal})=>apiGet<Trail>(`/api/v1/package-studio/source-trail/${effective}`,signal)});if(!lots.length)return <div className="info-banner">No available durable packages are present in this facility.</div>;return <section className="package-source-trail"><label>Package<select value={effective} onChange={event=>setLotId(event.target.value)}>{lots.map(row=><option value={row.lot_id} key={row.lot_id}>{lotLabel(row)}</option>)}</select></label>{trail.isLoading?<div className="state">Loading Source Trail…</div>:null}{trail.isError?<div className="form-error">{trail.error.message}</div>:null}{trail.data?<><div className="metrics three"><Metric label="Current balance" value={`${fixed(trail.data.lot.balance)} ${trail.data.lot.unit}`}/><Metric label="Package" value={trail.data.lot.lot_code}/><Metric label="Product" value={trail.data.lot.product_name.slice(0,24)}/></div><h4>Parent source</h4>{trail.data.created_by?<><strong>{trail.data.created_by.run_number} · {title(trail.data.created_by.action_type)}</strong><DataTable rows={trail.data.created_by.parents}/></>:<p className="ps-subtitle">This package does not have a Package Studio parent event yet.</p>}<h4>Downstream use</h4>{trail.data.used_by.length?trail.data.used_by.map(run=><details className="streamlit-expander" key={`${run.run_number}-${run.quantity_consumed}`}><summary>{run.run_number} · {title(run.action_type)}</summary><div className="streamlit-expander-body"><p className="ps-subtitle">Consumed {fixed(run.quantity_consumed)} {run.unit}</p><DataTable rows={run.outputs}/></div></details>):<p className="ps-subtitle">No downstream Package Studio transformations are recorded from this package.</p>}</>:null}</section>}

function RecentRuns({runs}:{runs:Run[]}){if(!runs.length)return <div className="info-banner">No Package Studio runs have been committed in this facility yet.</div>;const rows=runs.map(row=>({...row,action_type:title(row.action_type),external_sync_status:title(row.external_sync_status)}));return <DataTable rows={rows}/>}
function DataTable({rows}:{rows:Record<string,unknown>[]}){const columns=rows.length?Object.keys(rows[0]):[];return <div className="table-wrap"><table><thead><tr>{columns.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{columns.map(column=><td key={column}>{String(row[column]??"")}</td>)}</tr>)}</tbody></table></div>}
function Metric({label,value}:{label:string;value:string}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function lotLabel(lot:Lot){return `${lot.product_name} · ${lot.lot_code}${lot.compliance_package_id?` · ${lot.compliance_package_id}`:""} · ${fixed(lot.balance)} ${lot.unit}`}
function productLabel(product:Product){return `${product.name}${product.sku?` · ${product.sku}`:""}`}
