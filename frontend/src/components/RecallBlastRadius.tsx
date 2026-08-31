import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type RecallPathEdge = { from:string;to:string;relationship:string;quantity?:number|null;unit?:string|null;purpose?:string|null };
type AffectedLot = {
  lot_id:string;
  lot_code:string;
  package_id:string;
  product_id:string;
  product_name:string;
  facility_id:string;
  facility_name:string;
  license_number:string;
  status:string;
  balance:number;
  unit:string;
  depth:number;
  is_source:boolean;
  path:RecallPathEdge[];
};
type ProtectedExposure = {
  key:string;
  package_id:string;
  lot_code:string;
  facility_name:string;
  license_number:string;
  direction:string;
  status:string;
  redacted:boolean;
  depth:number;
  path:RecallPathEdge[];
};
type RecallBlastRadiusResponse = {
  source_lot_id:string;
  affected_lots:AffectedLot[];
  affected_lot_count:number;
  downstream_lot_count:number;
  active_inventory_lot_count:number;
  facility_count:number;
  license_count:number;
  transfer_count:number;
  protected_exposure_count:number;
  protected_exposures:ProtectedExposure[];
  on_hand_by_unit:Record<string,number>;
  status_counts:Record<string,number>;
  cross_facility:boolean;
  redacted_facility_count:number;
  scope_complete:boolean;
  evaluated_max_depth:number;
  hard_depth_limit:number;
  max_depth:number;
};

export function RecallBlastRadius({lotId}:{lotId:string}) {
  const recall=useQuery({
    queryKey:["recall-360",lotId],
    enabled:Boolean(lotId),
    queryFn:({signal})=>apiGet<RecallBlastRadiusResponse>(`/api/v1/material-lineage/lots/${lotId}/recall`,signal),
  });
  const data=recall.data;
  const onHand=data?Object.entries(data.on_hand_by_unit).map(([unit,quantity])=>`${number(quantity)} ${unit}`).join(" · "):"";

  return <section className="inventory-panel">
    <div className="eyebrow">RECALL 360 · BLAST RADIUS</div>
    <h3>Downstream exposure from this package</h3>
    <p className="source-caption">Deterministic read-only analysis follows only durable downstream production, packaging and confirmed transfer edges. It does not place inventory on hold, change Metrc or notify a regulator.</p>
    {recall.isLoading?<div className="state">Calculating downstream recall exposure…</div>:null}
    {recall.isError?<div className="warning-banner">{recall.error.message}</div>:null}
    {data?<>
      {!data.scope_complete?<div className="warning-banner"><strong>Recall scope incomplete:</strong> genealogy continued through the hard traversal safety limit ({data.hard_depth_limit}). Do not treat this package list as the full blast radius; escalate for traceability review before disposition decisions.</div>:null}
      <div className="metrics four">
        <Metric label="Affected packages" value={data.affected_lot_count}/>
        <Metric label="With inventory" value={data.active_inventory_lot_count}/>
        <Metric label="Licenses" value={data.license_count}/>
        <Metric label="Transfers" value={data.transfer_count}/>
      </div>
      <div className="info-banner"><strong>Current on-hand exposure:</strong> {onHand||"No positive on-hand balance remains in accessible affected packages."}</div>
      {data.protected_exposure_count>0?<div className="warning-banner"><strong>Protected / unresolved transfer exposure:</strong> {data.protected_exposure_count} downstream transfer reference(s) cannot be fully opened from this facility scope. Treat these as recall follow-up items rather than assuming the material is clear.</div>:null}
      {data.affected_lots.length?<div className="table-wrap"><table><thead><tr><th>Package / product</th><th>Facility / license</th><th>Exposure</th><th>On hand</th><th>Why it is in scope</th></tr></thead><tbody>{data.affected_lots.map(row=><tr key={row.lot_id}><td><strong>{row.package_id||row.lot_code}</strong><small>{row.product_name}</small></td><td>{row.facility_name}<small>{row.license_number||"No license number"}</small></td><td>{row.is_source?"Recall source":`Downstream · depth ${row.depth}`}<small>{title(row.status)}</small></td><td>{number(row.balance)} {row.unit}</td><td>{row.is_source?"Selected source package":pathLabel(row.path)}</td></tr>)}</tbody></table></div>:<div className="info-banner">No accessible packages were found in the recall scope.</div>}
      {data.protected_exposures.length?<div className="package-timeline">{data.protected_exposures.map(row=><article className="commercial-order-card" key={row.key}><div><strong>{row.package_id||row.lot_code||"Transfer exposure"}</strong><span className="status-pill">{row.redacted?"Protected facility":"In transit"}</span></div><p>{row.facility_name||row.license_number||"Other license"}</p><small>{pathLabel(row.path)}</small></article>)}</div>:null}
    </>:null}
  </section>;
}

function Metric({label,value}:{label:string;value:string|number}){return <article className="metric"><span>{label}</span><strong>{value}</strong></article>}
function number(value:number){return Number(value||0).toLocaleString(undefined,{maximumFractionDigits:4})}
function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
function pathLabel(path:RecallPathEdge[]){
  if(!path.length)return "Directly selected";
  const labels=path.map(edge=>title(edge.relationship));
  return labels.join(" → ");
}
