import { useMemo, useState } from "react";

type Step = 0 | 1 | 2 | 3 | 4;
type Form = {
  strain_name: string; strain_type: string; cultivator_name: string; vendor_name: string;
  bulk_weight_value: number; bulk_weight_unit: "g" | "oz" | "lb"; bulk_total_cost_usd: number;
  coa_link: string; thca_pct: number; terpene_pct: number; cultivator_license_number: string;
  source_metrc_package_id: string; batch_or_lot_number: string; harvest_date: string; testing_date: string; received_date: string;
  total_thc_pct: number; moisture_pct: number; testing_notes: string; buyer_notes: string; compliance_notes: string;
  discount_pct: number; shrink_loss_pct: number; labor_cost_total_usd: number; other_costs_usd: number;
  freight_or_delivery_cost_usd: number; sample_or_testing_cost_usd: number; compliance_admin_cost_usd: number;
  qa_hold_loss_pct: number; trim_loss_pct: number; moisture_loss_pct: number;
  coa_status: "Needs Review" | "Passed"; label_review_status: "Needs Review" | "Ready";
};
type PackagePlan = {
  enabled: boolean; package_size_g: number; allocation_pct: number; bag_or_container_cost_per_unit: number;
  label_cost_per_unit: number; tamper_seal_cost_per_unit: number; humidity_pack_cost_per_unit: number;
  compliance_sticker_cost_per_unit: number; other_packaging_cost_per_unit: number; target_retail_price_per_unit: number;
};
type Scenario = { form: Form; plan: PackagePlan[]; simpleMode: boolean };
type Result = {
  productName: string; packageSize: string; allocationPct: number; gramsAllocated: number; unitsProduced: number;
  retailPrice: number | null; totalPackagingPerUnit: number; totalPackagingCost: number; allInCostPerUnit: number | null;
  breakEvenPrice: number | null; revenue: number | null; grossProfit: number | null; grossMarginPct: number | null;
  status: "Complete" | "Incomplete"; missingInputs: string;
};

const today = () => new Date().toISOString().slice(0, 10);
const defaultForm = (): Form => ({
  strain_name: "", strain_type: "Indica", cultivator_name: "", vendor_name: "", bulk_weight_value: 0, bulk_weight_unit: "g", bulk_total_cost_usd: 0,
  coa_link: "", thca_pct: 0, terpene_pct: 0, cultivator_license_number: "", source_metrc_package_id: "", batch_or_lot_number: "",
  harvest_date: today(), testing_date: today(), received_date: today(), total_thc_pct: 0, moisture_pct: 0, testing_notes: "", buyer_notes: "", compliance_notes: "",
  discount_pct: 0, shrink_loss_pct: 0, labor_cost_total_usd: 0, other_costs_usd: 0, freight_or_delivery_cost_usd: 0, sample_or_testing_cost_usd: 0,
  compliance_admin_cost_usd: 0, qa_hold_loss_pct: 0, trim_loss_pct: 0, moisture_loss_pct: 0, coa_status: "Needs Review", label_review_status: "Needs Review",
});
const defaultPlan = (): PackagePlan[] => [
  row(false, 1, 0, .12, 10), row(true, 3.5, 50, .18, 25), row(true, 7, 25, .24, 45), row(true, 14, 15, .32, 80), row(true, 28, 10, .45, 140), row(false, 0, 0, .20, 0),
];
function row(enabled:boolean,size:number,allocation:number,bag:number,price:number):PackagePlan{return{enabled,package_size_g:size,allocation_pct:allocation,bag_or_container_cost_per_unit:bag,label_cost_per_unit:.05,tamper_seal_cost_per_unit:0,humidity_pack_cost_per_unit:0,compliance_sticker_cost_per_unit:0,other_packaging_cost_per_unit:0,target_retail_price_per_unit:price}}

