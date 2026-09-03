import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { InventoryDrivenLabelWorkflow } from "../components/InventoryDrivenLabelWorkflow";
import { apiGet } from "../lib/api";
import { LabelStudioPage } from "./LabelStudioPage";

type LabelStudioMode = "create" | "advanced";
type AccountContext = {
  user?: { role?: string };
  organization?: { slug?: string } | null;
  facility_id?: string;
  facilities?: Array<{ id:string;code:string;name?:string }>;
};

const ADVANCED_DEFAULT_ROLES = new Set(["qa", "dev", "admin"]);

export function LabelStudioWorkspacePage(){
  const [mode,setMode]=useState<LabelStudioMode>("create");
  const modeChosenByUser=useRef(false);
  const context=useQuery({
    queryKey:["account-context"],
    queryFn:({signal})=>apiGet<AccountContext>("/api/v1/account/context",signal),
  });
  const selectedFacility=context.data?.facilities?.find(row=>row.id===context.data?.facility_id);
  const sandboxTestPass=
    String(context.data?.user?.role??"").trim().toLowerCase()==="dev"&&
    String(context.data?.organization?.slug??"").trim().toLowerCase()==="dev-sandbox"&&
    String(selectedFacility?.code??"").trim().toUpperCase()==="SANDBOX";

  useEffect(()=>{
    if(modeChosenByUser.current)return;
    const role=String(context.data?.user?.role??"").trim().toLowerCase();
    if(ADVANCED_DEFAULT_ROLES.has(role))setMode("advanced");
  },[context.data?.user?.role]);

  const chooseMode=(next:LabelStudioMode)=>{
    modeChosenByUser.current=true;
    setMode(next);
  };

  return <div className="label-studio-workspace">
    <div className="page">
      <div className="eyebrow">COMPLIANCE · LABEL STUDIO</div>
      <div className="page-heading"><div><h1>Label Studio</h1><p>Create finished labels from existing inventory and Product Master data. Advanced testing-label templates and LabelGuard tools remain available without cluttering the normal operator workflow.</p></div></div>
      {sandboxTestPass?<div className="sandbox-environment-notice" role="status"><strong>DEV SANDBOX · SANDBOX OPERATION · ALL OPERATIONAL DATA IS TEST DATA</strong><span>Guarded print testing is enabled here only. Label/COA readiness and sandbox tag-availability gates may receive an audited test pass so DEV can exercise the complete print workflow. Production and customer-tenant safeguards are not changed.</span></div>:null}
      <div className="view-tabs parity-tabs" role="tablist" aria-label="Label Studio mode">
        <button className={mode==="create"?"active":""} type="button" role="tab" aria-selected={mode==="create"} onClick={()=>chooseMode("create")}>Create labels</button>
        <button className={mode==="advanced"?"active":""} type="button" role="tab" aria-selected={mode==="advanced"} onClick={()=>chooseMode("advanced")}>Advanced LabelGuard & templates</button>
      </div>
      {mode==="create"?<InventoryDrivenLabelWorkflow sandboxTestPass={sandboxTestPass}/>:null}
    </div>
    {mode==="advanced"?<LabelStudioPage />:null}
  </div>;
}
