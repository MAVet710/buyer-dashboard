import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { apiGet } from "../lib/api";

type Row = Record<string, unknown>;
type Overview = {
  summary:{runs:number;finished_output_g:number;avg_yield_pct:number;qa_holds:number;total_revenue_usd:number;total_cogs_usd:number;toll_jobs:number};
  alerts:string[];
  runs:Row[];
};
type MethodSummary = { method:string; runs:number; input:number; output:number; loss:number; cogs:number; avgYield:number };

export function ExtractionAnalyticsWorkspace() {
  const overview=useQuery({queryKey:["extraction-parity-overview"],queryFn:({signal})=>apiGet<Overview>("/api/v1/extraction-parity/overview",signal)});
  const methods=useMemo<MethodSummary[]>(()=>{
    const groups=new Map<string,{runs:number;input:number;output:number;loss:number;cogs:number;yields:number[]}>();
    for(const row of overview.data?.runs??[]){
      const method=String(row.method??"Unknown");
      const group=groups.get(method)??{runs:0,input:0,output:0,loss:0,cogs:0,yields:[]};
      group.runs+=1;
      group.input+=Number(row.input_weight_g??0);
      group.output+=Number(row.final_output_g??row.finished_output_g??0);
      group.loss+=Number(row.residual_loss_g??0);
      group.cogs+=Number(row.cogs_usd??0);
      const yieldPct=Number(row.yield_pct??0);if(Number.isFinite(yieldPct)&&yieldPct>0)group.yields.push(yieldPct);
      groups.set(method,group);
    }
    return Array.from(groups.entries()).map(([method,row])=>({method,runs:row.runs,input:row.input,output:row.output,loss:row.loss,cogs:row.cogs,avgYield:row.yields.length?row.yields.reduce((sum,value)=>sum+value,0)/row.yields.length:0})).sort((a,b)=>b.runs-a.runs);
  },[overview.data?.runs]);

  if(overview.isLoading)return <div className="state">Loading extraction analytics…</div>;
  if(overview.isError)return <div className="state error">{overview.error.message}</div>;
  const summary=overview.data?.summary;
  return <div className="extraction-analytics-workspace">
    <section className="inventory-panel">
      <div className="section-heading"><div><div className="eyebrow">Extraction analytics</div><h2>Performance</h2><p>Operational results derived from the durable run record. Data entry stays on Today/Runs; this view is for comparing performance and spotting exceptions.</p></div></div>
      {summary?<div className="metrics"><Metric label="Runs" value={summary.runs}/><Metric label="Finished output" value={`${number(summary.finished_output_g)} g`}/><Metric label="Avg yield" value={`${number(summary.avg_yield_pct,1)}%`}/><Metric label="QA holds" value={summary.qa_holds}/><Metric label="Total COGS" value={money(summary.total_cogs_usd)}/><Metric label="Toll jobs" value={summary.toll_jobs}/></div>:null}
      {overview.data?.alerts.length?<div className="alert-stack">{overview.data.alerts.map(alert=><div className="warning-banner" key={alert}>{alert}</div>)}</div>:<div className="success-banner">No major automated extraction alerts.</div>}
    </section>
    <section className="inventory-panel">
      <div className="section-heading"><div><div className="eyebrow">Method comparison</div><h3>Yield, loss and cost by extraction method</h3></div></div>
      <div className="table-wrap"><table><thead><tr><th>Method</th><th>Runs</th><th>Input</th><th>Output</th><th>Avg yield</th><th>Recorded loss</th><th>COGS</th></tr></thead><tbody>{methods.map(row=><tr key={row.method}><td><strong>{row.method}</strong></td><td>{row.runs}</td><td>{number(row.input)} g</td><td>{number(row.output)} g</td><td>{number(row.avgYield,1)}%</td><td>{number(row.loss)} g</td><td>{money(row.cogs)}</td></tr>)}</tbody></table>{!methods.length?<div className="empty">No extraction run analytics yet.</div>:null}</div>
    </section>
  </div>;
}

function Metric({label,value}:{label:string;value:string|number}){return <div className="metric"><span>{label}</span><strong>{value}</strong></div>}
function number(value:number,digits=2){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:digits})}
function money(value:number){return Number(value||0).toLocaleString(undefined,{style:"currency",currency:"USD",maximumFractionDigits:0})}
