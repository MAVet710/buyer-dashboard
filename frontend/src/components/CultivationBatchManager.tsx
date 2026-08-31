import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { CultivationPlant, PlantPhase } from "../types/inventory";
import { StreamlitDialog } from "./StreamlitDialog";

const groupTypes = ["clone_batch", "seed_batch", "nursery", "vegetative", "flowering"] as const;
const activePhases: PlantPhase[] = ["clone", "seedling", "vegetative", "flowering"];

type Group = {
  id:string; group_code:string; group_type:string; strain_name:string; room_code:string; mother_plant_id:string|null;
  mother_plant_tag:string; source_lot_id:string|null; status:string; plant_count:number; active_plant_count:number;
  phase_counts:Record<string,number>; notes:string; created_at:string;
};

type GroupList = { items:Group[] };

export function CultivationBatchManager({ plants, canWrite, onChanged }: { plants:CultivationPlant[]; canWrite:boolean; onChanged:()=>void }) {
  const client = useQueryClient();
  const [creating,setCreating]=useState(false);
  const [selected,setSelected]=useState<Group|null>(null);
  const groups=useQuery({queryKey:["cultivation-groups"],queryFn:({signal})=>apiGet<GroupList>("/api/v1/inventory/production/plants/groups",signal)});
  const active=groups.data?.items??[];
  const refresh=()=>{void client.invalidateQueries({queryKey:["cultivation-groups"]});onChanged()};
  return <section className="inventory-panel">
    <div className="section-heading"><div><div className="eyebrow">Nursery & plant groups</div><h2>Work plants in batches</h2><p>Create clone/seed groups once, preserve mother/source lineage, and move the whole group through rooms and phases while keeping individual plant history.</p></div>{canWrite?<button className="primary" type="button" onClick={()=>setCreating(true)}>New plant group</button>:null}</div>
    <div className="metrics"><div className="metric"><span>Active groups</span><strong>{active.length}</strong></div><div className="metric"><span>Plants in groups</span><strong>{active.reduce((sum,row)=>sum+row.active_plant_count,0)}</strong></div><div className="metric"><span>Mother-linked</span><strong>{active.filter(row=>row.mother_plant_id).length}</strong></div></div>
    {groups.isLoading?<div className="state">Loading cultivation groups…</div>:null}{groups.isError?<div className="state error">{groups.error.message}</div>:null}
    {active.length?<div className="table-wrap"><table><thead><tr><th>Group</th><th>Type</th><th>Strain</th><th>Plants</th><th>Room</th><th>Mother</th><th>Current phases</th></tr></thead><tbody>{active.map(row=><tr key={row.id} className="selectable-row" onClick={()=>setSelected(row)}><td><strong>{row.group_code}</strong></td><td>{title(row.group_type)}</td><td>{row.strain_name}</td><td>{row.active_plant_count}/{row.plant_count}</td><td>{row.room_code}</td><td>{row.mother_plant_tag||"—"}</td><td>{Object.entries(row.phase_counts).map(([phase,count])=>`${title(phase)} ${count}`).join(" · ")||"—"}</td></tr>)}</tbody></table></div>:!groups.isLoading?<div className="empty">No active cultivation groups yet. Create a clone, seed or nursery batch to stop entering plants one at a time.</div>:null}
    {creating?<CreateGroup plants={plants} onClose={()=>setCreating(false)} onSaved={()=>{setCreating(false);refresh()}}/>:null}
    {selected?<TransitionGroup group={selected} canWrite={canWrite} onClose={()=>setSelected(null)} onSaved={(next)=>{setSelected(next);refresh()}}/>:null}
  </section>;
}

