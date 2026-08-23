import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { apiDownload, apiGet, apiPost, downloadBlob } from "../lib/api";
import { AdminPage } from "./AdminPage";

type UploadRow = {
  ts: string;
  uploader: string;
  role: string;
  filename: string;
  upload_id: string;
  organization_id: string;
  facility_id: string;
  size: number;
  status: string;
};
type UploadsResponse = { ttl_minutes: number; uploads: UploadRow[] };
type Diagnostics = {
  organization_id: string;
  facility_id: string;
  role: string;
  users: number;
  active_facilities: number;
  durable_upload_versions: number;
  integrations: Array<{ provider:string; scope_type:string; status:string; facility_id:string; secret_hint:string; last_validated_at:string|null; last_error:string }>;
};
type AccountContext = { user:{ role:string } };
type FacilityAdminRow = {
  id:string;
  organization_id?:string;
  name:string;
  code:string;
  timezone_name?:string;
  license_number?:string;
  license_type?:string;
  active?:boolean;
  retail_enabled?:boolean;
  production_enabled?:boolean;
  cultivation_enabled?:boolean;
  commercial_enabled?:boolean;
};
type OrganizationAdminRow = { id:string; name:string; slug:string; active:boolean; facilities:FacilityAdminRow[] };
type FacilityForm = {
  name:string;
  code:string;
  timezone_name:string;
  license_number:string;
  license_type:string;
  retail_enabled:boolean;
  production_enabled:boolean;
  cultivation_enabled:boolean;
  commercial_enabled:boolean;
  active:boolean;
};

export function AdminToolsPage() {
  return <div className="admin-tools-parity">
    <AdminPage />
    <FacilityContextEditor />
    <AdminUploads />
    <AdminDiagnostics />
  </div>;
}

function facilityForm(row:FacilityAdminRow):FacilityForm {
  return {
    name:row.name,
    code:row.code,
    timezone_name:row.timezone_name||"America/New_York",
    license_number:row.license_number||"",
    license_type:row.license_type||"",
    retail_enabled:Boolean(row.retail_enabled),
    production_enabled:Boolean(row.production_enabled),
    cultivation_enabled:Boolean(row.cultivation_enabled),
    commercial_enabled:Boolean(row.commercial_enabled),
    active:row.active!==false,
  };
}

