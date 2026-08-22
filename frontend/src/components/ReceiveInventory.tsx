import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { InventoryReceipt, ProductOption } from "../types/inventory";
import { StreamlitDialog } from "./StreamlitPrimitives";

const empty: InventoryReceipt = { product_id: "", package_id: "", lot_code: "", quantity: 0, unit: "g", location: "RECEIVING", source_name: "", manifest_reference: "", lab_testing_state: "TestPassed", coa_reference: "", notes: "" };

export function ReceiveInventory({ operation, onClose }: { operation: "retail" | "production"; onClose: () => void }) {
  const [form, setForm] = useState(empty);
  const products = useQuery({ queryKey: ["inventory-products"], queryFn: ({ signal }) => apiGet<ProductOption[]>("/api/v1/inventory/products", signal) });
  const queryClient = useQueryClient();
  const receive = useMutation({ mutationFn: () => apiPost(`/api/v1/inventory/${operation}/receipts`, form), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["inventory"] }); onClose(); } });
  const update = (key: keyof InventoryReceipt, value: string | number) => setForm(current => ({ ...current, [key]: value }));
  return <StreamlitDialog title="Receive inventory" subtitle={`${operation} receiving`} onClose={onClose}>
    <div className="form-grid">
      <label className="span-2">Product<select value={form.product_id} onChange={e => { const product = products.data?.find(p => p.id === e.target.value); update("product_id", e.target.value); if (product) update("unit", product.base_unit); }}><option value="">Select product…</option>{products.data?.map(p => <option value={p.id} key={p.id}>{p.name} · {p.sku}</option>)}</select></label>
      <label>Package ID<input value={form.package_id} onChange={e => update("package_id", e.target.value)} /></label>
      <label>Internal lot<input value={form.lot_code} onChange={e => update("lot_code", e.target.value)} /></label>
      <label>Quantity<input type="number" min="0" value={form.quantity || ""} onChange={e => update("quantity", Number(e.target.value))} /></label>
      <label>Unit<input value={form.unit} onChange={e => update("unit", e.target.value)} /></label>
      <label>Location<input value={form.location} onChange={e => update("location", e.target.value)} /></label>
      <label>Lab state<select value={form.lab_testing_state} onChange={e => update("lab_testing_state", e.target.value)}><option>TestPassed</option><option>TestingInProgress</option><option>NotSubmitted</option><option>TestFailed</option></select></label>
      <label>Source / supplier<input value={form.source_name} onChange={e => update("source_name", e.target.value)} /></label>
      <label>Manifest / transfer<input value={form.manifest_reference} onChange={e => update("manifest_reference", e.target.value)} /></label>
      <label>COA reference<input value={form.coa_reference} onChange={e => update("coa_reference", e.target.value)} /></label>
      <label>Notes<input value={form.notes} onChange={e => update("notes", e.target.value)} /></label>
    </div>
    {receive.error ? <div className="form-error">{receive.error.message}</div> : null}
    <button className="primary submit" disabled={!form.product_id || !form.quantity || (!form.package_id && !form.lot_code) || receive.isPending} onClick={() => receive.mutate()}>{receive.isPending ? "Receiving…" : "Receive inventory"}</button>
  </StreamlitDialog>;
}