function CreateGroup({plants,onClose,onSaved}:{plants:CultivationPlant[];onClose:()=>void;onSaved:()=>void}){
  const mothers=useMemo(()=>plants.filter(row=>activePhases.includes(row.phase)),[plants]);
  const [form,setForm]=useState({group_code:"",group_type:"clone_batch",strain_name:"",quantity:10,room_code:"UNASSIGNED",mother_plant_id:"",tag_prefix:"",planted_at:"",estimated_harvest_date:"",notes:""});
  const mutation=useMutation({mutationFn:()=>apiPost<Group>("/api/v1/inventory/production/plants/groups",{
    ...form,quantity:Number(form.quantity),mother_plant_id:form.mother_plant_id||null,source_lot_id:null,plant_tags:null,
    planted_at:form.planted_at||null,estimated_harvest_date:form.estimated_harvest_date||null,
  }),onSuccess:()=>onSaved()});
  return <StreamlitDialog open onClose={onClose} eyebrow="Cultivation · Nursery" title="Create plant group" subtitle="Generate a real batch of plants with durable mother/source lineage in one transaction.">
    <div className="form-grid"><label>Group code<input value={form.group_code} onChange={e=>setForm({...form,group_code:e.target.value})}/></label><label>Group type<select value={form.group_type} onChange={e=>setForm({...form,group_type:e.target.value})}>{groupTypes.map(value=><option value={value} key={value}>{title(value)}</option>)}</select></label><label>Strain<input value={form.strain_name} onChange={e=>setForm({...form,strain_name:e.target.value})}/></label><label>Plant count<input type="number" min="1" max="5000" value={form.quantity} onChange={e=>setForm({...form,quantity:Number(e.target.value||0)})}/></label><label>Room<input value={form.room_code} onChange={e=>setForm({...form,room_code:e.target.value})}/></label><label>Plant tag prefix<input placeholder="Defaults to group code" value={form.tag_prefix} onChange={e=>setForm({...form,tag_prefix:e.target.value})}/></label><label>Mother / source plant<select value={form.mother_plant_id} onChange={e=>{const mother=mothers.find(row=>row.id===e.target.value);setForm({...form,mother_plant_id:e.target.value,strain_name:mother?.strain_name??form.strain_name})}}><option value="">No mother plant</option>{mothers.map(row=><option value={row.id} key={row.id}>{row.plant_tag} · {row.strain_name} · {row.phase}</option>)}</select></label><label>Planted date<input type="date" value={form.planted_at} onChange={e=>setForm({...form,planted_at:e.target.value})}/></label><label>Estimated harvest<input type="date" value={form.estimated_harvest_date} onChange={e=>setForm({...form,estimated_harvest_date:e.target.value})}/></label><label className="span-2">Notes<input value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></label></div>
    <div className="info-banner">DoobieLogic will create {Math.max(0,Number(form.quantity||0))} individual plant records atomically and preserve the group relationship on every plant.</div><button className="primary submit" disabled={mutation.isPending||!form.group_code.trim()||!form.strain_name.trim()||form.quantity<1} onClick={()=>mutation.mutate()}>{mutation.isPending?"Creating group…":"Create group & plants"}</button>{mutation.isError?<div className="form-error">{mutation.error.message}</div>:null}
  </StreamlitDialog>
}

function TransitionGroup({group,canWrite,onClose,onSaved}:{group:Group;canWrite:boolean;onClose:()=>void;onSaved:(group:Group)=>void}){
  const [phase,setPhase]=useState("");const [room,setRoom]=useState(group.room_code);const [reason,setReason]=useState("");
  const mutation=useMutation({mutationFn:()=>apiPost<Group>(`/api/v1/inventory/production/plants/groups/${group.id}/transition`,{phase:phase||null,room_code:room===group.room_code?null:room,reason,notes:""}),onSuccess:onSaved});
  return <StreamlitDialog open onClose={onClose} eyebrow="Cultivation · Batch action" title={group.group_code} subtitle={`${group.strain_name} · ${group.active_plant_count} active plants · ${group.room_code}`}><div className="form-grid"><label>Move all active plants to phase<select value={phase} onChange={e=>setPhase(e.target.value)}><option value="">No phase change</option>{activePhases.map(value=><option key={value} value={value}>{title(value)}</option>)}</select></label><label>Room<input value={room} onChange={e=>setRoom(e.target.value)}/></label><label className="span-2">Reason<input value={reason} onChange={e=>setReason(e.target.value)}/></label></div><div className="info-banner">The batch action is atomic. If any plant cannot make the requested transition or the destination room would exceed capacity, none of the plants are changed.</div>{canWrite?<button className="primary submit" disabled={mutation.isPending||(!phase&&room===group.room_code)} onClick={()=>mutation.mutate()}>{mutation.isPending?"Applying…":"Apply to entire group"}</button>:<div className="info-banner">Your role can review this group but cannot post cultivation changes.</div>}{mutation.isError?<div className="form-error">{mutation.error.message}</div>:null}</StreamlitDialog>
}

function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}
