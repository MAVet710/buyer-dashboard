import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type Forecast = {
  as_of:string;
  horizon_end:string;
  forecast_days:number;
  metrics:{historical_harvest_samples:number;projected_dry_weight:number;projected_dry_unit:string;nursery_shortage_plants:number;rooms_at_pipeline_risk:number};
  yield_model:{sample_count:number;overall_dry_weight_per_plant:number|null;unit:string;strains:Record<string,{sample_count:number;dry_weight_per_plant:number}>;method:string};
  supply_forecast:Array<{week:string;strain:string;plants:number;estimated_dry_weight:number;plants_without_yield_baseline:number;confidence:string}>;
  nursery_forecast:Array<{turnover_date:string;week:string;room_code:string;room_name:string;strain:string;required_transplants:number;pipeline_available_at_turnover:number;allocated_from_pipeline:number;allocation:Record<string,number>;shortage_plants:number;status:string;days_away:number}>;
  exceptions:Array<{turnover_date:string;room_code:string;room_name:string;strain:string;required_transplants:number;shortage_plants:number;days_away:number}>;
  policy:{deterministic_only:boolean;provider_write:boolean;creates_purchase_orders:boolean;message:string};
};

export function CultivationIntelligencePanel() {
  const query=useQuery({
    queryKey:["cultivation-intelligence"],
    queryFn:({signal})=>apiGet<Forecast>("/api/v1/inventory/production/plants/intelligence",signal),
    staleTime:30_000,
  });
  if(query.isLoading)return <section className="inventory-panel"><div className="state">Building cultivation forecast…</div></section>;
  if(query.isError)return <section className="inventory-panel"><div className="state error">Cultivation intelligence could not load: {query.error.message}</div></section>;
  if(!query.data)return null;
  const data=query.data;
  return <section className="inventory-panel cultivation-intelligence-panel">
    <div className="section-heading"><div><div className="eyebrow">CULTIVATION INTELLIGENCE</div><h3>Supply & Nursery Forecast</h3><p className="source-caption">Deterministic 12-week outlook from plant dates, flowering-room turnover, nursery pipeline, and finished Harvest 360 actuals.</p></div><span className="read-only-chip">Decision support</span></div>
    <div className="metrics four"><Metric label="Yield samples" value={data.metrics.historical_harvest_samples}/><Metric label="Projected dry supply" value={`${number(data.metrics.projected_dry_weight)} g`}/><Metric label="Nursery shortage" value={data.metrics.nursery_shortage_plants}/><Metric label="Rooms at risk" value={data.metrics.rooms_at_pipeline_risk}/></div>
    <div className="info-banner"><strong>Forecast boundary:</strong> {data.policy.message}</div>
    {data.exceptions.length?<div className="warning-banner"><strong>Pipeline shortfalls need planning</strong><div className="table-wrap"><table><thead><tr><th>Turnover</th><th>Room</th><th>Strain</th><th>Needed</th><th>Short</th></tr></thead><tbody>{data.exceptions.slice(0,12).map(row=><tr key={`${row.room_code}-${row.turnover_date}`}><td>{row.turnover_date}<br/><small>{row.days_away} days</small></td><td><strong>{row.room_name}</strong></td><td>{row.strain}</td><td>{row.required_transplants}</td><td><strong className="warning-text">{row.shortage_plants}</strong></td></tr>)}</tbody></table></div></div>:<div className="success-banner"><strong>No modeled nursery shortages in the next {data.forecast_days} days.</strong><br/><span>Configured flowering-room turns are covered by the current clone, seedling, and vegetative pipeline.</span></div>}
    <div className="two-col">
      <section><div className="section-heading"><div><h4>Projected dry supply</h4><p className="source-caption">Uses strain-specific Harvest 360 actuals when available, then facility-wide yield per plant as fallback.</p></div></div>{data.supply_forecast.length?<div className="table-wrap"><table><thead><tr><th>Week</th><th>Strain</th><th>Plants</th><th>Dry forecast</th><th>Confidence</th></tr></thead><tbody>{data.supply_forecast.map(row=><tr key={`${row.week}-${row.strain}`}><td>{row.week}</td><td><strong>{row.strain}</strong></td><td>{row.plants}</td><td>{number(row.estimated_dry_weight)} g</td><td>{title(row.confidence)}{row.plants_without_yield_baseline?<><br/><small>{row.plants_without_yield_baseline} without baseline</small></>:null}</td></tr>)}</tbody></table></div>:<div className="empty">Add flowering harvest dates and completed Harvest 360 actuals to produce a dry-supply forecast.</div>}</section>
      <section><div className="section-heading"><div><h4>Room turnover coverage</h4><p className="source-caption">Each clone/seedling/veg plant is allocated at most once across future turns, preventing false coverage.</p></div></div>{data.nursery_forecast.length?<div className="table-wrap"><table><thead><tr><th>Turnover</th><th>Room</th><th>Need</th><th>Allocated</th><th>Status</th></tr></thead><tbody>{data.nursery_forecast.slice(0,18).map(row=><tr key={`${row.room_code}-${row.turnover_date}`}><td>{row.turnover_date}</td><td><strong>{row.room_name}</strong><br/><small>{row.strain}</small></td><td>{row.required_transplants}</td><td>{row.allocated_from_pipeline}<br/><small>{allocation(row.allocation)}</small></td><td className={row.shortage_plants?"warning-text":""}>{row.shortage_plants?`Short ${row.shortage_plants}`:"Covered"}</td></tr>)}</tbody></table></div>:<div className="empty">Configure flowering rooms with capacity and cycle days to model nursery coverage.</div>}</section>
    </div>
    <p className="source-caption">Yield baseline: {data.yield_model.overall_dry_weight_per_plant==null?"not established yet":`${number(data.yield_model.overall_dry_weight_per_plant)} g dry per plant`} · As of {data.as_of} · Horizon through {data.horizon_end}</p>
  </section>;
}

function Metric({label,value}:{label:string;value:string|number}){return <article className="metric"><span>{label}</span><strong>{typeof value==="number"?value.toLocaleString():value}</strong></article>}
function number(value:number){return new Intl.NumberFormat("en-US",{maximumFractionDigits:2}).format(value||0)}
function title(value:string){return (value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function allocation(value:Record<string,number>){const rows=Object.entries(value).filter(([,count])=>count>0).map(([phase,count])=>`${count} ${phase}`);return rows.length?rows.join(" · "):"No pipeline allocation"}
