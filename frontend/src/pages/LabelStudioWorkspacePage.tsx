import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { InventoryDrivenLabelWorkflow } from "../components/InventoryDrivenLabelWorkflow";
import { LabelRunHistory } from "../components/LabelRunHistory";
import { apiGet } from "../lib/api";
import { LabelStudioPage } from "./LabelStudioPage";

type LabelStudioMode = "create" | "history" | "advanced";
type AccountContext = {
  user?: { id?: string; role?: string };
  organization?: { id?: string; slug?: string } | null;
  facility_id?: string;
  facilities?: Array<{ id:string;code:string;name?:string }>;
};
const ADVANCED_DEFAULT_ROLES = new Set(["qa", "dev", "admin"]);
const WRITE_ROLES = new Set(["dev", "admin", "supervisor", "operator", "qa"]);

export function LabelStudioWorkspacePage(){
  const [params,setParams]=useSearchParams();
  const requestedMode=params.get("labelMode");
  const selectedRunId=params.get("labelRun")??"";
  const sourceLotId=params.get("sourceLot")??"";
  const [mode,setMode]=useState<LabelStudioMode>(selectedRunId||requestedMode==="history"?"history":requestedMode==="advanced"?"advanced":"create");
  const modeChosenByUser=useRef(Boolean(requestedMode||selectedRunId||sourceLotId));
  const context=useQuery({queryKey:["account-context"],queryFn:({signal})=>apiGet<AccountContext>("/api/v1/account/context",signal)});
  const selectedFacility=context.data?.facilities?.find(row=>row.id===context.data?.facility_id);
  const role=String(context.data?.user?.role??"").trim().toLowerCase();
  const organizationId=context.data?.organization?.id??"";
  const facilityId=context.data?.facility_id??"";
  const scope=`${organizationId}:${facilityId}:${context.data?.user?.id??""}`;
  const sandboxTestPass=role==="dev"&&String(context.data?.organization?.slug??"").trim().toLowerCase()==="dev-sandbox"&&String(selectedFacility?.code??"").trim().toUpperCase()==="SANDBOX";
  useEffect(()=>{
    if(selectedRunId||requestedMode==="history"){setMode("history");return;}
    if(requestedMode==="create"||sourceLotId){setMode("create");return;}
    if(requestedMode==="advanced"){setMode("advanced");return;}
    if(!modeChosenByUser.current&&ADVANCED_DEFAULT_ROLES.has(role))setMode("advanced");
  },[requestedMode,selectedRunId,sourceLotId,role]);
  const chooseMode=(next:LabelStudioMode)=>{
    modeChosenByUser.current=true;setMode(next);
    setParams(previous=>{const updated=new URLSearchParams(previous);updated.set("labelMode",next);updated.delete("labelRun");updated.delete("sourceLot");return updated;});
  };
  const selectRun=(id:string)=>{
    setParams(previous=>{const updated=new URLSearchParams(previous);updated.set("labelMode","history");if(id)updated.set("labelRun",id);else updated.delete("labelRun");return updated;});
  };
  return <div className="label-studio-workspace">
    <div className="page">
      <div className="eyebrow">COMPLIANCE · LABEL STUDIO</div>
      <div className="page-heading"><div><h1>Label Studio</h1><p>Create finished labels from existing inventory and Product Master data. Reopen saved labels in History &amp; Reprints. Advanced testing-label templates and LabelGuard tools remain available.</p></div></div>
      {sandboxTestPass?<div className="sandbox-environment-notice" role="status"><strong>DEV SANDBOX · SANDBOX OPERATION · ALL OPERATIONAL DATA IS TEST DATA</strong><span>Guarded print testing is enabled here only. Label/COA readiness and sandbox tag-availability gates may receive an audited test pass so DEV can exercise the complete print workflow. Production and customer-tenant safeguards are not changed.</span></div>:null}
      <div className="view-tabs parity-tabs" role="tablist" aria-label="Label Studio mode">
        <button className={mode==="create"?"active":""} type="button" role="tab" aria-selected={mode==="create"} onClick={()=>chooseMode("create")}>Create labels</button>
        <button className={mode==="history"?"active":""} type="button" role="tab" aria-selected={mode==="history"} onClick={()=>chooseMode("history")}>History &amp; Reprints</button>
        <button className={mode==="advanced"?"active":""} type="button" role="tab" aria-selected={mode==="advanced"} onClick={()=>chooseMode("advanced")}>Advanced LabelGuard &amp; templates</button>
      </div>
      {context.isLoading?<div className="state">Loading facility context…</div>:null}
      {context.isError?<div className="state error">Facility context is unavailable. {context.error.message}</div>:null}
      {mode==="create"&&context.data?<InventoryDrivenLabelWorkflow key={`${scope}:${sourceLotId}`} sandboxTestPass={sandboxTestPass} canWrite={WRITE_ROLES.has(role)} initialSourceLotId={sourceLotId}/>:null}
      {mode==="history"&&context.data?<LabelRunHistory key={scope} organizationId={organizationId} facilityId={facilityId} canWrite={WRITE_ROLES.has(role)} selectedRunId={selectedRunId} onSelect={selectRun} onStartNew={()=>chooseMode("create")}/>:null}
    </div>
    {mode==="advanced"?<LabelStudioPage />:null}
  </div>;
}