export function WhiteLabelRepackPage() {
  const [step, setStep] = useState<Step>(0);
  const [scenarioName, setScenarioName] = useState("Current Session");
  const [loadName, setLoadName] = useState("Current Session");
  const [form, setForm] = useState<Form>(defaultForm);
  const [plan, setPlan] = useState<PackagePlan[]>(defaultPlan);
  const [simpleMode, setSimpleMode] = useState(true);
  const [notice, setNotice] = useState("");
  const [saved, setSaved] = useState<Record<string,Scenario>>(() => {
    try { return JSON.parse(sessionStorage.getItem("white-label-scenarios") || "{}"); } catch { return {}; }
  });
  const update = <K extends keyof Form>(key: K, value: Form[K]) => setForm(current => ({ ...current, [key]: value }));
  const updatePlan = (index: number, key: keyof PackagePlan, value: number | boolean) => setPlan(current => current.map((item,i) => i === index ? { ...item, [key]: value } : item));
  const calculations = useMemo(() => calculate(form, plan), [form, plan]);
  const scenarioNames = ["Current Session", ...Object.keys(saved).sort()];

  const persist = (next: Record<string,Scenario>) => { setSaved(next); sessionStorage.setItem("white-label-scenarios", JSON.stringify(next)); };
  const saveScenario = () => { const name = scenarioName.trim() || "Current Session"; persist({ ...saved, [name]: { form, plan, simpleMode } }); setScenarioName(name); setNotice(`Saved scenario: ${name}`); };
  const duplicate = () => { const source = saved[loadName]; if (!source) return; const name = `${loadName} Copy`; persist({ ...saved, [name]: structuredClone(source) }); setNotice(`Duplicated as ${name}`); };
  const clear = () => { setForm(defaultForm()); setPlan(defaultPlan()); setSimpleMode(true); setScenarioName("Current Session"); setLoadName("Current Session"); setNotice("Cleared scenario values for current session."); };
  const apply = () => { const source = saved[loadName]; if (!source) return; setForm(structuredClone(source.form)); setPlan(structuredClone(source.plan)); setSimpleMode(source.simpleMode); setScenarioName(loadName); setNotice(`Loaded ${loadName}`); };

  return <div className="page">
    <div className="page-heading"><div><div className="eyebrow">White Label / Repack</div><h1>White Label / Repack</h1><p>Plan a private-label flower lot from bulk intake through package margin and release readiness.</p></div></div>

    <section className="inventory-panel scenario-controls">
      <Field label="Scenario Name"><input value={scenarioName} onChange={event => setScenarioName(event.target.value)}/></Field>
      <button className="secondary" type="button" onClick={saveScenario}>Save Scenario</button>
      <Field label="Load Scenario"><select value={loadName} onChange={event => setLoadName(event.target.value)}>{scenarioNames.map(name => <option key={name}>{name}</option>)}</select></Field>
      <button className="secondary" type="button" onClick={duplicate} disabled={loadName === "Current Session"}>Duplicate Scenario</button>
      <button className="secondary" type="button" onClick={clear}>Clear Scenario</button>
      {loadName !== "Current Session" ? <button className="primary" type="button" onClick={apply}>Apply Loaded Scenario</button> : null}
    </section>
    {notice ? <div className="success-banner">{notice}</div> : null}

    <div className="view-tabs white-label-tabs">
      {["Step 1: Bulk Lot","Step 2: Costs","Step 3: Package Plan","Step 4: Results","Step 5: Compliance"].map((label,index) => <button className={step === index ? "active" : ""} key={label} onClick={() => setStep(index as Step)}>{label}</button>)}
    </div>

    {step === 0 ? <BulkLot form={form} update={update}/> : null}
    {step === 1 ? <Costs form={form} update={update}/> : null}
    {step === 2 ? <PackagePlanStep plan={plan} updatePlan={updatePlan} simpleMode={simpleMode} setSimpleMode={setSimpleMode} allocationTotal={calculations.allocationTotal}/> : null}
    {step === 3 ? <Results calculations={calculations}/> : null}
    {step === 4 ? <Compliance form={form} update={update}/> : null}
  </div>;
}

