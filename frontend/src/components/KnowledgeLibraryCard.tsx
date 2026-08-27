import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPost, apiPostForm } from "../lib/api";

type KnowledgeDocument = {
  id: string;
  title: string;
  source: string;
  source_type: string;
  authority_level: number;
  jurisdiction: string;
  effective_date: string;
  retrieved_or_uploaded_at: string;
  version: string;
  document_hash: string;
  source_url: string;
  scope: "facility" | "organization" | "global";
};

type KnowledgePayload = {
  documents: KnowledgeDocument[];
  health: { ok: boolean; document_count: number; error?: string };
};

type CatalogSource = {
  key: string;
  title: string;
  source: string;
  source_type: string;
  authority_level: number;
  jurisdiction: string;
  effective_date: string;
  version: string;
  url: string;
};

type CatalogPayload = { schema_version: number; reviewed_at: string; sources: CatalogSource[] };
type SeedResult = { indexed: number; unchanged: number; failed: number; health?: { document_count?: number } };

const SOURCE_TYPES = [
  ["facility_sop", "Approved facility SOP"],
  ["internal_policy", "Internal policy"],
  ["approved_equipment_sop", "Approved equipment SOP"],
  ["manufacturer", "Manufacturer documentation"],
  ["metrc", "METRC documentation"],
  ["dutchie", "Dutchie documentation"],
  ["technical_reference", "Technical reference"],
  ["peer_reviewed", "Peer-reviewed reference"],
  ["industry", "Industry material"],
  ["field_practice", "Field-practice note"],
  ["internal_document", "Internal document"],
  ["regulation", "Government regulation (Admin/DEV)"],
  ["regulatory_guidance", "Government guidance (Admin/DEV)"],
] as const;

