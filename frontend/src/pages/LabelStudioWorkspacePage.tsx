import { useState } from "react";
import { InventoryDrivenLabelWorkflow } from "../components/InventoryDrivenLabelWorkflow";
import { LabelStudioPage } from "./LabelStudioPage";

type LabelStudioMode = "create" | "advanced";

export function LabelStudioWorkspacePage(){
  const [mode,setMode]=useState<LabelStudioMode>("create");
  return <div className="label-studio-workspace">
    <div className="page">
      <div className="eyebrow">COMPLIANCE · LABEL STUDIO</div>
      <div className="page-heading"><div><h1>Label Studio + LabelGuard</h1><p>Create finished labels from existing inventory and Product Master data. Advanced testing-label templates and LabelGuard tools remain available without cluttering the normal operator workflow.</p></div></div>
      <div className="view-tabs parity-tabs" role="tablist" aria-label="Label Studio mode">
        <button className={mode==="create"?"active":""} type="button" role="tab" aria-selected={mode==="create"} onClick={()=>setMode("create")}>Create labels</button>
        <button className={mode==="advanced"?"active":""} type="button" role="tab" aria-selected={mode==="advanced"} onClick={()=>setMode("advanced")}>Advanced LabelGuard & templates</button>
      </div>
      {mode==="create"?<InventoryDrivenLabelWorkflow />:null}
    </div>
    {mode==="advanced"?<LabelStudioPage />:null}
  </div>;
}