function BulkLot({ form, update }: { form: Form; update: <K extends keyof Form>(key: K, value: Form[K]) => void }) {
  return <section className="inventory-panel white-label-step"><div className="info-banner">Start with the bulk flower lot you are considering buying or repacking.</div>
    <Field label="Strain Name *"><input value={form.strain_name} onChange={event => update("strain_name", event.target.value)}/></Field>
    <Field label="Strain Type *"><select value={form.strain_type} onChange={event => update("strain_type", event.target.value)}>{["Indica","Sativa","Hybrid","CBD","Mixed","Unknown"].map(value => <option key={value}>{value}</option>)}</select></Field>
    <Field label="Cultivator Name *"><input value={form.cultivator_name} onChange={event => update("cultivator_name", event.target.value)}/></Field>
    <Field label="Vendor Name *"><input value={form.vendor_name} onChange={event => update("vendor_name", event.target.value)}/></Field>
    <div className="two-col"><NumberField label="Bulk Weight *" value={form.bulk_weight_value} min={0} onChange={value => update("bulk_weight_value", value)}/><Field label="Weight Unit *"><select value={form.bulk_weight_unit} onChange={event => update("bulk_weight_unit", event.target.value as Form["bulk_weight_unit"])}>{["g","oz","lb"].map(value => <option key={value}>{value}</option>)}</select></Field></div>
    <NumberField label="Total Bulk Cost ($) *" value={form.bulk_total_cost_usd} min={0} onChange={value => update("bulk_total_cost_usd", value)}/>
    <Field label="Certificate of Analysis (COA) Link *"><input value={form.coa_link} onChange={event => update("coa_link", event.target.value)}/></Field>
    <NumberField label="THCA (%) *" value={form.thca_pct} min={0} max={100} onChange={value => update("thca_pct", value)}/>
    <NumberField label="Terpenes (%) *" value={form.terpene_pct} min={0} max={100} onChange={value => update("terpene_pct", value)}/>
    <details className="streamlit-expander"><summary>Advanced Lot Details</summary><div className="streamlit-expander-body form-grid">
      <Field label="Cultivator License Number"><input value={form.cultivator_license_number} onChange={event => update("cultivator_license_number", event.target.value)}/></Field>
      <Field label="Source METRC Package ID"><input value={form.source_metrc_package_id} onChange={event => update("source_metrc_package_id", event.target.value)}/></Field>
      <Field label="Batch or Lot Number"><input value={form.batch_or_lot_number} onChange={event => update("batch_or_lot_number", event.target.value)}/></Field>
      <DateField label="Harvest Date" value={form.harvest_date} onChange={value => update("harvest_date", value)}/><DateField label="Testing Date" value={form.testing_date} onChange={value => update("testing_date", value)}/><DateField label="Received Date" value={form.received_date} onChange={value => update("received_date", value)}/>
      <NumberField label="Total THC (%)" value={form.total_thc_pct} min={0} max={100} onChange={value => update("total_thc_pct", value)}/><NumberField label="Moisture (%)" value={form.moisture_pct} min={0} max={100} onChange={value => update("moisture_pct", value)}/>
      <Field label="Testing Notes"><textarea value={form.testing_notes} onChange={event => update("testing_notes", event.target.value)}/></Field><Field label="Buyer Notes"><textarea value={form.buyer_notes} onChange={event => update("buyer_notes", event.target.value)}/></Field><Field label="Compliance Notes"><textarea value={form.compliance_notes} onChange={event => update("compliance_notes", event.target.value)}/></Field>
    </div></details>
  </section>;
}

