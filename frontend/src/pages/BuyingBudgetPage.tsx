import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { apiGet } from "../lib/api";

type Row = Record<string, unknown>;
type Budget = {
  summary: { recommended_budget:number; active_inventory_cost:number; target_inventory_cost:number; recommended_position:number; avg_daily_cogs:number; on_order_cost:number; sales_window_total:number };
  categories: Row[];
  scenarios: Row[];
};

const CATEGORY_COLUMNS = ["Category","Sales Window Retail Sales","Avg Daily Sales","Avg Daily COGS","Current Inventory at Cost","Target Inventory at Cost","Recommended Budget","Budget Status","Notes"];
const SCENARIO_COLUMNS = ["Scenario","Target Inventory","Current Active Inventory","On Order","Recommended Budget","Status"];

export function BuyingBudgetPage() {
  const proposedPoTotal = Number(sessionStorage.getItem("buyer-dash-proposed-po-total") ?? 0) || 0;
  const poWasOpened = sessionStorage.getItem("buyer-dash-po-items") !== null;
  const [days,setDays] = useState(30);
  const [target,setTarget] = useState(45);
  const [cogs,setCogs] = useState(50);
  const [safety,setSafety] = useState(10);
  const [growth,setGrowth] = useState(0);
  const [dead,setDead] = useState(false);
  const [quarantine,setQuarantine] = useState(false);
  const [accessories,setAccessories] = useState(false);
  const [onOrder,setOnOrder] = useState(proposedPoTotal);
  const params = useMemo(() => new URLSearchParams({selected_days:String(days),target_dos:String(target),cogs_pct:String(cogs),safety_stock_pct:String(safety),growth_adj_pct:String(growth),include_dead:String(dead),include_quarantine:String(quarantine),include_accessories:String(accessories),on_order_cost:String(onOrder)}), [days,target,cogs,safety,growth,dead,quarantine,accessories,onOrder]);
  const data = useQuery({queryKey:["buying-budget-parity",params.toString()],queryFn:({signal})=>apiGet<Budget>(`/api/v1/buying-budget-parity?${params}`,signal)});
  const remaining = data.data ? data.data.summary.recommended_position - proposedPoTotal : 0;

  return <div className="page exact-buying-budget">
    <h1>Purchasing Budget</h1>
    <section className="inventory-panel parity-controls buying-budget-controls">
      <label>Planning sales window<select value={days} onChange={event=>setDays(Number(event.target.value))}>{[14,30,60,90].map(value=><option value={value} key={value}>{value}</option>)}</select></label>
      <Num label="Target DOS" value={target} onChange={setTarget} min={1}/>
      <Num label="COGS % fallback" value={cogs} onChange={setCogs} min={0} max={100}/>
      <Num label="Safety stock %" value={safety} onChange={setSafety} min={0} max={200}/>
      <Num label="Growth adjustment %" value={growth} onChange={setGrowth} min={-100} max={300}/>
      <Toggle label="Include dead stock?" value={dead} onChange={setDead}/>
      <Toggle label="Include quarantine inventory?" value={quarantine} onChange={setQuarantine}/>
      <Toggle label="Include accessories?" value={accessories} onChange={setAccessories}/>
      <Num label="On-order inventory cost" value={onOrder} onChange={setOnOrder} min={0} step={1}/>
    </section>
    {data.isError?<div className="state error">{data.error.message}</div>:null}
    {data.isLoading?<div className="state">Calculating purchasing budget…</div>:null}
    {data.data?<>
      <section className="metrics three"><Metric label="Recommended Purchasing Budget" value={money(data.data.summary.recommended_budget)}/><Metric label="Current Active Inventory at Cost" value={money(data.data.summary.active_inventory_cost)}/><Metric label="Target Inventory at Cost" value={money(data.data.summary.target_inventory_cost)}/><Metric label="Over/Under Position" value={data.data.summary.recommended_position<0?`Overbought by ${money(Math.abs(data.data.summary.recommended_position))}`:`Available to Buy: ${money(data.data.summary.recommended_position)}`}/><Metric label="Avg Daily COGS" value={money(data.data.summary.avg_daily_cogs)}/><Metric label="On Order Cost" value={money(data.data.summary.on_order_cost)}/></section>
      {data.data.categories.length?<section className="inventory-panel"><h3>Category-Level Recommended Budget</h3><Table rows={data.data.categories} columns={CATEGORY_COLUMNS}/><BudgetChart rows={data.data.categories}/><ComparisonChart rows={data.data.categories}/></section>:null}
      <section className="inventory-panel"><h3>Budget Scenario Table</h3><Table rows={data.data.scenarios} columns={SCENARIO_COLUMNS}/></section>
      {poWasOpened?<><section className="metrics single"><Metric label="Remaining Budget After PO" value={money(remaining)}/></section>{remaining<0?<div className="warning-banner">This PO exceeds the recommended purchasing budget by {money(Math.abs(remaining))}.</div>:null}</>:null}
    </>:null}
  </div>;
}

function Num({label,value,onChange,min=0,max,step=1}:{label:string;value:number;onChange:(value:number)=>void;min?:number;max?:number;step?:number}){return <label>{label}<input type="number" min={min} max={max} step={step} value={value} onChange={event=>onChange(Number(event.target.value))}/></label>}
function Toggle({label,value,onChange}:{label:string;value:boolean;onChange:(value:boolean)=>void}){return <label className="toggle"><input type="checkbox" checked={value} onChange={event=>onChange(event.target.checked)}/>{label}</label>}
function Metric({label,value}:{label:string;value:string|number}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function money(value:number){return value.toLocaleString(undefined,{style:"currency",currency:"USD",minimumFractionDigits:2,maximumFractionDigits:2})}
function show(value:unknown){if(value==null||value==="")return "—";if(typeof value==="number")return money(value);return String(value)}
function Table({rows,columns}:{rows:Row[];columns:string[]}){return <div className="table-wrap"><table><thead><tr>{columns.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{columns.map(column=><td key={column}>{show(row[column])}</td>)}</tr>)}</tbody></table></div>}
function BudgetChart({rows}:{rows:Row[]}){const max=Math.max(...rows.map(row=>Math.abs(Number(row["Recommended Budget"]||0))),1);return <section className="budget-chart" aria-label="Recommended Budget by Category"><h4>Recommended Budget by Category</h4>{rows.map(row=>{const value=Number(row["Recommended Budget"]||0);return <div className="budget-chart-row" key={String(row.Category)}><span>{String(row.Category)}</span><div><i className={value<0?"negative":""} style={{width:`${Math.abs(value)/max*100}%`}}/></div><strong>{money(value)}</strong></div>})}</section>}
function ComparisonChart({rows}:{rows:Row[]}){const max=Math.max(...rows.flatMap(row=>[Number(row["Current Inventory at Cost"]||0),Number(row["Target Inventory at Cost"]||0)]),1);return <section className="budget-chart comparison-chart" aria-label="Current vs Target Inventory by Category"><h4>Current vs Target Inventory by Category</h4>{rows.map(row=>{const current=Number(row["Current Inventory at Cost"]||0);const target=Number(row["Target Inventory at Cost"]||0);return <div className="budget-comparison-row" key={String(row.Category)}><span>{String(row.Category)}</span><div><i className="current" style={{width:`${current/max*100}%`}}/><i className="target" style={{width:`${target/max*100}%`}}/></div><small>Current {money(current)} · Target {money(target)}</small></div>})}</section>}