function FacilityContextEditor() {
  const client=useQueryClient();
  const context=useQuery({queryKey:["account-context"],queryFn:({signal})=>apiGet<AccountContext>("/api/v1/account/context",signal)});
  const isDev=context.data?.user.role==="dev";
  const organizations=useQuery({
    queryKey:["admin-organizations"],
    queryFn:({signal})=>apiGet<OrganizationAdminRow[]>("/api/v1/admin/organizations",signal),
    enabled:isDev,
  });
  const facilities=useMemo(()=>organizations.data?.flatMap(org=>org.facilities.map(facility=>({...facility,organization_id:org.id,organization_name:org.name})))??[],[organizations.data]);
  const [selectedId,setSelectedId]=useState("");
  const selected=facilities.find(row=>row.id===selectedId)??facilities[0];
  const [form,setForm]=useState<FacilityForm|null>(null);
  useEffect(()=>{
    if(!selected)return;
    if(!selectedId)setSelectedId(selected.id);
    setForm(facilityForm(selected));
  },[selected?.id]);
  const save=useMutation({
    mutationFn:()=>apiPost<FacilityAdminRow>(`/api/v1/admin/facilities/${encodeURIComponent(selected!.id)}/update`,form!),
    onSuccess:async()=>{
      await Promise.all([
        client.invalidateQueries({queryKey:["admin-organizations"]}),
        client.invalidateQueries({queryKey:["account-context"]}),
        client.invalidateQueries({queryKey:["access-options"]}),
        client.invalidateQueries({queryKey:["admin-diagnostics"]}),
      ]);
    },
  });
  if(context.isLoading)return null;
  if(!isDev)return null;
  return <details className="streamlit-expander admin-facility-context" open>
    <summary>Facility license &amp; operation context</summary>
    <div className="streamlit-expander-body">
      <p>Each legal operating site should carry the license and capabilities that belong to that facility. Keep separate Retail and Production/Cultivation license contexts separate rather than sharing one METRC facility.</p>
      {organizations.isLoading?<div className="state">Loading facilities…</div>:null}
      {organizations.isError?<div className="state error">{organizations.error.message}</div>:null}
      {!organizations.isLoading&&!facilities.length?<div className="info-banner">No facilities are available to edit.</div>:null}
      {selected&&form?<>
        <label>Facility<select value={selected.id} onChange={event=>setSelectedId(event.target.value)}>{facilities.map(row=><option value={row.id} key={row.id}>{(row as typeof row & {organization_name?:string}).organization_name} · {row.name} · {row.code}</option>)}</select></label>
        <div className="form-grid two">
          <label>Facility name<input value={form.name} onChange={event=>setForm({...form,name:event.target.value})}/></label>
          <label>Facility code<input value={form.code} onChange={event=>setForm({...form,code:event.target.value})}/></label>
          <label>Timezone<input value={form.timezone_name} onChange={event=>setForm({...form,timezone_name:event.target.value})}/></label>
          <label>License number<input value={form.license_number} onChange={event=>setForm({...form,license_number:event.target.value})}/></label>
          <label>License type<input value={form.license_type} onChange={event=>setForm({...form,license_type:event.target.value})}/></label>
        </div>
        <fieldset className="facility-checks"><legend>Capabilities</legend>
          <label><input type="checkbox" checked={form.retail_enabled} onChange={event=>setForm({...form,retail_enabled:event.target.checked})}/> Retail</label>
          <label><input type="checkbox" checked={form.production_enabled} onChange={event=>setForm({...form,production_enabled:event.target.checked})}/> Production / Manufacturing</label>
          <label><input type="checkbox" checked={form.cultivation_enabled} onChange={event=>setForm({...form,cultivation_enabled:event.target.checked})}/> Cultivation</label>
          <label><input type="checkbox" checked={form.commercial_enabled} onChange={event=>setForm({...form,commercial_enabled:event.target.checked})}/> Commercial</label>
          <label><input type="checkbox" checked={form.active} onChange={event=>setForm({...form,active:event.target.checked})}/> Active</label>
        </fieldset>
        <button className="primary" type="button" disabled={!form.name.trim()||!form.code.trim()||save.isPending} onClick={()=>save.mutate()}>{save.isPending?"Saving…":"Save facility context"}</button>
        {save.isSuccess?<div className="success-banner">Facility license and capability context saved.</div>:null}
        {save.isError?<div className="form-error">Unable to save facility context: {save.error.message}</div>:null}
      </>:null}
    </div>
  </details>;
}

