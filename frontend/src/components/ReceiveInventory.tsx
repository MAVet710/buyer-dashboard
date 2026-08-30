import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { InventoryReceipt, ProductOption } from "../types/inventory";
import { InventoryReconciliationControl } from "./InventoryReconciliationControl";
import { StreamlitDialog } from "./StreamlitDialog";

type Stage = "queue" | "details" | "review" | "complete" | "manual";
type InboundTransfer = {
  transfer_id: string;
  delivery_id: string;
  manifest: string;
  vendor: string;
  vendor_license: string;
  package_count: number;
  received_count: number;
  estimated_arrival: string;
  source: string;
};
type InboundQueue = { configured: boolean; message: string; license_number?: string; transfers: InboundTransfer[] };
type InboundPackage = {
  package_record_id: string;
  package_id: string;
  item_id: string;
  item_name: string;
  category: string;
  quantity: number;
  shipped_quantity: number;
  received_quantity: number;
  unit: string;
  shipment_state: string;
  lab_testing_state: string;
  delivery_id: string;
  delivery_number: string;
};
type TransferDetails = { transfer_id: string; packages: InboundPackage[]; warnings: string[]; read_only_traceability: boolean };
type LocationSettings = { auto_map_products_during_receive: boolean; default_receiving_room: string };
type PhysicalCondition = "ok" | "damaged" | "other";
type MappedPackage = InboundPackage & {
  product_id: string;
  location: string;
  coa_reference: string;
  notes: string;
  physical_quantity: number;
  physical_condition: PhysicalCondition;
  discrepancy_note: string;
};
type LabPayload = { package_record_id: string; lab_results: Record<string, unknown>[]; read_only: boolean };
type ReceivingPreflight = {
  id: string;
  status: "prepared" | "processing" | "consumed" | "stale" | "cancelled";
  transfer_id: string;
  jurisdiction: string;
  environment: string;
  license_number: string;
  snapshot_digest: string;
  expires_at: string;
  reason: string;
};
type ReceivingCommit = { preflight: ReceivingPreflight; receipts: Array<{ lot_id: string }>; idempotent: boolean };
type ReceivingDiscrepancy = {
  id: string;
  preflight_id: string;
  transfer_id: string;
  package_identity: string;
  provider_quantity: string;
  observed_quantity: string;
  unit: string;
  discrepancy_type: "short" | "over" | "missing" | "unexpected" | "damaged" | "other";
  status: "open" | "resolved" | "cancelled";
  note: string;
  recorded_by: string;
  resolved_by: string;
  resolved_at: string | null;
  resolution_note: string;
};
type DiscrepancyList = {
  preflight_id: string;
  transfer_id: string;
  can_resolve: boolean;
  open_count: number;
  discrepancies: ReceivingDiscrepancy[];
};
type DiscrepancyRecordResult = {
  preflight: ReceivingPreflight;
  can_post: boolean;
  can_resolve: boolean;
  message: string;
  discrepancies: ReceivingDiscrepancy[];
};

const empty: InventoryReceipt = { product_id: "", package_id: "", lot_code: "", quantity: 0, unit: "g", location: "RECEIVING", source_name: "", manifest_reference: "", lab_testing_state: "TestPassed", coa_reference: "", notes: "" };

