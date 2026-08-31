import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type GraphNode = {
  key:string;
  type:string;
  id:string;
  lot_code?:string;
  package_id?:string;
  product_name?:string;
  status?:string;
  balance?:number;
  unit?:string;
  transformation_type?:string;
  source_entity_type?:string;
  source_entity_id?:string;
  harvest_code?:string;
  strain?:string;
  plant_tag?:string;
  strain_name?:string;
  mother_plant_tag?:string;
  order_number?:string;
};
type GraphEdge = { from:string;to:string;relationship:string;quantity?:number;unit?:string;purpose?:string };
type Graph = { root_lot_id:string;nodes:GraphNode[];edges:GraphEdge[];node_count:number;edge_count:number;max_depth:number };

export function MaterialLineageGraph({lotId}:{lotId:string}) {
  const graph=useQuery({queryKey:["material-lineage",lotId],enabled:Boolean(lotId),queryFn:({signal})=>apiGet<Graph>(`/api/v1/material-lineage/lots/${lotId}`,signal)});
  const labels=useMemo(()=>new Map((graph.data?.nodes??[]).map(node=>[node.key,nodeLabel(node)])),[graph.data?.nodes]);
  const nodes=graph.data?.nodes??[];
  const sourcePlants=nodes.filter(node=>node.type==="plant");
  const harvests=nodes.filter(node=>node.type==="harvest");
  const transformations=nodes.filter(node=>node.type==="transformation"||node.type==="production_order");
  const lots=nodes.filter(node=>node.type==="lot");

  return <section className="inventory-panel">
    <div className="eyebrow">SEED-TO-SALE GENEALOGY</div><h3>Recursive material source trail</h3><p className="source-caption">This graph follows durable material relationships across cultivation harvests, Production Run 360 and Package Studio. It is facility scoped and does not infer ancestry from free-text notes.</p>
    {graph.isLoading?<div className="state">Tracing upstream and downstream material…</div>:null}
    {graph.isError?<div className="warning-banner">{graph.error.message}</div>:null}
    {graph.data?<>
      <div className="metrics four"><Metric label="Source plants" value={sourcePlants.length}/><Metric label="Harvests" value={harvests.length}/><Metric label="Processes" value={transformations.length}/><Metric label="Related lots" value={lots.length}/></div>
      {sourcePlants.length?<div className="info-banner"><strong>Plant source:</strong> {sourcePlants.slice(0,12).map(node=>node.plant_tag).join(", ")}{sourcePlants.length>12?` + ${sourcePlants.length-12} more`:""}</div>:null}
      {harvests.length?<div className="info-banner"><strong>Harvest source:</strong> {harvests.map(node=>`${node.harvest_code}${node.strain?` · ${node.strain}`:""}`).join("; ")}</div>:null}
      {graph.data.edges.length?<div className="table-wrap"><table><thead><tr><th>From</th><th>Relationship</th><th>To</th><th>Quantity / purpose</th></tr></thead><tbody>{graph.data.edges.map((edge,index)=><tr key={`${edge.from}-${edge.to}-${edge.relationship}-${index}`}><td><strong>{labels.get(edge.from)??edge.from}</strong></td><td>{title(edge.relationship)}</td><td><strong>{labels.get(edge.to)??edge.to}</strong></td><td>{edge.quantity==null?"—":`${number(edge.quantity)} ${edge.unit||""}`}{edge.purpose?` · ${title(edge.purpose)}`:""}</td></tr>)}</tbody></table></div>:<div className="info-banner">This lot has no durable parent/child material edges yet.</div>}
    </>:null}
  </section>;
}

function nodeLabel(node:GraphNode){
  if(node.type==="lot")return `${node.product_name||"Lot"} · ${node.package_id||node.lot_code||node.id}`;
  if(node.type==="plant")return `Plant ${node.plant_tag||node.id}`;
  if(node.type==="harvest")return `Harvest ${node.harvest_code||node.id}`;
  if(node.type==="production_order")return `Production ${node.order_number||node.id}`;
  if(node.type==="transformation")return title(node.transformation_type||"Transformation");
  return `${title(node.type)} ${node.id}`;
}
function Metric({label,value}:{label:string;value:string|number}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function number(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:4})}