export function KnowledgeLibraryCard({ canSeedApproved }: { canSeedApproved: boolean }) {
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({
    title: "",
    source: "",
    source_type: "facility_sop",
    jurisdiction: "MA",
    effective_date: "",
    version: "",
    source_url: "",
  });
  const library = useQuery({
    queryKey: ["ai-knowledge"],
    queryFn: ({ signal }) => apiGet<KnowledgePayload>("/api/v1/ai-knowledge", signal),
    retry: false,
  });
  const catalog = useQuery({
    queryKey: ["ai-knowledge-approved"],
    queryFn: ({ signal }) => apiGet<CatalogPayload>("/api/v1/ai-knowledge/approved-sources", signal),
    retry: false,
  });
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["ai-knowledge"] });
  };
  const upload = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a knowledge file first.");
      const body = new FormData();
      body.append("file", file);
      body.append("title", form.title || file.name);
      body.append("source", form.source || file.name);
      body.append("source_type", form.source_type);
      body.append("jurisdiction", form.jurisdiction);
      body.append("effective_date", form.effective_date);
      body.append("version", form.version);
      body.append("source_url", form.source_url);
      body.append("facility_scope", "true");
      body.append("global_scope", "false");
      return apiPostForm<{ document_id: string; chunks: number }>("/api/v1/ai-agents/knowledge", body);
    },
    onSuccess: async () => {
      setFile(null);
      setForm(current => ({ ...current, title: "", source: "", effective_date: "", version: "", source_url: "" }));
      await refresh();
    },
  });
  const seed = useMutation({
    mutationFn: () => apiPost<SeedResult>("/api/v1/ai-knowledge/seed-approved", { keys: [], force_reindex: false }),
    onSuccess: refresh,
  });

  const marketSourceCount = (catalog.data?.sources ?? []).filter(source =>
    source.source_type.includes("market") || source.source_type.includes("retail_market") || source.source_type.includes("wholesale_market")
  ).length;

  return <section className="inventory-panel integration-card">
    <header>
      <div><h2>AI Knowledge Library</h2><p>Facility-scoped SOPs, regulatory material, METRC/Dutchie guidance, technical references, and approved public cannabis market intelligence used to ground DoobieLogic Agents.</p></div>
      <span className={`badge ${library.data?.health.ok ? "production-ready" : ""}`}>{library.data?.health.document_count ?? 0} indexed</span>
    </header>

    <div className="form-grid">
      <label className="span-2">Knowledge file<input type="file" accept=".pdf,.docx,.txt,.md,.markdown,.html,.htm" onChange={event => setFile(event.target.files?.[0] ?? null)}/></label>
      <label>Title<input value={form.title} placeholder={file?.name || "Document title"} onChange={event => setForm({ ...form, title: event.target.value })}/></label>
      <label>Source<input value={form.source} placeholder="Company SOP / manufacturer / agency" onChange={event => setForm({ ...form, source: event.target.value })}/></label>
      <label>Source type<select value={form.source_type} onChange={event => setForm({ ...form, source_type: event.target.value })}>{SOURCE_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>Jurisdiction<input value={form.jurisdiction} placeholder="MA or blank" onChange={event => setForm({ ...form, jurisdiction: event.target.value })}/></label>
      <label>Effective date<input type="date" value={form.effective_date} onChange={event => setForm({ ...form, effective_date: event.target.value })}/></label>
      <label>Version<input value={form.version} placeholder="SOP v3 / manual revision" onChange={event => setForm({ ...form, version: event.target.value })}/></label>
      <label className="span-2">Source URL<input value={form.source_url} placeholder="Required for government/regulatory material" onChange={event => setForm({ ...form, source_url: event.target.value })}/></label>
    </div>
    <div className="audit-actions">
      <button className="primary" disabled={!file || upload.isPending} onClick={() => upload.mutate()}>{upload.isPending ? "Indexing…" : "Upload & Index"}</button>
      {canSeedApproved ? <button className="secondary" disabled={seed.isPending} onClick={() => seed.mutate()}>{seed.isPending ? "Updating…" : "Seed / Update Public Knowledge"}</button> : null}
    </div>
    {upload.isError ? <div className="form-error">{upload.error.message}</div> : null}
    {seed.isError ? <div className="form-error">{seed.error.message}</div> : null}
    {upload.data ? <div className="connection-result success">Indexed {upload.data.chunks} knowledge chunk(s).</div> : null}
    {seed.data ? <div className={seed.data.failed ? "connection-result error" : "connection-result success"}>Public knowledge: {seed.data.indexed} indexed · {seed.data.unchanged} unchanged · {seed.data.failed} failed.</div> : null}

    <div style={{ marginTop: 16 }}>
      <strong>Indexed for this facility</strong>
      {library.isLoading ? <div className="state">Loading knowledge library…</div> : null}
      {library.isError ? <div className="form-error">{library.error.message}</div> : null}
      {!library.isLoading && !library.data?.documents.length ? <p>No knowledge documents are indexed for this facility yet.</p> : null}
      {library.data?.documents.slice(0, 40).map(document => <div key={document.id} className="connection-result" style={{ marginTop: 8 }}>
        <strong>{document.title}</strong><br/>
        {document.source} · authority {document.authority_level} · {document.scope} scope{document.jurisdiction ? ` · ${document.jurisdiction}` : ""}{document.effective_date ? ` · effective ${document.effective_date}` : ""}
        {document.version ? <><br/>Version: {document.version}</> : null}
        {document.source_url ? <><br/><a href={document.source_url} target="_blank" rel="noreferrer">Source reference</a></> : null}
      </div>)}
    </div>

    <footer>
      <span>Approved catalog: {catalog.data?.sources.length ?? 0} source(s)</span>
      <span>Public market intelligence: {marketSourceCount} source(s)</span>
      <span>Catalog reviewed: {catalog.data?.reviewed_at || "unavailable"}</span>
      <span>Facility data stays primary; market sources are benchmark context only.</span>
    </footer>
  </section>;
}