function Costs({ form, update }: { form: Form; update: <K extends keyof Form>(key: K, value: Form[K]) => void }) {
  return <section className="inventory-panel white-label-step"><div className="info-banner">Add the costs that change the true landed cost of the flower.</div>
    <NumberField label="Purchase Discount (%)" value={form.discount_pct} min={0} max={100} onChange={value => update("discount_pct", value)}/><NumberField label="Expected Shrink Loss (%)" value={form.shrink_loss_pct} min={0} max={100} onChange={value => update("shrink_loss_pct", value)}/><NumberField label="Total Labor Cost ($)" value={form.labor_cost_total_usd} min={0} onChange={value => update("labor_cost_total_usd", value)}/><NumberField label="Other Costs ($)" value={form.other_costs_usd} min={0} onChange={value => update("other_costs_usd", value)}/>
    <details className="streamlit-expander"><summary>Advanced Costs</summary><div className="streamlit-expander-body form-grid"><NumberField label="Freight or Delivery Cost ($)" value={form.freight_or_delivery_cost_usd} min={0} onChange={value => update("freight_or_delivery_cost_usd", value)}/><NumberField label="Sampling or Testing Cost ($)" value={form.sample_or_testing_cost_usd} min={0} onChange={value => update("sample_or_testing_cost_usd", value)}/><NumberField label="Compliance Administration Cost ($)" value={form.compliance_admin_cost_usd} min={0} onChange={value => update("compliance_admin_cost_usd", value)}/><NumberField label="QA Hold Loss (%)" value={form.qa_hold_loss_pct} min={0} max={100} onChange={value => update("qa_hold_loss_pct", value)}/><NumberField label="Trim Loss (%)" value={form.trim_loss_pct} min={0} max={100} onChange={value => update("trim_loss_pct", value)}/><NumberField label="Moisture Loss (%)" value={form.moisture_loss_pct} min={0} max={100} onChange={value => update("moisture_loss_pct", value)}/></div></details>
  </section>;
}

function PackagePlanStep({ plan, updatePlan, simpleMode, setSimpleMode, allocationTotal }: { plan: PackagePlan[]; updatePlan: (index:number,key:keyof PackagePlan,value:number|boolean)=>void; simpleMode:boolean; setSimpleMode:(value:boolean)=>void; allocationTotal:number }) {
  const baseColumns: (keyof PackagePlan)[] = ["enabled","package_size_g","allocation_pct","target_retail_price_per_unit"];
  const detailColumns: (keyof PackagePlan)[] = ["bag_or_container_cost_per_unit","label_cost_per_unit","tamper_seal_cost_per_unit","humidity_pack_cost_per_unit","compliance_sticker_cost_per_unit","other_packaging_cost_per_unit"];
  return <section className="inventory-panel white-label-step"><div className="info-banner">Choose how much of the lot goes into each package size. Packaging costs can vary by size.</div>
    <label className="toggle"><input type="checkbox" checked={simpleMode} onChange={event => setSimpleMode(event.target.checked)}/> Simple Mode</label>
    <PackageEditor rows={plan} columns={baseColumns} update={updatePlan} showPackagingTotal/>
    {!simpleMode ? <details className="streamlit-expander"><summary>Packaging Cost Details</summary><div className="streamlit-expander-body"><PackageEditor rows={plan} columns={["enabled","package_size_g",...detailColumns]} update={updatePlan}/></div></details> : null}
    {allocationTotal > 100 ? <div className="warning-banner">Your package allocation is over 100%.</div> : allocationTotal < 100 ? <div className="warning-banner">You still have {(100-allocationTotal).toFixed(1)}% unallocated.</div> : null}
  </section>;
}

function Results({ calculations }: { calculations: ReturnType<typeof calculate> }) {
  return <section className="inventory-panel white-label-step"><div className="info-banner">Review estimated units, revenue, profit, and margin.</div>
    {calculations.packageLeftovers.length ? <div className="info-banner">Package-size rounding leaves partial grams in: {calculations.packageLeftovers.map(row => `${row.size} (${row.grams.toFixed(2)} g)`).join(", ")}.</div> : null}
    <div className="metrics five"><Metric label="Usable Weight" value={`${calculations.usableWeight.toLocaleString(undefined,{maximumFractionDigits:1})} g`}/><Metric label="Total Units" value={calculations.totalUnits.toLocaleString()}/><Metric label="Total Revenue" value={money0(calculations.totalRevenue)}/><Metric label="Gross Profit" value={money0(calculations.grossProfit)}/><Metric label="Gross Margin %" value={`${calculations.grossMargin.toFixed(1)}%`}/></div>
    <div className="metrics"><Metric label="Leftover Grams" value={`${calculations.leftoverTotal.toFixed(1)} g`}/><Metric label="Best Package Size by Margin" value={calculations.bestPackageSize || "—"}/></div>
    {calculations.results.length ? <><h4>Margin Readiness</h4><pre className="readiness-json">{JSON.stringify(calculations.readiness,null,2)}</pre>{calculations.readiness.incomplete_rows > 0 ? <div className="warning-banner">Some margins are incomplete because required inputs are missing.</div> : null}</> : null}
    <ResultsTable rows={calculations.results}/>
    {calculations.results.length ? <><SimpleBars title="Revenue" rows={calculations.results.map(row => ({label:row.packageSize,value:row.revenue ?? 0}))}/><SimpleBars title="Gross Profit" rows={calculations.results.map(row => ({label:row.packageSize,value:row.grossProfit ?? 0}))}/><SimpleBars title="Gross Margin %" rows={calculations.results.map(row => ({label:row.packageSize,value:row.grossMarginPct ?? 0}))}/></> : null}
  </section>;
}

