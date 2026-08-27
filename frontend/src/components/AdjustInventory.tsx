import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { InventoryPackage } from "../types/inventory";
import { StreamlitDialog } from "./StreamlitDialog";

type AdjustmentType = "incremental" | "set_quantity";
type ReasonPayload = {
  reasons: { name: string; requires_note: boolean }[];
  metrc_ready: boolean;
  can_bypass: boolean;
  license_number: string;
};
type AdjustmentResult = {
  transaction_id: string;
  lot_id: string;
  previous_quantity: number;
  delta: number;
  final_quantity: number;
  reserved_quantity: number;
  unit: string;
  reason: string;
  metrc_status: string;
  traceability_transaction_id: string;
};

export function AdjustInventory({ operation, item, onClose }: { operation: "retail" | "production"; item: InventoryPackage; onClose: () => void }) {
  const client = useQueryClient();
  const reasons = useQuery({
    queryKey: ["inventory-adjustment-reasons", operation],
    queryFn: ({ signal }) => apiGet<ReasonPayload>(`/api/v1/inventory/${operation}/adjustment-reasons`, signal),
  });
  const [adjustmentType, setAdjustmentType] = useState<AdjustmentType>("incremental");
  const [quantity, setQuantity] = useState(0);
  const [reason, setReason] = useState("");
  const [reasonNote, setReasonNote] = useState("");
  const [syncToMetrc, setSyncToMetrc] = useState(false);
  const [bypass, setBypass] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!reasons.data || initialized) return;
    setReason(current => current || reasons.data?.reasons[0]?.name || "");
    setSyncToMetrc(Boolean(reasons.data.metrc_ready));
    setInitialized(true);
  }, [initialized, reasons.data]);

  const current = Number(item.on_hand || 0);
  const final = adjustmentType === "incremental" ? current + quantity : quantity;
  const reasonMeta = reasons.data?.reasons.find(row => row.name === reason);
  const noteRequired = Boolean(reasonMeta?.requires_note);
  const invalidFinal = final < 0 || final + 1e-9 < Number(item.reserved || 0);
  const unchanged = Math.abs(final - current) <= 1e-9;
  const canSubmit = reviewed && reason.trim() && !invalidFinal && !unchanged && (!noteRequired || reasonNote.trim());

  const mutation = useMutation({
    mutationFn: () => apiPost<AdjustmentResult>(`/api/v1/inventory/${operation}/adjustments`, {
      lot_id: item.id,
      package_id: item.package_id,
      adjustment_type: adjustmentType,
      quantity,
      reason,
      reason_note: reasonNote,
      sync_to_metrc: syncToMetrc,
      bypass_state_system: bypass,
      reviewed,
    }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["inventory"] });
      await client.invalidateQueries({ queryKey: ["operations-inbox"] });
      onClose();
    },
  });

  return <StreamlitDialog
    open
    onClose={onClose}
    eyebrow="INVENTORY / ADJUST"
    title="Adjust inventory"
    subtitle="Every adjustment requires a reason and is recorded in the inventory adjustment journal."
  >
    {reasons.isLoading ? <div className="state">Loading facility adjustment reasons…</div> : null}
    {reasons.isError ? <div className="state error">{reasons.error.message}</div> : null}
    <label>Package *<select value={item.id} disabled><option value={item.id}>{item.product_name} · {item.package_id}</option></select></label>
    <section className="quantity-summary">
      <span>Physical on hand<strong>{trimQuantity(current)} {item.unit}</strong></span>
      <span>Committed / reserved<strong>{trimQuantity(item.reserved)} {item.unit}</strong></span>
      <span>Available<strong>{trimQuantity(item.available)} {item.unit}</strong></span>
      <span>Final physical quantity<strong>{trimQuantity(final)} {item.unit}</strong></span>
    </section>
    {item.reservation_sources.length ? <p className="source-caption">Reserved for: {item.reservation_sources.join(" · ")}</p> : null}

    <fieldset className="segmented-field">
      <legend>Adjustment type *</legend>
      <div className="grain-control" role="group" aria-label="Adjustment type">
        <button type="button" className={adjustmentType === "incremental" ? "active" : ""} onClick={() => { setAdjustmentType("incremental"); setQuantity(0); setReviewed(false); }}>Incremental</button>
        <button type="button" className={adjustmentType === "set_quantity" ? "active" : ""} onClick={() => { setAdjustmentType("set_quantity"); setQuantity(current); setReviewed(false); }}>Set Quantity</button>
      </div>
    </fieldset>

    <label>{adjustmentType === "incremental" ? "Change (+ / -) *" : "New physical quantity *"}<input type="number" min={adjustmentType === "set_quantity" ? 0 : undefined} step="0.1" value={quantity} onChange={event => { setQuantity(Number(event.target.value)); setReviewed(false); }}/></label>
    <p className="source-caption">Final physical quantity: {trimQuantity(final)} {item.unit}</p>

    <label>Reason *<select value={reason} onChange={event => { setReason(event.target.value); setReviewed(false); }}>{reasons.data?.reasons.map(row => <option value={row.name} key={row.name}>{row.name}</option>)}</select></label>
    <label>{noteRequired ? "Reason note *" : "Reason note"}<textarea value={reasonNote} onChange={event => { setReasonNote(event.target.value); setReviewed(false); }}/></label>

    <label className="toggle"><input type="checkbox" checked={syncToMetrc} disabled={!reasons.data?.metrc_ready || bypass} onChange={event => { setSyncToMetrc(event.target.checked); if (event.target.checked) setBypass(false); setReviewed(false); }}/>Sync adjustment to Metrc</label>
    <p className="source-caption">When enabled, DoobieLogic submits the package adjustment to Metrc before posting the local inventory change.</p>
    <label className="toggle"><input type="checkbox" checked={bypass} disabled={!reasons.data?.can_bypass} onChange={event => { setBypass(event.target.checked); if (event.target.checked) setSyncToMetrc(false); setReviewed(false); }}/>Bypass state system</label>
    {bypass ? <div className="warning-banner">This changes DoobieLogic only. Use bypass only when the state system has already been handled separately.</div> : null}
    {reasons.data && !reasons.data.metrc_ready ? <div className="info-banner">No complete Metrc connection is available for this user/facility. This adjustment will be local only.</div> : null}
    {reasons.data?.metrc_ready && reasons.data.license_number ? <p className="source-caption">Active facility license: {reasons.data.license_number}</p> : null}

    {invalidFinal ? <div className="form-error">Final physical quantity cannot be negative or below {trimQuantity(item.reserved)} currently committed or reserved.</div> : null}
    {noteRequired && !reasonNote.trim() ? <div className="form-error">This adjustment reason requires a note.</div> : null}
    <label className="toggle"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)}/>I reviewed the package, final physical quantity, active commitments, and adjustment reason.</label>
    {mutation.isError ? <div className="form-error">{mutation.error.message}</div> : null}
    {mutation.data ? <div className="success-banner">Adjusted {item.package_id} by {signed(mutation.data.delta)} {mutation.data.unit} · final {trimQuantity(mutation.data.final_quantity)}. {mutation.data.metrc_status === "synced" ? "Metrc accepted and the local ledger is verified." : ""}</div> : null}
    <button className="primary submit" type="button" disabled={!canSubmit || mutation.isPending || reasons.isLoading || reasons.isError} onClick={() => mutation.mutate()}>{mutation.isPending ? "Adjusting inventory…" : "Adjust inventory"}</button>
  </StreamlitDialog>;
}

function trimQuantity(value: number) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 });
}
function signed(value: number) {
  const number = Number(value || 0);
  return `${number >= 0 ? "+" : ""}${trimQuantity(number)}`;
}
