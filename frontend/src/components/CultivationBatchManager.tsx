import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { CultivationPlant, PlantPhase } from "../types/inventory";
import {
  CultivationActionRequest,
  CultivationIdentityResponse,
  MetrcCultivationActionDialog,
  MetrcObjectLink,
  MetrcRoomLinkDialog,
  useMetrcCultivationIdentities,
} from "./MetrcCultivationControls";
import { StreamlitDialog } from "./StreamlitDialog";

const groupTypes = ["clone_batch", "seed_batch", "nursery", "vegetative", "flowering"] as const;
const activePhases: PlantPhase[] = ["clone", "seedling", "vegetative", "flowering"];

type Group = {
  id:string; group_code:string; group_type:string; strain_name:string; room_code:string; mother_plant_id:string|null;
  mother_plant_tag:string; source_lot_id:string|null; status:string; plant_count:number; active_plant_count:number;
  phase_counts:Record<string,number>; notes:string; created_at:string;
};
type GroupList = { items:Group[] };
type Room = {id:string;room_code:string;display_name:string;phase:string;plant_capacity:number;active:boolean};
type RoomList = {items:Room[]};
type Tag = {id:string;tag_type:string;label:string;status:string;synced_at:string|null};
type TagList = {items:Tag[]};

export function CultivationBatchManager({ plants, canWrite, onChanged }: { plants:CultivationPlant[]; canWrite:boolean; onChanged:()=>void }) {
  const client = useQueryClient();
  const [creating,setCreating]=useState(false);
  const [selected,setSelected]=useState<Group|null>(null);
  const groups=useQuery({queryKey:["cultivation-groups"],queryFn:({signal})=>apiGet<GroupList>("/api/v1/inventory/production/plants/groups",signal)});
  const rooms=useQuery({queryKey:["cultivation-rooms"],queryFn:({signal})=>apiGet<RoomList>("/api/v1/inventory/production/plants/rooms",signal)});
  const identities=useMetrcCultivationIdentities(true);
  const active=groups.data?.items??[];
  const refresh=()=>{void client.invalidateQueries({queryKey:["cultivation-groups"]});void client.invalidateQueries({queryKey:["metrc-cultivation-identities"]});onChanged()};
  const batchLinks=new Map((identities.data?.plant_batches??[]).map(row=>[row.entity_id,row]));
  return <section className="inventory-panel">
    <div className="section-heading"><div><div className="eyebrow">Nursery & plant groups</div><h2>Work plants in batches</h2><p>Create clone/seed groups once, preserve lineage, then let DoobieLogic handle exact Metrc synchronization, confirmation, readback and reconciliation underneath.</p></div>{canWrite?<button className="primary" type="button" onClick={()=>setCreating(true)}>New plant group</button>:null}</div>
    <div className="metrics"><div className="metric"><span>Active groups</span><strong>{active.length}</strong></div><div className="metric"><span>Plants in groups</span><strong>{active.reduce((sum,row)=>sum+row.active_plant_count,0)}</strong></div><div className="metric"><span>Metrc-linked batches</span><strong>{identities.data?.plant_batches.filter(row=>row.status==="verified").length??0}</strong></div></div>
    {groups.isLoading?<div className="state">Loading cultivation groups…</div>:null}{groups.isError?<div className="state error">{groups.error.message}</div>:null}
    {active.length?<div className="table-wrap"><table><thead><tr><th>Group</th><th>Type</th><th>Strain</th><th>Plants</th><th>Room</th><th>Mother</th><th>Current phases</th><th>Metrc</th></tr></thead><tbody>{active.map(row=>{const link=batchLinks.get(row.id);return <tr key={row.id} className="selectable-row" onClick={()=>setSelected(row)}><td><strong>{row.group_code}</strong></td><td>{title(row.group_type)}</td><td>{row.strain_name}</td><td>{row.active_plant_count}/{row.plant_count}</td><td>{row.room_code}</td><td>{row.mother_plant_tag||"—"}</td><td>{Object.entries(row.phase_counts).map(([phase,count])=>`${title(phase)} ${count}`).join(" · ")||"—"}</td><td>{link?<span className="badge">{link.status==="verified"?"Verified":"Review"}</span>:identities.isSuccess?<span className="badge muted">Not linked</span>:"—"}</td></tr>})}</tbody></table></div>:!groups.isLoading?<div className="empty">No active cultivation groups yet. Create a clone, seed or nursery batch to stop entering plants one at a time.</div>:null}
    {identities.isError?<div className="source-caption">Metrc-controlled cultivation actions are not active for this facility/environment. Local cultivation workflows remain available for untracked objects.</div>:null}
    {identities.isSuccess?<TrackedPlantMove plants={plants} rooms={rooms.data?.items??[]} identities={identities.data} canWrite={canWrite} onChanged={refresh}/>:null}
    {creating?<CreateGroup plants={plants} onClose={()=>setCreating(false)} onSaved={()=>{setCreating(false);refresh()}}/>:null}
    {selected?<TransitionGroup group={selected} canWrite={canWrite} identities={identities.data} identitiesAvailable={identities.isSuccess} rooms={rooms.data?.items??[]} onClose={()=>setSelected(null)} onSaved={(next)=>{setSelected(next);refresh()}} onRegulatedChanged={()=>{setSelected(null);refresh()}}/>:null}
  </section>;
}