function Compliance({ form, update }: { form: Form; update: <K extends keyof Form>(key: K, value: Form[K]) => void }) {
  const checklist = [
    ["COA Link Present", form.coa_link ? "Ready" : "Missing"],
    ["COA Status Passed", form.coa_status === "Passed" ? "Ready" : "Needs Review"],
    ["THCA / Cannabinoid Data Present", form.thca_pct > 0 || form.total_thc_pct > 0 ? "Ready" : "Missing"],
    ["Terpene Data Present", form.terpene_pct > 0 ? "Ready" : "Needs Review"],
    ["Cultivator Name Present", form.cultivator_name ? "Ready" : "Missing"],
    ["Cultivator License Present", form.cultivator_license_number ? "Ready" : "Missing"],
    ["Source METRC Package ID Present", form.source_metrc_package_id ? "Ready" : "Missing"],
    ["Batch/Lot Number Present", form.batch_or_lot_number ? "Ready" : "Missing"],
    ["Harvest Date Present", form.harvest_date ? "Ready" : "Missing"],
    ["Testing Date Present", form.testing_date ? "Ready" : "Missing"],
    ["Label Review Completed", form.label_review_status === "Ready" ? "Ready" : "Needs Review"],
  ];
  return <section className="inventory-panel white-label-step"><div className="info-banner">Check whether the lot has the documentation needed before launch.</div>
    <div className="two-col"><Field label="COA Status"><select value={form.coa_status} onChange={event => update("coa_status", event.target.value as Form["coa_status"])}><option>Needs Review</option><option>Passed</option></select></Field><Field label="Label Review"><select value={form.label_review_status} onChange={event => update("label_review_status", event.target.value as Form["label_review_status"])}><option>Needs Review</option><option>Ready</option></select></Field></div>
    <div className="table-wrap"><table><thead><tr><th>Requirement</th><th>Status</th></tr></thead><tbody>{checklist.map(([requirement,status]) => <tr key={requirement}><td>{requirement}</td><td><span className={`status-pill ${status === "Ready" ? "healthy" : status === "Missing" ? "critical" : "warning"}`}>{status}</span></td></tr>)}</tbody></table></div>
  </section>;
}

