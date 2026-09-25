import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { WhiteLabelExecutionHandoff } from "./components/WhiteLabelExecutionHandoff";
import { WhiteLabelRepackPage, type DurablePlan } from "./pages/WhiteLabelRepackPage";
import { calculate, formDefaults, planRow } from "./pages/whiteLabelRepackParity";

vi.mock("./lib/api",()=>({apiGet:vi.fn(),apiPost:vi.fn(),apiDownload:vi.fn(),downloadBlob:vi.fn()}));
vi.mock("@tanstack/react-query",()=>({useQuery:({queryKey}:{queryKey:string[]})=>({data:queryKey[0]==="white-label-plans"?[{id:"saved-plan",name:"Durable lot",status:"draft"}]:[],refetch:vi.fn()})}));

describe("durable White Label handoff",()=>{
  it("retains planning and export while exposing server-backed save/load and source selection",()=>{
    vi.stubGlobal("localStorage",{getItem:()=>"scope"});
    const html=renderToStaticMarkup(<MemoryRouter><WhiteLabelRepackPage/></MemoryRouter>);
    expect(html).toContain("Save durable plan");
    expect(html).toContain("Durable lot");
    expect(html).toContain("Export Retail Ops Report");
    expect(html).toContain("Existing source inventory");
    expect(html).toContain("Step 3: Package Plan");
    vi.unstubAllGlobals();
  });
  it("carries saved identity, canonical run identity and expected allocations into execution",()=>{
    const plan={id:"plan-1",name:"Bulk A",status:"approved",production_order_id:"run-1",source:{lot_code:"LOT-A",quantity:100,unit:"g"},economics:{outputs:[{package_size_g:3.5,units:28,packaged_g:98}]}} as DurablePlan;
    const html=renderToStaticMarkup(<MemoryRouter><WhiteLabelExecutionHandoff plan={plan}/></MemoryRouter>);
    expect(html).toContain('/production/repack?plan=plan-1');
    expect(html).toContain('/production/runs/run-1');
    expect(html).toContain('/compliance/labels');
    expect(html).toContain('LOT-A');
    expect(html).toContain('<td>28</td>');
    expect(html).toContain('Inventory moves only through the existing execution confirmation');
  });
  it("preserves package rounding and planning economics",()=>{
    const result=calculate({...formDefaults(),bulk_weight_value:100,bulk_total_cost_usd:50},[planRow(true,3.5,100,0,20)]);
    expect(result.totalUnits).toBe(28);
    expect(result.totalRevenue).toBe(560);
    expect(result.leftovers[0].grams).toBe(2);
  });
});
