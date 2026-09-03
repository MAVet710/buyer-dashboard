import { InventoryDrivenLabelWorkflow } from "../components/InventoryDrivenLabelWorkflow";
import { LabelStudioPage } from "./LabelStudioPage";

export function LabelStudioWorkspacePage(){
  return <>
    <div className="page"><InventoryDrivenLabelWorkflow /></div>
    <LabelStudioPage />
  </>;
}