function calculate(form: Form, plan: PackagePlan[]) {
  const totalGrams = form.bulk_weight_unit === "lb" ? form.bulk_weight_value * 453.59237 : form.bulk_weight_unit === "oz" ? form.bulk_weight_value * 28.349523125 : form.bulk_weight_value;
  const landedCost = Math.max(0, form.bulk_total_cost_usd * (1-form.discount_pct/100) + form.freight_or_delivery_cost_usd + form.sample_or_testing_cost_usd);
  const totalLossPct = Math.min(100, form.shrink_loss_pct + form.trim_loss_pct + form.qa_hold_loss_pct + form.moisture_loss_pct);
  const usableWeight = Math.max(0,totalGrams*(1-totalLossPct/100));
  const effectiveCostPerGram = usableWeight > 0 ? landedCost/usableWeight : 0;
  const enabled = plan.filter(row => row.enabled);
  const packageLeftovers:{size:string;grams:number}[]=[];
  const results:Result[]=[];
  for(const item of enabled){
    const missing:string[]=[];
    if(item.target_retail_price_per_unit<=0)missing.push("Retail price missing");
    if(item.bag_or_container_cost_per_unit<0||item.label_cost_per_unit<0||item.tamper_seal_cost_per_unit<0||item.humidity_pack_cost_per_unit<0||item.compliance_sticker_cost_per_unit<0||item.other_packaging_cost_per_unit<0)missing.push("Packaging cost missing");
    if(item.allocation_pct<=0)missing.push("Allocation missing");
    if(landedCost<=0)missing.push("Bulk cost missing");
    if(item.package_size_g<=0){missing.push("Package size missing");continue;}
    const allocated=usableWeight*(item.allocation_pct/100); const units=Math.floor(allocated/item.package_size_g); const leftover=Math.max(0,allocated-units*item.package_size_g); if(leftover>0)packageLeftovers.push({size:`${item.package_size_g:g}g`.replace(":g",""),grams:leftover});
    const packUnit=Math.max(0,item.bag_or_container_cost_per_unit+item.label_cost_per_unit+item.tamper_seal_cost_per_unit+item.humidity_pack_cost_per_unit+item.compliance_sticker_cost_per_unit+item.other_packaging_cost_per_unit); const packTotal=units*packUnit; const revenue=missing.length?null:units*item.target_retail_price_per_unit; const bulkCost=units*item.package_size_g*effectiveCostPerGram; const unitOther=(form.labor_cost_total_usd+form.other_costs_usd+form.compliance_admin_cost_usd)/Math.max(1,enabled.length); const allIn=bulkCost+packTotal+unitOther; const profit=revenue==null?null:revenue-allIn; const margin=profit!=null&&revenue&&revenue>0?profit/revenue*100:null; const breakEven=units>0&&!missing.length?allIn/units:null; const strain=form.strain_name.trim()||"Repack Product";
    results.push({productName:`${strain} Flower ${formatSize(item.package_size_g)}g`,packageSize:`${formatSize(item.package_size_g)}g`,allocationPct:item.allocation_pct,gramsAllocated:allocated,unitsProduced:units,retailPrice:item.target_retail_price_per_unit>0?item.target_retail_price_per_unit:null,totalPackagingPerUnit:packUnit,totalPackagingCost:packTotal,allInCostPerUnit:units>0?allIn/units:null,breakEvenPrice:breakEven,revenue,grossProfit:profit,grossMarginPct:margin,status:missing.length?"Incomplete":"Complete",missingInputs:missing.join(", ")});
  }
  const totalUnits=results.reduce((sum,row)=>sum+row.unitsProduced,0); const totalRevenue=results.reduce((sum,row)=>sum+(row.revenue??0),0); const totalAllIn=results.reduce((sum,row)=>sum+(row.allInCostPerUnit??0)*row.unitsProduced,0); const grossProfit=totalRevenue-totalAllIn; const grossMargin=totalRevenue>0?grossProfit/totalRevenue*100:0; const allocated=results.reduce((sum,row)=>sum+row.gramsAllocated,0); const leftoverTotal=Math.max(0,usableWeight-allocated); const allocationTotal=plan.filter(row=>row.enabled).reduce((sum,row)=>sum+row.allocation_pct,0); const ranked=[...results].filter(row=>row.grossMarginPct!=null).sort((a,b)=>(b.grossMarginPct??-Infinity)-(a.grossMarginPct??-Infinity)); const bestPackageSize=ranked[0]?.packageSize??"";
  const readiness={complete_rows:results.filter(row=>row.status==="Complete").length,incomplete_rows:results.filter(row=>row.status==="Incomplete").length,missing_retail_price_count:results.filter(row=>row.missingInputs.includes("Retail price missing")).length,missing_packaging_cost_count:results.filter(row=>row.missingInputs.includes("Packaging cost missing")).length,total_allocation_pct:results.reduce((sum,row)=>sum+row.allocationPct,0),unallocated_grams:leftoverTotal};
  return {totalGrams,landedCost,totalLossPct,usableWeight,effectiveCostPerGram,packageLeftovers,results,totalUnits,totalRevenue,grossProfit,grossMargin,leftoverTotal,allocationTotal,bestPackageSize,readiness};
}

