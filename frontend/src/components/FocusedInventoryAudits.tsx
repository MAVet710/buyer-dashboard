import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { AuditSummary, InventoryResponse } from "../types/inventory";
import { InventoryAudits } from "./InventoryAudits";

type Focus = { product_id: string; sku: string; product_name: string };

function readFocus(): Focus | null {
  try {
    const raw = sessionStorage.getItem("buyer-dash-audit-product-focus");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Focus>;
    return parsed.product_id
      ? { product_id: String(parsed.product_id), sku: String(parsed.sku ?? ""), product_name: String(parsed.product_name ?? "") }
      : null;
  } catch {
    return null;
  }
}

function auditNumber() {
  const now = new Date();
  const part = (value: number) => String(value).padStart(2, "0");
  return `RTL-${now.getFullYear()}${part(now.getMonth() + 1)}${part(now.getDate())}-${part(now.getHours())}${part(now.getMinutes())}${part(now.getSeconds())}`;
}

export function FocusedInventoryAudits() {
  const client = useQueryClient();
  const [focus, setFocus] = useState<Focus | null>(() => readFocus());
  const [number, setNumber] = useState(() => auditNumber());
  const [blind, setBlind] = useState(true);
  const [tolerance, setTolerance] = useState(0);
  const inventory = useQuery({
    queryKey: ["audit-focus-inventory", focus?.product_id],
    enabled: Boolean(focus?.product_id),
    queryFn: ({ signal }) => apiGet<InventoryResponse>("/api/v1/inventory/retail/packages?view=all", signal),
  });
  const lots = useMemo(
    () => (inventory.data?.items ?? []).filter(row => row.product_id === focus?.product_id),
    [focus?.product_id, inventory.data?.items],
  );
  const create = useMutation({
    mutationFn: () => apiPost<AuditSummary>("/api/v1/inventory/retail/audits", {
      audit_number: number,
      scope_label: `Product: ${focus?.product_name || focus?.sku || focus?.product_id}`,
      notes: `Started from Product 360 audit focus${focus?.sku ? ` · ${focus.sku}` : ""}`,
      lot_ids: lots.map(row => row.id),
      blind_count: blind,
      recount_tolerance: tolerance,
    }),
    onSuccess: async () => {
      sessionStorage.removeItem("buyer-dash-audit-product-focus");
      setFocus(null);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["audits", "retail"] }),
        client.invalidateQueries({ queryKey: ["audit-inventory", "retail"] }),
      ]);
    },
  });

  useEffect(() => {
    const sync = () => setFocus(readFocus());
    window.addEventListener("pageshow", sync);
    return () => window.removeEventListener("pageshow", sync);
  }, []);

  return <>
    {focus ? <section className="inventory-panel audit-focus-panel">
      <div className="eyebrow">PRODUCT 360 / AUDIT FOCUS</div>
      <h3>Audit this SKU</h3>
      <p><strong>{focus.product_name || "Focused product"}</strong>{focus.sku ? ` · ${focus.sku}` : ""}</p>
      {inventory.isLoading ? <div className="state">Loading this product&apos;s facility inventory…</div> : null}
      {inventory.isError ? <div className="state error">{inventory.error.message}</div> : null}
      {inventory.data ? <>
        <p className="section-note">{lots.length.toLocaleString()} package / lot row(s) in this retail facility will be selected. Other inventory is not included in this focused audit.</p>
        <div className="form-grid two">
          <label>Audit name / number<input value={number} onChange={event => setNumber(event.target.value)} /></label>
          <label>Recount tolerance<input type="number" min="0" step="0.1" value={tolerance} onChange={event => setTolerance(Number(event.target.value))} /></label>
        </div>
        <label className="toggle"><input type="checkbox" checked={blind} onChange={event => setBlind(event.target.checked)} />Blind first count</label>
        <div className="heading-actions">
          <button className="secondary" type="button" onClick={() => { sessionStorage.removeItem("buyer-dash-audit-product-focus"); setFocus(null); }}>Clear product focus</button>
          <button className="primary" type="button" disabled={!number.trim() || !lots.length || create.isPending} onClick={() => create.mutate()}>{create.isPending ? "Starting…" : "Start focused audit"}</button>
        </div>
        {create.isError ? <div className="form-error">We couldn&apos;t start the focused audit: {create.error.message}</div> : null}
      </> : null}
    </section> : null}
    <InventoryAudits operation="retail" />
  </>;
}
