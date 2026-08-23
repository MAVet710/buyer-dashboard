import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { InventoryReceipt, ProductOption } from "../types/inventory";
import { StreamlitDialog } from "./StreamlitDialog";

type ReceiptResult = { lot_id: string; transaction_id: string; operation: "production"; status: string };

export function ProductionReceiveInventory({ onClose, onReceived }: { onClose: () => void; onReceived: (message: string) => void }) {
  const client = useQueryClient();
  const products = useQuery({ queryKey: ["inventory-products"], queryFn: ({ signal }) => apiGet<ProductOption[]>("/api/v1/inventory/products", signal) });
  const [productId, setProductId] = useState("");
  const selected = products.data?.find(product => product.id === productId);
  const [packageId, setPackageId] = useState("");
  const [lotCode, setLotCode] = useState("");
  const [quantity, setQuantity] = useState(0);
  const [unit, setUnit] = useState("");
  const [location, setLocation] = useState("RECEIVING");
  const [sourceName, setSourceName] = useState("");
  const [manifest, setManifest] = useState("");
  const [notes, setNotes] = useState("");

  const unitOptions = useMemo(() => Array.from(new Set([selected?.base_unit || "", "g", "kg", "oz", "lb", "unit"].filter(Boolean))), [selected?.base_unit]);
  const receipt: InventoryReceipt = {
    product_id: productId,
    package_id: packageId.trim(),
    lot_code: lotCode.trim() || packageId.trim(),
    quantity,
    unit: unit || selected?.base_unit || "unit",
    location: location.trim() || "RECEIVING",
    source_name: sourceName.trim(),
    manifest_reference: manifest.trim(),
    lab_testing_state: "TestPassed",
    coa_reference: "",
    notes: notes.trim(),
  };

  const receive = useMutation({
    mutationFn: () => apiPost<ReceiptResult>("/api/v1/inventory/production/receipts", receipt),
    onSuccess: async result => {
      await client.invalidateQueries({ queryKey: ["inventory"] });
      await client.invalidateQueries({ queryKey: ["inventory-receive-history", "production"] });
      onReceived(`Received material into production inventory · lot ${result.lot_id}`);
      onClose();
    },
  });

  return <StreamlitDialog open onClose={onClose} eyebrow="PRODUCTION / CULTIVATION RECEIVING" title="Receive material" subtitle="Posts only to the active facility/license inventory. Retail inventory is never modified.">
    {products.isLoading ? <div className="state">Loading Product Master materials…</div> : null}
    {products.isError ? <div className="state error">{products.error.message}</div> : null}
    {!products.isLoading && !products.isError && !products.data?.length ? <div className="warning-banner">Create the material in Product Master before receiving it.</div> : null}
    {products.data?.length ? <>
      <label>Material / product<select value={productId} onChange={event => { const value = event.target.value; const product = products.data?.find(item => item.id === value); setProductId(value); setUnit(product?.base_unit || "unit"); }}><option value="">Select material…</option>{products.data.map(product => <option value={product.id} key={product.id}>{product.name} · {product.sku}</option>)}</select></label>
      <div className="form-grid two">
        <label>METRC package ID<input value={packageId} onChange={event => { const value = event.target.value; setPackageId(value); if (!lotCode.trim()) setLotCode(value); }}/></label>
        <label>Internal lot / batch<input value={lotCode} onChange={event => setLotCode(event.target.value)} title="Defaults to the METRC package ID when the internal lot is not different."/></label>
      </div>
      <div className="form-grid">
        <label>Quantity<input type="number" min="0" step="1" value={quantity || ""} onChange={event => setQuantity(Number(event.target.value))}/></label>
        <label>Unit<select value={unit || selected?.base_unit || "unit"} onChange={event => setUnit(event.target.value)}>{unitOptions.map(value => <option value={value} key={value}>{value}</option>)}</select></label>
        <label>Room / location<input value={location} onChange={event => setLocation(event.target.value)}/></label>
        <label>Source facility / supplier<input value={sourceName} onChange={event => setSourceName(event.target.value)}/></label>
        <label>Manifest / transfer #<input value={manifest} onChange={event => setManifest(event.target.value)}/></label>
        <label className="span-2">Notes<textarea value={notes} onChange={event => setNotes(event.target.value)}/></label>
      </div>
      {receive.isError ? <div className="state error">{receive.error.message}</div> : null}
      <button className="primary submit" type="button" disabled={!productId || quantity <= 0 || (!packageId.trim() && !lotCode.trim()) || receive.isPending} onClick={() => receive.mutate()}>{receive.isPending ? "Receiving material…" : "Receive material"}</button>
    </> : null}
  </StreamlitDialog>;
}