function PackageEditor({ rows, columns, update, showPackagingTotal=false }: { rows:PackagePlan[]; columns:(keyof PackagePlan)[]; update:(index:number,key:keyof PackagePlan,value:number|boolean)=>void; showPackagingTotal?:boolean }) { const all=[...columns,...(showPackagingTotal?["total_packaging_cost_per_unit" as const]:[])]; return <div className="table-wrap"><table><thead><tr>{all.map(column=><th key={column}>{header(column)}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{all.map(column=><td key={column}>{column==="total_packaging_cost_per_unit"?money2(packagingUnit(row)):column==="enabled"?<input type="checkbox" checked={row.enabled} onChange={event=>update(index,"enabled",event.target.checked)}/>:<input className="table-input" type="number" min={0} step="any" value={Number(row[column])} onChange={event=>update(index,column,Number(event.target.value))}/>}</td>)}</tr>)}</tbody></table></div> }
function ResultsTable({rows}:{rows:Result[]}){if(!rows.length)return <div className="empty">No enabled package rows have calculable output yet.</div>;return <div className="table-wrap"><table><thead><tr>{["Product Name","Package Size","Allocation %","Grams Allocated","Units Produced","Retail Price","Total Packaging / Unit","Total Packaging Cost","All-In Cost / Unit","Break-even Price","Revenue","Gross Profit","Gross Margin %","Status","Missing Inputs"].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.productName}><td>{row.productName}</td><td>{row.packageSize}</td><td>{row.allocationPct.toFixed(1)}</td><td>{row.gramsAllocated.toFixed(2)}</td><td>{row.unitsProduced}</td><td>{nullableMoney(row.retailPrice)}</td><td>{money2(row.totalPackagingPerUnit)}</td><td>{money2(row.totalPackagingCost)}</td><td>{nullableMoney(row.allInCostPerUnit)}</td><td>{nullableMoney(row.breakEvenPrice)}</td><td>{nullableMoney(row.revenue)}</td><td>{nullableMoney(row.grossProfit)}</td><td>{row.grossMarginPct==null?"N/A":`${row.grossMarginPct.toFixed(1)}%`}</td><td>{row.status}</td><td>{row.missingInputs||""}</td></tr>)}</tbody></table></div>}
function SimpleBars({title,rows}:{title:string;rows:{label:string;value:number}[]}){const max=Math.max(...rows.map(row=>Math.max(0,row.value)),1);return <div className="chart-card"><h4>{title}</h4><div className="simple-bars">{rows.map(row=><div className="simple-bar-row" key={row.label}><span>{row.label}</span><div><i style={{width:`${Math.max(0,row.value)/max*100}%`}}/></div><strong>{row.value.toLocaleString(undefined,{maximumFractionDigits:1})}</strong></div>)}</div></div>}
function Field({label,children}:{label:string;children:React.ReactNode}){return <label className="compact-field"><span>{label}</span>{children}</label>}
function NumberField({label,value,min,max,onChange}:{label:string;value:number;min?:number;max?:number;onChange:(value:number)=>void}){return <Field label={label}><input type="number" value={value} min={min} max={max} step="any" onChange={event=>onChange(Number(event.target.value))}/></Field>}
function DateField({label,value,onChange}:{label:string;value:string;onChange:(value:string)=>void}){return <Field label={label}><input type="date" value={value} onChange={event=>onChange(event.target.value)}/></Field>}
function Metric({label,value}:{label:string;value:string}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function packagingUnit(row:PackagePlan){return row.bag_or_container_cost_per_unit+row.label_cost_per_unit+row.tamper_seal_cost_per_unit+row.humidity_pack_cost_per_unit+row.compliance_sticker_cost_per_unit+row.other_packaging_cost_per_unit}
function header(value:string){return value.replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function formatSize(value:number){return Number.isInteger(value)?String(value):String(value)}
function money0(value:number){return value.toLocaleString(undefined,{style:"currency",currency:"USD",maximumFractionDigits:0})}
function money2(value:number){return value.toLocaleString(undefined,{style:"currency",currency:"USD",minimumFractionDigits:2,maximumFractionDigits:2})}
function nullableMoney(value:number|null){return value==null?"N/A":money2(value)}