function CreateGroup({plants,onClose,onSaved}:{plants:CultivationPlant[];onClose:()=>void;onSaved:()=>void}){
  const mothers=useMemo(()=>plants.filter(row=>activePhases.includes(row.phase)),[plants]);
  const [form,setForm]=useState({group_code:"",group_type:"clone_batch",strain_name:"",quantity:10,room_code:"UNASSIGNED",mother_plant_id:"",tag_prefix:"",planted_at:"",estimated_harvest_date:"",notes:""});
  const mutation=useMutation({mutationFn:()=>apiPost<Group>("/api/v1/inventory/production/plants/groups",{
    ...form,quantity:Number(form.quantity),mother_plant_id:form.mother_plant_id||null,source_lot_id:null,plant_tags:null,
    planted_at:form.planted_at||null,estimated_harvest_date:form.estimated_harvest_date||null,
  }),onSuccess:()=>onSaved()});
  return <StreamlitDialog open onClose={onClose} eyebrow="Cultivation · Nursery" title="Create plant group" subtitle="Create the local operating group first. For a connected MA sandbox, open the group afterward and choose Sync batch to Metrc.">
    <div className="form-grid"><label>Group code<input value={form.group_code} onChange={e=>setForm({...form,group_code:e.target.value})}/></label><label>Group type<select value={form.group_type} onChange={e=>setForm({...form,group_type:e.target.value})}>{groupTypes.map(value=><option value={value} key={value}>{title(value)}</option>)}</select></label><label>Strain<input value={form.strain_name} onChange={e=>setForm({...form,strain_name:e.target.value})}/></label><label>Plant count<input type="number" min="1" max="5000" value={form.quantity} onChange={e=>setForm({...form,quantity:Number(e.target.value||0)})}/></label><label>Room<input value={form.room_code} onChange={e=>setForm({...form,room_code:e.target.value})}/></label><label>Plant tag prefix<input placeholder="Defaults to group code" value={form.tag_prefix} onChange={e=>setForm({...form,tag_prefix:e.target.value})}/></label><label>Mother / source plant<select value={form.mother_plant_id} onChange={e=>{const mother=mothers.find(row=>row.id===e.target.value);setForm({...form,mother_plant_id:e.target.value,strain_name:mother?.strain_name??form.strain_name})}}><option value="">No mother plant</option>{mothers.map(row=><option value={row.id} key={row.id}>{row.plant_tag} · {row.strain_name} · {row.phase}</option>)}</select></label><label>Planted date<input type="date" value={form.planted_at} onChange={e=>setForm({...form,planted_at:e.target.value})}/></label><label>Estimated harvest<input type="date" value={form.estimated_harvest_date} onChange={e=>setForm({...form,estimated_harvest_date:e.target.value})}/></label><label className="span-2">Notes<input value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></label></div>
    <div className="info-banner">DoobieLogic creates {Math.max(0,Number(form.quantity||0))} individual local plant records atomically. A later controlled Metrc sync establishes the exact regulatory plant-batch identity and origin.</div><button className="primary submit" disabled={mutation.isPending||!form.group_code.trim()||!form.strain_name.trim()||form.quantity<1} onClick={()=>mutation.mutate()}>{mutation.isPending?"Creating group…":"Create group & plants"}</button>{mutation.isError?<div className="form-error">{mutation.error.message}</div>:null}
  </StreamlitDialog>
}