export function ReceiveInventory({ operation, onClose }: { operation: "retail" | "production"; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [stage, setStage] = useState<Stage>("queue");
  const [selected, setSelected] = useState<InboundTransfer | null>(null);
  const [mapped, setMapped] = useState<MappedPackage[]>([]);
  const [preflight, setPreflight] = useState<ReceivingPreflight | null>(null);
  const [postedCount, setPostedCount] = useState(0);
  const [labs, setLabs] = useState<Record<string, LabPayload>>({});
  const [labLoading, setLabLoading] = useState("");
  const [labError, setLabError] = useState("");
  const [manual, setManual] = useState(empty);
  const [resolutionNotes, setResolutionNotes] = useState<Record<string, string>>({});

  const products = useQuery({ queryKey: ["inventory-products"], queryFn: ({ signal }) => apiGet<ProductOption[]>("/api/v1/inventory/products", signal) });
  const settings = useQuery({ queryKey: ["location-settings"], queryFn: ({ signal }) => apiGet<LocationSettings>("/api/v1/location-settings", signal) });
  const queue = useQuery({ queryKey: ["inventory-inbound", operation], queryFn: ({ signal }) => apiGet<InboundQueue>(`/api/v1/inventory/${operation}/inbound`, signal) });
  const details = useQuery({
    queryKey: ["inventory-inbound-details", operation, selected?.transfer_id],
    enabled: Boolean(selected?.transfer_id),
    queryFn: ({ signal }) => apiGet<TransferDetails>(`/api/v1/inventory/${operation}/inbound/${encodeURIComponent(selected!.transfer_id)}`, signal),
  });
  const discrepancyQuery = useQuery({
    queryKey: ["receiving-discrepancies", operation, selected?.transfer_id, preflight?.id],
    enabled: Boolean(selected?.transfer_id && preflight?.id),
    queryFn: ({ signal }) => apiGet<DiscrepancyList>(`/api/v1/inventory/${operation}/inbound/${encodeURIComponent(selected!.transfer_id)}/preflight/${encodeURIComponent(preflight!.id)}/discrepancies`, signal),
  });

  useEffect(() => {
    if (!details.data || !selected) return;
    const room = settings.data?.default_receiving_room || "Receiving";
    setMapped(details.data.packages.map(row => ({
      ...row,
      product_id: "",
      location: room,
      coa_reference: "",
      notes: "",
      physical_quantity: row.quantity,
      physical_condition: "ok",
      discrepancy_note: "",
    })));
  }, [details.data, selected, settings.data?.default_receiving_room]);

  const readyToReview = mapped.length > 0 && mapped.every(row => row.product_id && row.quantity > 0 && (row.package_id || row.package_record_id) && row.unit && row.physical_quantity >= 0);
  const reviewedReceipts = useMemo(() => mapped.map(row => ({
    product_id: row.product_id,
    package_id: row.package_id || row.package_record_id,
    lot_code: row.package_id || row.package_record_id,
    quantity: row.quantity,
    unit: row.unit || "unit",
    location: row.location || settings.data?.default_receiving_room || "Receiving",
    source_name: selected?.vendor || "",
    manifest_reference: selected?.manifest || selected?.transfer_id || "",
    lab_testing_state: row.lab_testing_state || "",
    coa_reference: row.coa_reference,
    notes: row.notes,
  })), [mapped, selected, settings.data?.default_receiving_room]);
  const physicalObservations = useMemo(() => mapped.map(row => ({
    package_id: row.package_id || row.package_record_id,
    observed_quantity: row.physical_quantity,
    unit: row.unit || "unit",
    condition: row.physical_condition,
    note: row.discrepancy_note,
  })), [mapped]);
  const hasPhysicalMismatch = mapped.some(row => row.physical_quantity !== row.quantity || row.physical_condition !== "ok");
  const discrepancyRows = discrepancyQuery.data?.discrepancies || [];
  const openDiscrepancies = discrepancyRows.filter(row => row.status === "open");
  const canPost = Boolean(preflight) && !hasPhysicalMismatch && openDiscrepancies.length === 0;

  const preparePreflight = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Choose an inbound transfer before review.");
      return apiPost<ReceivingPreflight>(`/api/v1/inventory/${operation}/inbound/${encodeURIComponent(selected.transfer_id)}/preflight`, {});
    },
    onSuccess: result => {
      setPreflight(result);
      setResolutionNotes({});
      setStage("review");
    },
  });
  const recordDiscrepancy = useMutation({
    mutationFn: () => {
      if (!selected || !preflight) throw new Error("A provider preflight is required before recording a discrepancy.");
      return apiPost<DiscrepancyRecordResult>(`/api/v1/inventory/${operation}/inbound/${encodeURIComponent(selected.transfer_id)}/preflight/discrepancies`, {
        preflight_id: preflight.id,
        observations: physicalObservations,
      });
    },
    onSuccess: async result => {
      setPreflight(result.preflight);
      await queryClient.invalidateQueries({ queryKey: ["receiving-discrepancies", operation, selected?.transfer_id, preflight?.id] });
    },
  });
  const resolveDiscrepancy = useMutation({
    mutationFn: ({ discrepancyId, note }: { discrepancyId: string; note: string }) => {
      if (!selected || !preflight) throw new Error("A provider preflight is required before resolving a discrepancy.");
      return apiPost<ReceivingDiscrepancy>(`/api/v1/inventory/${operation}/inbound/${encodeURIComponent(selected.transfer_id)}/preflight/${encodeURIComponent(preflight.id)}/discrepancies/${encodeURIComponent(discrepancyId)}/resolve`, {
        resolution_note: note,
      });
    },
    onSuccess: async result => {
      setResolutionNotes(current => ({ ...current, [result.id]: "" }));
      await queryClient.invalidateQueries({ queryKey: ["receiving-discrepancies", operation, selected?.transfer_id, preflight?.id] });
    },
  });
  const postBatch = useMutation({
    mutationFn: () => {
      if (!selected || !preflight) throw new Error("A fresh provider confirmation is required before posting inventory.");
      return apiPost<ReceivingCommit>(`/api/v1/inventory/${operation}/inbound/${encodeURIComponent(selected.transfer_id)}/preflight/commit`, {
        preflight_id: preflight.id,
        receipts: reviewedReceipts,
        observations: physicalObservations,
      });
    },
    onSuccess: async result => {
      setPreflight(result.preflight);
      setPostedCount(result.receipts.length);
      await queryClient.invalidateQueries({ queryKey: ["inventory"] });
      await queryClient.invalidateQueries({ queryKey: ["inventory-receive-history", operation] });
      await queryClient.invalidateQueries({ queryKey: ["inventory-inbound", operation] });
      setStage("complete");
    },
  });
  const manualReceive = useMutation({
    mutationFn: () => apiPost(`/api/v1/inventory/${operation}/receipts`, manual),
    onSuccess: async () => {
      setPostedCount(1);
      await queryClient.invalidateQueries({ queryKey: ["inventory"] });
      await queryClient.invalidateQueries({ queryKey: ["inventory-receive-history", operation] });
      setStage("complete");
    },
  });

  const chooseTransfer = (transfer: InboundTransfer) => { setSelected(transfer); setMapped([]); setPreflight(null); setResolutionNotes({}); setLabs({}); setLabError(""); setStage("details"); };
  const backToQueue = () => { setSelected(null); setMapped([]); setPreflight(null); setResolutionNotes({}); setLabs({}); setStage("queue"); };
  const backToDetails = () => { setPreflight(null); setResolutionNotes({}); setStage("details"); };
  const updateMapped = (index: number, patch: Partial<MappedPackage>) => setMapped(rows => rows.map((row, position) => position === index ? { ...row, ...patch } : row));
  const updateManual = (key: keyof InventoryReceipt, value: string | number) => setManual(current => ({ ...current, [key]: value }));
  const loadLabs = async (row: MappedPackage) => {
    if (!row.package_record_id) return;
    setLabError(""); setLabLoading(row.package_record_id);
    try {
      const result = await apiGet<LabPayload>(`/api/v1/inventory/${operation}/inbound/packages/${encodeURIComponent(row.package_record_id)}/lab-results`);
      setLabs(current => ({ ...current, [row.package_record_id]: result }));
    } catch (error) {
      setLabError(error instanceof Error ? error.message : "Unable to load METRC lab results.");
    } finally { setLabLoading(""); }
  };

  const title = operation === "production" ? "Receive production inventory" : "Receive inventory";
  return <StreamlitDialog open onClose={onClose} eyebrow={operation === "production" ? "Production Ops · Inbound Inventory" : "Retail Ops · Inbound Inventory"} title={title} subtitle="Inbound Queue → Receive Details → Provider Check → Post Inventory → Labels">
    <div className="receive-workflow">
      <div className="info-banner"><strong>Traceability stays read-only in this work window.</strong> State transfer acceptance still happens in METRC. DoobieLogic keeps the provider quantity immutable, records the separate physical count, and blocks local inventory whenever those facts disagree.</div>
      <StageRail stage={stage}/>

      {stage === "queue" ? <>
        <div className="section-heading"><div><h3>Inbound Queue</h3><p>{queue.data?.message || "Loading the active facility inbound queue…"}</p></div><button className="secondary" type="button" onClick={() => queue.refetch()}>Refresh</button></div>
        {queue.isLoading ? <div className="state">Loading inbound transfers for the active facility license…</div> : null}
        {queue.isError ? <div className="state error">{queue.error.message}</div> : null}
        {queue.data?.configured && queue.data.license_number ? <p className="source-caption">Active facility license: {queue.data.license_number}</p> : null}
        <InventoryReconciliationControl operation={operation}/>
        {queue.data?.transfers.length ? <div className="receive-queue-list">{queue.data.transfers.map(transfer => <button className="receive-queue-row" type="button" key={transfer.transfer_id} onClick={() => chooseTransfer(transfer)}><span><strong>{transfer.manifest || `Transfer ${transfer.transfer_id}`}</strong><small>{transfer.vendor || "Unknown source"}{transfer.vendor_license ? ` · ${transfer.vendor_license}` : ""}</small></span><span><b>{transfer.package_count}</b><small>packages</small></span><span><b>{transfer.received_count}</b><small>received</small></span><em>Receive Details →</em></button>)}</div> : !queue.isLoading && !queue.isError ? <div className="empty">No pending inbound transfers are visible for this facility.</div> : null}
        {!queue.data?.configured ? <div className="warning-banner">Connect METRC for this exact facility under Data &amp; Settings → Integrations to load the live inbound queue. Retail and production/cultivation facilities keep separate license context.</div> : null}
        <details className="streamlit-expander"><summary>Manual receipt (additive fallback)</summary><div className="streamlit-expander-body"><p className="source-caption">Use only when the inbound transfer is not available through the configured facility traceability connection.</p><button className="secondary" type="button" onClick={() => setStage("manual")}>Open manual receipt</button></div></details>
      </> : null}

      {stage === "details" ? <>
        <div className="section-heading"><button className="secondary" type="button" onClick={backToQueue}>← Inbound Queue</button><div><h3>Receive Details</h3><p>{selected?.manifest || selected?.transfer_id} · {selected?.vendor || "Unknown source"}</p></div></div>
        {details.isLoading ? <div className="state">Loading delivery packages…</div> : null}
        {details.isError ? <div className="state error">{details.error.message}</div> : null}
        {details.data?.warnings.map((warning, index) => <div className="warning-banner" key={index}>{warning}</div>)}
        <div className="info-banner"><strong>Count what is physically in front of you.</strong> Do not edit the METRC quantity to force a match. Enter the physical count and condition separately; DoobieLogic will create a discrepancy if they differ.</div>
        {mapped.length ? <div className="receive-package-editor">{mapped.map((row, index) => {
          const mismatch = row.physical_quantity !== row.quantity || row.physical_condition !== "ok";
          return <article className="receive-package-card" key={`${row.package_record_id}-${index}`}>
            <header><div><strong>{row.item_name || "Incoming item"}</strong><small>{row.package_id || row.package_record_id} · {row.category || "Uncategorized"}</small></div><span>{mismatch ? "Needs review" : "Physical match"}</span></header>
            <div className="form-grid two">
              <label>Mapped Product<select value={row.product_id} onChange={event => { const product = products.data?.find(item => item.id === event.target.value); updateMapped(index, { product_id: event.target.value, unit: row.unit || product?.base_unit || "unit" }); }}><option value="">Choose catalog product…</option>{products.data?.map(product => <option value={product.id} key={product.id}>{product.name} · {product.sku}</option>)}</select></label>
              <label>Receiving room<input value={row.location} onChange={event => updateMapped(index, { location: event.target.value })}/></label>
              <label>METRC quantity<input type="number" value={row.quantity} readOnly/><small>Provider controlled · never edited here</small></label>
              <label>METRC unit<input value={row.unit} readOnly/><small>Provider controlled</small></label>
              <label>Physical count<input type="number" min="0" step="any" value={row.physical_quantity} onChange={event => updateMapped(index, { physical_quantity: Number(event.target.value) })}/><small>{mismatch ? "Does not match provider state" : "Matches provider state"}</small></label>
              <label>Physical condition<select value={row.physical_condition} onChange={event => updateMapped(index, { physical_condition: event.target.value as PhysicalCondition })}><option value="ok">OK</option><option value="damaged">Damaged</option><option value="other">Other review needed</option></select></label>
              <label>METRC lab state<input value={row.lab_testing_state} readOnly/><small>Provider controlled</small></label>
              <label>COA reference<input value={row.coa_reference} onChange={event => updateMapped(index, { coa_reference: event.target.value })}/></label>
            </div>
            {mismatch ? <label>Discrepancy note<input value={row.discrepancy_note} onChange={event => updateMapped(index, { discrepancy_note: event.target.value })} placeholder="What was physically observed?"/></label> : null}
            <label>Receive notes<input value={row.notes} onChange={event => updateMapped(index, { notes: event.target.value })}/></label>
            <div className="receive-lab-actions"><button className="secondary" type="button" disabled={!row.package_record_id || labLoading === row.package_record_id} onClick={() => loadLabs(row)}>{labLoading === row.package_record_id ? "Loading labs…" : "Pull read-only METRC lab results"}</button>{labs[row.package_record_id] ? <span>{labs[row.package_record_id].lab_results.length} lab result row(s) loaded</span> : null}</div>
          </article>;
        })}</div> : !details.isLoading && !details.isError ? <div className="empty">This transfer has no remaining packages to receive.</div> : null}
        {labError ? <div className="state error">{labError}</div> : null}
        {preparePreflight.isError ? <div className="state error">{preparePreflight.error.message}</div> : null}
        <div className="audit-actions"><button className="primary" type="button" disabled={!readyToReview || preparePreflight.isPending} onClick={() => preparePreflight.mutate()}>{preparePreflight.isPending ? "Confirming with METRC…" : "Confirm provider state & review"}</button></div>
      </> : null}

      {stage === "review" ? <>
        <div className="section-heading"><button className="secondary" type="button" onClick={backToDetails}>← Receive Details</button><div><h3>Review</h3><p>Provider truth and the physical receipt remain separate until they agree.</p></div></div>
        {preflight ? <div className="success-banner"><strong>Provider preflight confirmed.</strong><br/>METRC {preflight.jurisdiction} · {preflight.environment} · license {preflight.license_number} · evidence {preflight.snapshot_digest.slice(0, 12)}… · expires {new Date(preflight.expires_at).toLocaleTimeString()}</div> : null}
        <div className="table-wrap"><table><thead><tr><th>Incoming Item</th><th>Package</th><th>METRC Qty</th><th>Physical Qty</th><th>Condition</th><th>Room</th></tr></thead><tbody>{mapped.map((row, index) => <tr key={index}><td>{row.item_name}</td><td>{row.package_id || row.package_record_id}</td><td>{row.quantity.toLocaleString()} {row.unit}</td><td>{row.physical_quantity.toLocaleString()} {row.unit}</td><td>{row.physical_condition}</td><td>{row.location}</td></tr>)}</tbody></table></div>

        {hasPhysicalMismatch ? <div className="warning-banner"><strong>Physical receipt does not match METRC.</strong> Local inventory is blocked. Record the discrepancy instead of changing the provider quantity.</div> : <div className="info-banner">Physical count matches the prepared provider snapshot. Posting still performs a second fresh METRC read before the atomic local receipt.</div>}

        {discrepancyQuery.isError ? <div className="state error">{discrepancyQuery.error.message}</div> : null}
        {recordDiscrepancy.isError ? <div className="state error">{recordDiscrepancy.error.message}</div> : null}
        {resolveDiscrepancy.isError ? <div className="state error">{resolveDiscrepancy.error.message}</div> : null}
        {discrepancyRows.length ? <section className="inventory-panel">
          <h3>Receiving exceptions</h3>
          <p className="source-caption">These records preserve what was physically observed without mutating METRC or inventory.</p>
          <div className="receive-package-editor">{discrepancyRows.map(row => <article className="receive-package-card" key={row.id}>
            <header><div><strong>{row.discrepancy_type.toUpperCase()} · {row.package_identity}</strong><small>Provider {row.provider_quantity} {row.unit} · observed {row.observed_quantity} {row.unit}</small></div><span>{row.status}</span></header>
            {row.note ? <p>{row.note}</p> : null}
            {row.status === "resolved" ? <div className="success-banner">Resolved by {row.resolved_by || "authorized reviewer"}{row.resolution_note ? ` · ${row.resolution_note}` : ""}</div> : null}
            {row.status === "open" && discrepancyQuery.data?.can_resolve ? <div className="form-grid two"><label>Resolution note<input value={resolutionNotes[row.id] || ""} onChange={event => setResolutionNotes(current => ({ ...current, [row.id]: event.target.value }))} placeholder="How was the exception verified/resolved?"/></label><div className="audit-actions"><button className="secondary" type="button" disabled={(resolutionNotes[row.id] || "").trim().length < 3 || resolveDiscrepancy.isPending} onClick={() => resolveDiscrepancy.mutate({ discrepancyId: row.id, note: resolutionNotes[row.id] || "" })}>Resolve exception</button></div></div> : null}
            {row.status === "open" && !discrepancyQuery.data?.can_resolve ? <div className="warning-banner">Supervisor or QA review is required before this exception can be resolved.</div> : null}
          </article>)}</div>
        </section> : null}

        {postBatch.isError ? <div className="state error">{postBatch.error.message}</div> : null}
        <div className="audit-actions">
          {hasPhysicalMismatch && discrepancyRows.length === 0 ? <button className="primary" type="button" disabled={!preflight || recordDiscrepancy.isPending} onClick={() => recordDiscrepancy.mutate()}>{recordDiscrepancy.isPending ? "Recording exception…" : "Record discrepancy & block receipt"}</button> : null}
          {hasPhysicalMismatch && discrepancyRows.length > 0 && openDiscrepancies.length === 0 ? <button className="secondary" type="button" onClick={backToDetails}>Refresh physical review after resolution</button> : null}
          {!hasPhysicalMismatch ? <button className="primary" type="button" disabled={!canPost || postBatch.isPending || discrepancyQuery.isLoading} onClick={() => postBatch.mutate()}>{postBatch.isPending ? "Rechecking METRC & posting…" : openDiscrepancies.length ? "Resolve exceptions before posting" : "Verify again & Post Inventory"}</button> : null}
        </div>
      </> : null}

      {stage === "complete" ? <>
        <div className="success-banner"><strong>Inventory receipt posted.</strong><br/>{postedCount} package(s) were added to the active {operation} facility after the physical review and matching provider readback.</div>
        <section className="inventory-panel"><h3>Labels</h3><p className="source-caption">Print the reviewed package labels now or close this work window and return to Inventory.</p><div className="label-sheet">{reviewedReceipts.slice(0, 24).map((row, index) => { const product = products.data?.find(item => item.id === row.product_id); return <article className="inventory-label" key={index}><strong>{product?.name || "Received inventory"}</strong><span>{row.package_id || row.lot_code}</span><b>{row.quantity.toLocaleString()} {row.unit}</b><small>{row.location} · {row.manifest_reference}</small></article>; })}</div></section>
        <div className="audit-actions"><button className="secondary" type="button" onClick={() => window.print()}>Print labels</button><button className="primary" type="button" onClick={onClose}>Done</button></div>
      </> : null}

      {stage === "manual" ? <>
        <div className="section-heading"><button className="secondary" type="button" onClick={() => setStage("queue")}>← Inbound Queue</button><div><h3>Manual receipt</h3><p>Additive fallback for inventory that cannot be loaded from the traceability queue.</p></div></div>
        <div className="form-grid">
          <label className="span-2">Product<select value={manual.product_id} onChange={event => { const product = products.data?.find(item => item.id === event.target.value); updateManual("product_id", event.target.value); if (product) updateManual("unit", product.base_unit); }}><option value="">Select product…</option>{products.data?.map(product => <option value={product.id} key={product.id}>{product.name} · {product.sku}</option>)}</select></label>
          <label>Package ID<input value={manual.package_id} onChange={event => updateManual("package_id", event.target.value)}/></label>
          <label>Internal lot<input value={manual.lot_code} onChange={event => updateManual("lot_code", event.target.value)}/></label>
          <label>Quantity<input type="number" min="0" value={manual.quantity || ""} onChange={event => updateManual("quantity", Number(event.target.value))}/></label>
          <label>Unit<input value={manual.unit} onChange={event => updateManual("unit", event.target.value)}/></label>
          <label>Location<input value={manual.location} onChange={event => updateManual("location", event.target.value)}/></label>
          <label>Lab state<select value={manual.lab_testing_state} onChange={event => updateManual("lab_testing_state", event.target.value)}><option>TestPassed</option><option>TestingInProgress</option><option>NotSubmitted</option><option>TestFailed</option></select></label>
          <label>Source / supplier<input value={manual.source_name} onChange={event => updateManual("source_name", event.target.value)}/></label>
          <label>Manifest / transfer<input value={manual.manifest_reference} onChange={event => updateManual("manifest_reference", event.target.value)}/></label>
          <label>COA reference<input value={manual.coa_reference} onChange={event => updateManual("coa_reference", event.target.value)}/></label>
          <label>Notes<input value={manual.notes} onChange={event => updateManual("notes", event.target.value)}/></label>
        </div>
        {manualReceive.isError ? <div className="form-error">{manualReceive.error.message}</div> : null}
        <button className="primary submit" type="button" disabled={!manual.product_id || !manual.quantity || (!manual.package_id && !manual.lot_code) || manualReceive.isPending} onClick={() => manualReceive.mutate()}>{manualReceive.isPending ? "Receiving…" : "Receive inventory"}</button>
      </> : null}
    </div>
  </StreamlitDialog>;
}

function StageRail({ stage }: { stage: Stage }) {
  const stages: Stage[] = ["queue", "details", "review", "complete"];
  if (stage === "manual") return null;
  const current = stages.indexOf(stage);
  return <ol className="receive-stage-rail">{["Inbound Queue", "Receive Details", "Provider Check", "Post Inventory / Labels"].map((label, index) => <li className={index === current ? "active" : index < current ? "done" : ""} key={label}><span>{index + 1}</span>{label}</li>)}</ol>;
}