function AdminUploads() {
  const client = useQueryClient();
  const uploads = useQuery({ queryKey:["admin-uploads"], queryFn:({signal})=>apiGet<UploadsResponse>("/api/v1/admin/uploads",signal) });
  const rows = uploads.data?.uploads ?? [];
  const [selected,setSelected] = useState("");
  const selectedRow = useMemo(()=>rows.find(row=>row.upload_id===selected) ?? rows[0], [rows,selected]);
  const clear = useMutation({ mutationFn:()=>apiPost<{cleared:boolean}>("/api/v1/admin/uploads/clear",{}), onSuccess:()=>client.invalidateQueries({queryKey:["admin-uploads"]}) });
  const download = useMutation({ mutationFn:async(row:UploadRow)=>({row,blob:await apiDownload(`/api/v1/admin/uploads/${encodeURIComponent(row.upload_id)}/download`)}), onSuccess:({row,blob})=>downloadBlob(blob,row.filename || "upload.bin") });
  return <details className="streamlit-expander admin-uploads-viewer">
    <summary>🗂️ Admin Uploads</summary>
    <div className="streamlit-expander-body">
      <div className="warning-banner">⚠️ This panel displays sensitive user-uploaded data. Handle with care and do not share outside authorized personnel.</div>
      <p className="source-caption">Uploads remain visible in this admin viewer for {uploads.data?.ttl_minutes ?? 60} minutes, matching the original Streamlit viewer window. Clearing the viewer does not destroy source data already published into DoobieLogic.</p>
      <button className="secondary" type="button" disabled={clear.isPending} onClick={()=>clear.mutate()}>{clear.isPending?"Clearing…":"🗑️ Clear all stored uploads"}</button>
      {clear.isError?<div className="form-error">{clear.error.message}</div>:null}
      {uploads.isLoading?<div className="state">Loading recent uploads…</div>:null}
      {uploads.isError?<div className="state error">{uploads.error.message}</div>:null}
      {!uploads.isLoading&&!uploads.isError&&!rows.length?<p>No uploads logged yet.</p>:null}
      {rows.length?<>
        <div className="table-wrap"><table><thead><tr><th>ts</th><th>uploader</th><th>role</th><th>filename</th><th>upload_id</th></tr></thead><tbody>{rows.map(row=><tr key={row.upload_id}><td>{new Date(row.ts).toLocaleString()}</td><td>{row.uploader||"—"}</td><td>{row.role||"—"}</td><td>{row.filename}</td><td>{row.upload_id}</td></tr>)}</tbody></table></div>
        <h4>Download an uploaded file</h4>
        <label>Select upload<select value={selectedRow?.upload_id ?? ""} onChange={event=>setSelected(event.target.value)}>{rows.map(row=><option value={row.upload_id} key={row.upload_id}>{row.filename} · {row.upload_id}</option>)}</select></label>
        {selectedRow?<div className="detail-facts"><p><strong>Uploader:</strong> {selectedRow.uploader||"—"}</p><p><strong>Role:</strong> {selectedRow.role||"—"}</p><p><strong>Facility:</strong> {selectedRow.facility_id||"—"}</p><p><strong>Size:</strong> {selectedRow.size.toLocaleString()} bytes</p></div>:null}
        <button className="primary" type="button" disabled={!selectedRow||download.isPending} onClick={()=>selectedRow&&download.mutate(selectedRow)}>{download.isPending?"Downloading…":"Download upload"}</button>
        {download.isError?<div className="form-error">{download.error.message}</div>:null}
      </>:null}
    </div>
  </details>;
}

function AdminDiagnostics() {
  const diagnostics = useQuery({ queryKey:["admin-diagnostics"], queryFn:({signal})=>apiGet<Diagnostics>("/api/v1/admin/diagnostics",signal) });
  return <details className="streamlit-expander admin-diagnostics">
    <summary>Operational diagnostics</summary>
    <div className="streamlit-expander-body">
      <p>Doobie diagnostics, compliance source QA, and operational admin utilities.</p>
      {diagnostics.isLoading?<div className="state">Loading diagnostics…</div>:null}
      {diagnostics.isError?<div className="state error">{diagnostics.error.message}</div>:null}
      {diagnostics.data?<>
        <section className="metrics four"><article className="metric"><span>Users</span><strong>{diagnostics.data.users}</strong></article><article className="metric"><span>Active facilities</span><strong>{diagnostics.data.active_facilities}</strong></article><article className="metric"><span>Durable upload versions</span><strong>{diagnostics.data.durable_upload_versions}</strong></article><article className="metric"><span>Role</span><strong>{diagnostics.data.role}</strong></article></section>
        <p className="source-caption">Organization {diagnostics.data.organization_id||"platform"} · Facility {diagnostics.data.facility_id||"none selected"}</p>
        <h4>Integration diagnostics</h4>
        {!diagnostics.data.integrations.length?<div className="info-banner">No integration configurations are visible in this administrative scope.</div>:<div className="table-wrap"><table><thead><tr><th>Provider</th><th>Scope</th><th>Facility</th><th>Status</th><th>Credential</th><th>Last validated</th><th>Last error</th></tr></thead><tbody>{diagnostics.data.integrations.map((row,index)=><tr key={`${row.provider}-${row.scope_type}-${row.facility_id}-${index}`}><td>{row.provider}</td><td>{row.scope_type}</td><td>{row.facility_id||"—"}</td><td>{row.status}</td><td>{row.secret_hint||"Not configured"}</td><td>{row.last_validated_at?new Date(row.last_validated_at).toLocaleString():"Never"}</td><td>{row.last_error||"—"}</td></tr>)}</tbody></table></div>}
      </>:null}
    </div>
  </details>;
}
