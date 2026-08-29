import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "../lib/api";

type User={id:string;organization_id:string;username:string;display_name:string;role:string;active:boolean;facility_ids:string[]};
type Facility={id:string;organization_id?:string;name:string;code:string;active?:boolean};
type Organization={id:string;name:string;active:boolean;facilities:Facility[]};
type Context={user:{role:string};organization:{id:string;name:string}|null;facilities:Facility[]};
type Permission={key:string;group:string;label:string;description:string};
type PermissionSnapshot={user_id:string;facility_id:string;role:string;role_defaults:Record<string,boolean>;overrides:Record<string,"allow"|"deny">;effective:Record<string,boolean>;source:Record<string,string>};
type OverrideValue="inherit"|"allow"|"deny";

export function UserPermissionManager(){
  const client=useQueryClient();
  const context=useQuery({queryKey:["account-context"],queryFn:({signal})=>apiGet<Context>("/api/v1/account/context",signal)});
  const users=useQuery({queryKey:["admin-users"],queryFn:({signal})=>apiGet<User[]>("/api/v1/admin/users",signal)});
  const registry=useQuery({queryKey:["permission-registry"],queryFn:({signal})=>apiGet<Permission[]>("/api/v1/admin/permission-registry",signal)});
  const isDev=context.data?.user.role==="dev";
  const organizations=useQuery({queryKey:["admin-organizations"],queryFn:({signal})=>apiGet<Organization[]>("/api/v1/admin/organizations",signal),enabled:isDev});
  const manageable=(users.data??[]).filter(user=>user.active&&user.role!=="dev");
  const [userId,setUserId]=useState("");
  const selected=manageable.find(user=>user.id===userId)??manageable[0];
  const facilities=useMemo(()=>{
    if(!selected)return [] as Facility[];
    if(isDev){
      const org=organizations.data?.find(row=>row.id===selected.organization_id);
      return (org?.facilities??[]).filter(row=>row.active!==false&&(selected.role==="admin"||selected.facility_ids.includes(row.id)));
    }
    return (context.data?.facilities??[]).filter(row=>row.active!==false&&(selected.role==="admin"||selected.facility_ids.includes(row.id)));
  },[selected,isDev,organizations.data,context.data?.facilities]);
  const [facilityId,setFacilityId]=useState("");
  useEffect(()=>{if(selected&&!userId)setUserId(selected.id);},[selected?.id,userId]);
  useEffect(()=>{if(!facilities.some(row=>row.id===facilityId))setFacilityId(facilities[0]?.id??"");},[selected?.id,facilities.map(row=>row.id).join("|")]);
  const snapshot=useQuery({
    queryKey:["user-permissions",selected?.id,facilityId],
    queryFn:({signal})=>apiGet<PermissionSnapshot>(`/api/v1/admin/users/${encodeURIComponent(selected!.id)}/permissions?facility_id=${encodeURIComponent(facilityId)}`,signal),
    enabled:Boolean(selected&&facilityId),
  });
  const [overrides,setOverrides]=useState<Record<string,OverrideValue>>({});
  useEffect(()=>{
    if(!snapshot.data)return;
    const next:Record<string,OverrideValue>={};
    for(const permission of registry.data??[])next[permission.key]=snapshot.data.overrides[permission.key]??"inherit";
    setOverrides(next);
  },[snapshot.data,registry.data]);
  const save=useMutation({
    mutationFn:()=>apiPost<PermissionSnapshot>(`/api/v1/admin/users/${encodeURIComponent(selected!.id)}/permissions`,{facility_id:facilityId,overrides}),
    onSuccess:async data=>{
      await client.invalidateQueries({queryKey:["user-permissions",selected?.id,facilityId]});
      setOverrides(Object.fromEntries((registry.data??[]).map(permission=>[permission.key,data.overrides[permission.key]??"inherit"])) as Record<string,OverrideValue>);
    },
  });
  if(context.isLoading||users.isLoading)return null;
  if(!["dev","admin"].includes(context.data?.user.role??""))return null;
  return <details className="streamlit-expander admin-user-permissions" open>
    <summary>User permissions</summary>
    <div className="streamlit-expander-body">
      <p>Roles provide safe defaults. Use facility-specific overrides only for exceptions. An explicit deny overrides the role default; inherit returns the user to their role default.</p>
      {!manageable.length?<div className="info-banner">No non-DEV users are available for permission overrides.</div>:<>
        <div className="form-grid two">
          <label>User<select value={selected?.id??""} onChange={event=>setUserId(event.target.value)}>{manageable.map(user=><option key={user.id} value={user.id}>{user.display_name||user.username} · {user.role}</option>)}</select></label>
          <label>Facility<select value={facilityId} onChange={event=>setFacilityId(event.target.value)}>{facilities.map(facility=><option key={facility.id} value={facility.id}>{facility.name} · {facility.code}</option>)}</select></label>
        </div>
        {!facilities.length?<div className="warning-banner">This user has no facility assignment available for permission overrides.</div>:null}
        {snapshot.isLoading?<div className="state">Loading effective permissions…</div>:null}
        {snapshot.isError?<div className="state error">{snapshot.error.message}</div>:null}
        {snapshot.data?<div className="table-wrap"><table><thead><tr><th>Permission</th><th>Role default</th><th>Override</th><th>Effective</th></tr></thead><tbody>{(registry.data??[]).map(permission=>{
          const effective=Boolean(snapshot.data?.effective[permission.key]);
          return <tr key={permission.key}><td><strong>{permission.label}</strong><br/><small>{permission.description}</small></td><td>{snapshot.data?.role_defaults[permission.key]?"Allowed":"Denied"}</td><td><select aria-label={`${permission.label} override`} value={overrides[permission.key]??"inherit"} onChange={event=>setOverrides(current=>({...current,[permission.key]:event.target.value as OverrideValue}))}><option value="inherit">Inherit role</option><option value="allow">Allow</option><option value="deny">Deny</option></select></td><td><span className={`badge ${effective?"production-ready":"blocked"}`}>{effective?"Allowed":"Denied"}</span><br/><small>{snapshot.data?.source[permission.key]??"role"}</small></td></tr>;
        })}</tbody></table></div>:null}
        <button type="button" className="primary" disabled={!selected||!facilityId||save.isPending} onClick={()=>save.mutate()}>{save.isPending?"Saving permissions…":"Save user permissions"}</button>
        {save.isSuccess?<div className="success-banner">Permission overrides saved and audited for this facility.</div>:null}
        {save.isError?<div className="form-error">Unable to save permissions: {save.error.message}</div>:null}
      </>}
    </div>
  </details>;
}