function TransitionGroup({group,canWrite,identities,identitiesAvailable,rooms,onClose,onSaved,onRegulatedChanged}:{group:Group;canWrite:boolean;identities:CultivationIdentityResponse|undefined;identitiesAvailable:boolean;rooms:Room[];onClose:()=>void;onSaved:(group:Group)=>void;onRegulatedChanged:()=>void}){
  const client=useQueryClient();
  const [phase,setPhase]=useState("");const [room,setRoom]=useState(group.room_code);const [reason,setReason]=useState("");
  const [destinationRoomId,setDestinationRoomId]=useState("");const [startingTag,setStartingTag]=useState("");const [actualDate,setActualDate]=useState(today());
  const [action,setAction]=useState<CultivationActionRequest|null>(null);const [roomToLink,setRoomToLink]=useState<Room|null>(null);
  const mutation=useMutation({mutationFn:()=>apiPost<Group>(`/api/v1/inventory/production/plants/groups/${group.id}/transition`,{phase:phase||null,room_code:room===group.room_code?null:room,reason,notes:""}),onSuccess:onSaved});
  const tags=useQuery({queryKey:["metrc-plant-tags",identities?.environment],queryFn:({signal})=>apiGet<TagList>(`/api/v1/metrc-readiness/tags?tag_type=plant&status=available&environment=${encodeURIComponent(identities?.environment||"sandbox")}`,signal),enabled:Boolean(identitiesAvailable&&identities),retry:false});
  const syncTags=useMutation({mutationFn:()=>apiPost("/api/v1/metrc-readiness/tags/sync",{}),onSuccess:()=>client.invalidateQueries({queryKey:["metrc-plant-tags"]})});
  const groupLink=identities?.plant_batches.find(row=>row.entity_id===group.id);
  const roomLink=(id:string)=>identities?.rooms.find(row=>row.entity_id===id&&row.status==="verified");
  const currentRoom=rooms.find(row=>row.room_code===group.room_code);
  const currentRoomLink=currentRoom?roomLink(currentRoom.id):undefined;
  const destinationRoom=rooms.find(row=>row.id===destinationRoomId);
  const destinationLink=destinationRoom?roomLink(destinationRoom.id):undefined;
  const immature=(group.phase_counts.clone||0)+(group.phase_counts.seedling||0)===group.active_plant_count&&group.active_plant_count>0;
  const syncEligible=["clone_batch","seed_batch"].includes(group.group_type)&&immature;
  const currentRoomReady=group.room_code==="UNASSIGNED"||Boolean(currentRoomLink);
  const refreshIdentities=async()=>{await client.invalidateQueries({queryKey:["metrc-cultivation-identities"]})};
  const regulatedChanged=async()=>{await Promise.all([client.invalidateQueries({queryKey:["cultivation-groups"]}),client.invalidateQueries({queryKey:["metrc-cultivation-identities"]}),client.invalidateQueries({queryKey:["metrc-plant-tags"]})]);onRegulatedChanged()};
  return <StreamlitDialog open onClose={onClose} eyebrow="Cultivation · Batch action" title={group.group_code} subtitle={`${group.strain_name} · ${group.active_plant_count} active plants · ${group.room_code}`}>
    {identitiesAvailable?<section className="inventory-panel compact"><div className="section-heading"><div><h4>Metrc traceability</h4><p className="source-caption">Operator verbs stay simple; exact provider IDs, confirmation, readback and reconciliation stay underneath.</p></div></div>
      {groupLink?<div className={groupLink.status==="verified"?"success-banner":"warning-banner"}><strong>{groupLink.status==="verified"?"Metrc plant batch verified":"Metrc identity needs review"}</strong><br/><span>{groupLink.provider_label||group.group_code} · provider ID {groupLink.provider_id}</span></div>:<div className="info-banner"><strong>Not linked to Metrc yet.</strong><br/><span>Sync this local clone/seed group once to establish its exact Metrc plant-batch identity.</span></div>}
      {!groupLink&&group.room_code!=="UNASSIGNED"&&!currentRoom?<div className="warning-banner">Local room {group.room_code} is not configured as an active cultivation room. Fix the room before Metrc synchronization.</div>:null}
      {!groupLink&&currentRoom&&!currentRoomLink?<div className="warning-banner"><strong>Link the current room first.</strong><br/><span>{currentRoom.display_name||currentRoom.room_code} needs an exact Metrc Location identity before this batch can be synchronized.</span>{canWrite?<button className="secondary" type="button" onClick={()=>setRoomToLink(currentRoom)}>Link room to Metrc</button>:null}</div>:null}
      {!groupLink&&syncEligible&&currentRoomReady&&canWrite?<div className="audit-actions"><button className="primary" type="button" onClick={()=>setAction({operation_type:"plant_batch_sync",entity_id:group.id,actual_date:actualDate,reason:reason.trim()||"Create verified Metrc plant batch"})}>Sync batch to Metrc</button></div>:null}
      {!groupLink&&!syncEligible?<div className="source-caption">Automatic batch creation is currently promoted only while a clone/seed group is fully immature. Other local group types remain fail-closed from automatic Metrc creation.</div>:null}
      {groupLink?.status==="verified"&&immature?<><div className="form-grid"><label>Destination room<select value={destinationRoomId} onChange={e=>setDestinationRoomId(e.target.value)}><option value="">Choose room</option>{rooms.filter(row=>row.active).map(row=><option key={row.id} value={row.id}>{row.display_name||row.room_code}{roomLink(row.id)?" · Metrc linked":" · link required"}</option>)}</select></label><label>Starting Metrc plant tag<select value={startingTag} onChange={e=>setStartingTag(e.target.value)}><option value="">Choose starting tag</option>{(tags.data?.items??[]).map(row=><option key={row.id} value={row.label}>{row.label}</option>)}</select></label><label>Growth date<input type="date" value={actualDate} onChange={e=>setActualDate(e.target.value)}/></label><label>Reason<input value={reason} onChange={e=>setReason(e.target.value)}/></label></div>
        <div className="audit-actions"><button className="secondary" type="button" disabled={syncTags.isPending} onClick={()=>syncTags.mutate()}>{syncTags.isPending?"Refreshing tags…":"Refresh available tags"}</button>{destinationRoom&&!destinationLink&&canWrite?<button className="secondary" type="button" onClick={()=>setRoomToLink(destinationRoom)}>Link destination room</button>:null}{canWrite?<button className="primary" type="button" disabled={!destinationLink||!startingTag||!actualDate} onClick={()=>setAction({operation_type:"plant_batch_vegetative",entity_id:group.id,destination_room_id:destinationRoomId,starting_tag:startingTag,actual_date:actualDate,reason:reason.trim()||"Move verified plant batch to vegetative"})}>Move batch to vegetative</button>:null}</div>
        {tags.isError?<div className="form-error">{tags.error.message}</div>:null}{syncTags.isError?<div className="form-error">{syncTags.error.message}</div>:null}
      </>:null}
      {groupLink?.status==="verified"&&!immature?<div className="source-caption">This group is already individually tracked or beyond the currently promoted batch-growth action. Further phase/harvest changes stay fail-closed until their exact Metrc contracts are promoted.</div>:null}
    </section>:null}
    {!groupLink?<><div className="section-heading"><div><h4>{identitiesAvailable?"Local preparation":"Local batch transition"}</h4><p className="source-caption">{identitiesAvailable?"Before Metrc tracking, you may update the local room. Phase promotion should use the controlled Metrc path above.":"This facility is not using the promoted MA sandbox workflow, so the existing local batch action remains available."}</p></div></div><div className="form-grid">{!identitiesAvailable?<label>Move all active plants to phase<select value={phase} onChange={e=>setPhase(e.target.value)}><option value="">No phase change</option>{activePhases.map(value=><option key={value} value={value}>{title(value)}</option>)}</select></label>:null}<label>Room<input value={room} onChange={e=>setRoom(e.target.value)}/></label><label className="span-2">Reason<input value={reason} onChange={e=>setReason(e.target.value)}/></label></div><div className="info-banner">The local batch action is atomic. Once this group has a verified Metrc identity, legacy local phase/room mutation is blocked server-side.</div>{canWrite?<button className="primary submit" disabled={mutation.isPending||((!phase||identitiesAvailable)&&room===group.room_code)} onClick={()=>mutation.mutate()}>{mutation.isPending?"Applying…":"Apply local preparation"}</button>:<div className="info-banner">Your role can review this group but cannot post cultivation changes.</div>}{mutation.isError?<div className="form-error">{mutation.error.message}</div>:null}</>:null}
    {action?<MetrcCultivationActionDialog request={action} onClose={()=>setAction(null)} onChanged={regulatedChanged}/>:null}
    {roomToLink?<MetrcRoomLinkDialog room={roomToLink} onClose={()=>setRoomToLink(null)} onLinked={refreshIdentities}/>:null}
  </StreamlitDialog>
}

