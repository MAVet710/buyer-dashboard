import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
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

export function AdminToolsPage() {
  return <div className="admin-tools-parity">
    <AdminPage />
    <AdminUploads />
    <AdminDiagnostics />
  </div>;
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
