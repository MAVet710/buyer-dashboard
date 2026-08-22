import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiPost } from "../lib/api";
import type { InventoryAdjustment, InventoryPackage } from "../types/inventory";
import { StreamlitDialog } from "./StreamlitPrimitives";

const reasons = ["Inventory count correction", "Scale variance", "Damage / destruction", "Waste / disposal", "Found inventory", "Entry error", "Other"];

export function AdjustInventory({ operation, item, onClose }: { operation: "retail" | "production"; item: InventoryPackage; onClose: () => void }) {
  const [form, setForm] = useState<InventoryAdjustment>({ lot_id: item.id, adjustment_type: "incremental", quantity: 0, reason: reasons[0], reason_note: "" });
  const client = useQueryClient();
  const mutation = useMutation({ mutationFn: () => apiPost(`/api/v1/inventory/${operation}/adjustments`, form), onSuccess: async () => { await client.invalidateQueries({ queryKey: ["inventory"] }); onClose(); } });
  const final = form.adjustment_type === "incremental" ? item.available + form.quantity : form.quantity;
  return <StreamlitDialog title="Adjust package" subtitle="Inventory control" onClose={onClose} size="compact">
    <p className="dialog-context">{item.product_name} · {item.package_id}</p>
    <div className="quantity-summary"><span>Current<strong>{item.available.toLocaleString()} {item.unit}</strong></span><span>Reserved<strong>{item.reserved.toLocaleString()} {item.unit}</strong></span><span>Final<strong>{final.toLocaleString()} {item.unit}</strong></span></div>
    <div className="form-grid">
      <label>Adjustment type<select value={form.adjustment_type} onChange={e => setForm({ ...form, adjustment_type: e.target.value as InventoryAdjustment["adjustment_type"], quantity: 0 })}><option value="incremental">Incremental (+ / −)</option><option value="set_quantity">Set quantity</option></select></label>
      <label>{form.adjustment_type === "incremental" ? "Quantity change" : "New quantity"}<input type="number" step="0.01" value={form.quantity} onChange={e => setForm({ ...form, quantity: Number(e.target.value) })} /></label>
      <label className="span-2">Reason<select value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })}>{reasons.map(reason => <option key={reason}>{reason}</option>)}</select></label>
      <label className="span-2">Reason note<input value={form.reason_note} onChange={e => setForm({ ...form, reason_note: e.target.value })} /></label>
    </div>
    {mutation.error ? <div className="form-error">{mutation.error.message}</div> : null}
    <button className="primary submit" disabled={final < item.reserved || final < 0 || mutation.isPending || (form.adjustment_type === "incremental" && form.quantity === 0) || (form.adjustment_type === "set_quantity" && form.quantity === item.available)} onClick={() => mutation.mutate()}>{mutation.isPending ? "Posting adjustment…" : "Post adjustment"}</button>
  </StreamlitDialog>;
}