function TrackedPlantMove({plants,rooms,identities,canWrite,onChanged}:{plants:CultivationPlant[];rooms:Room[];identities:CultivationIdentityResponse;canWrite:boolean;onChanged:()=>void}){
  const client=useQueryClient();
  const [plantId,setPlantId]=useState("");const [roomId,setRoomId]=useState("");const [reason,setReason]=useState("");const [actualDate,setActualDate]=useState(today());
  const [action,setAction]=useState<CultivationActionRequest|null>(null);const [roomToLink,setRoomToLink]=useState<Room|null>(null);
  const verifiedPlantLinks=identities.plants.filter(row=>row.status==="verified");
  if(!verifiedPlantLinks.length)return null;
  const linkByPlant=new Map(verifiedPlantLinks.map(row=>[row.entity_id,row]));
  const tracked=plants.filter(row=>linkByPlant.has(row.id)&&["vegetative","flowering"].includes(row.phase));
  const selectedPlant=tracked.find(row=>row.id===plantId);
  const selectedRoom=rooms.find(row=>row.id===roomId);
  const selectedRoomLink=selectedRoom?identities.rooms.find(row=>row.entity_id===selectedRoom.id&&row.status==="verified"):undefined;
  const linkedRoomName=(link:MetrcObjectLink|undefined)=>link?.provider_label||"";
  const refresh=async()=>{await Promise.all([client.invalidateQueries({queryKey:["metrc-cultivation-identities"]}),client.invalidateQueries({queryKey:["plants"]}),client.invalidateQueries({queryKey:["cultivation-groups"]})]);onChanged()};
  return <section className="inventory-panel compact"><div className="section-heading"><div><div className="eyebrow">Metrc tracked plants</div><h3>Move tracked plant</h3><p className="source-caption">Select the plant and destination room. DoobieLogic resolves provider IDs server-side, verifies the Metrc move, then changes the local room.</p></div></div>
    <div className="form-grid"><label>Plant<select value={plantId} onChange={e=>setPlantId(e.target.value)}><option value="">Choose tracked plant</option>{tracked.map(row=><option key={row.id} value={row.id}>{linkByPlant.get(row.id)?.provider_label||row.plant_tag} · {row.strain_name} · {row.room_code}</option>)}</select></label><label>Destination room<select value={roomId} onChange={e=>setRoomId(e.target.value)}><option value="">Choose destination room</option>{rooms.filter(row=>row.active).map(row=>{const link=identities.rooms.find(item=>item.entity_id===row.id&&item.status==="verified");return <option key={row.id} value={row.id}>{row.display_name||row.room_code}{link?` · ${linkedRoomName(link)}`:" · link required"}</option>})}</select></label><label>Move date<input type="date" value={actualDate} onChange={e=>setActualDate(e.target.value)}/></label><label>Reason<input value={reason} onChange={e=>setReason(e.target.value)}/></label></div>
    <div className="audit-actions">{selectedRoom&&!selectedRoomLink&&canWrite?<button className="secondary" type="button" onClick={()=>setRoomToLink(selectedRoom)}>Link destination room</button>:null}{canWrite?<button className="primary" type="button" disabled={!selectedPlant||!selectedRoomLink||!actualDate||selectedPlant?.room_code===selectedRoom?.room_code} onClick={()=>setAction({operation_type:"plant_move",entity_id:plantId,destination_room_id:roomId,actual_date:actualDate,reason:reason.trim()||"Move verified Metrc plant"})}>Move plant</button>:null}</div>
    {selectedPlant&&selectedRoom&&selectedPlant.room_code===selectedRoom.room_code?<div className="source-caption">Choose a different destination room.</div>:null}
    {action?<MetrcCultivationActionDialog request={action} onClose={()=>setAction(null)} onChanged={refresh}/>:null}
    {roomToLink?<MetrcRoomLinkDialog room={roomToLink} onClose={()=>setRoomToLink(null)} onLinked={()=>client.invalidateQueries({queryKey:["metrc-cultivation-identities"]})}/>:null}
  </section>
}

function today(){return new Date().toISOString().slice(0,10)}
function title(value:string){return String(value||"").replaceAll("_"," ").replace(/\b\w/g,char=>char.toUpperCase())}