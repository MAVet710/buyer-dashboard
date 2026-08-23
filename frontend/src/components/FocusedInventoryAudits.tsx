import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "../lib/api";
import type { AuditSummary, InventoryResponse } from "../types/inventory";
import { InventoryAudits } from "./InventoryAudits";

type Operation = "retail" | "production";
type FocusSelection = { product_id: string; sku: string; product_name: string; lot_id?: string };
type Focus = { operation: Operation; selections: FocusSelection[] };

function currentOperation(): Operation {
  return localStorage.getItem("buyer-dash-operation") === "Production Ops" ? "production" : "retail";
}

function normalizeSelection(value: unknown): FocusSelection | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Partial<FocusSelection>;
  if (!row.product_id && !row.lot_id) return null;
  return {
    product_id: String(row.product_id ?? ""),
    sku: String(row.sku ?? ""),
    product_name: String(row.product_name ?? ""),
    lot_id: row.lot_id ? String(row.lot_id) : undefined,
  };
}

function readFocus(): Focus | null {
  try {
    const raw = sessionStorage.getItem("buyer-dash-audit-product-focus");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;

    // Current format: operation + exact selected rows. Keep support for the
    // earlier Product 360 object and Inventory multi-select array so existing
    // sessions do not lose their intended audit scope during the migration.
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && "selections" in parsed) {
      const payload = parsed as { operation?: string; selections?: unknown[] };
      const selections = (payload.selections ?? []).map(normalizeSelection).filter((row): row is FocusSelection => Boolean(row));
      if (!selections.length) return null;
      return { operation: payload.operation === "production" ? "production" : "retail", selections };
    }
    if (Array.isArray(parsed)) {
      const selections = parsed.map(normalizeSelection).filter((row): row is FocusSelection => Boolean(row));
      return selections.length ? { operation: currentOperation(), selections } : null;
    }
    const legacy = normalizeSelection(parsed);
    return legacy ? { operation: currentOperation(), selections: [legacy] } : null;
  } catch {
    return null;
  }
}

function auditNumber(operation: Operation) {
  const now = new Date();
  const part = (value: number) => String(value).padStart(2, "0");
  const prefix = operation === "production" ? "PRO" : "RTL";
  return `${prefix}-${now.getFullYear()}${part(now.getMonth() + 1)}${part(now.getDate())}-${part(now.getHours())}${part(now.getMinutes())}${part(now.getSeconds())}`;
}

export function FocusedInventoryAudits() {
  const client = useQueryClient();
  const [focus, setFocus] = useState<Focus | null>(() => readFocus());
  const operation = focus?.operation ?? currentOperation();
  const [number, setNumber] = useState(() => auditNumber(operation));
  const [blind, setBlind] = useState(true);
  const [tolerance, setTolerance] = useState(0);

  useEffect(() => {
    setNumber(auditNumber(operation));
  }, [operation]);

  const inventory = useQuery({
    queryKey: ["audit-focus-inventory", operation, focus?.selections],
    enabled: Boolean(focus?.selections.length),
    queryFn: ({ signal }) => apiGet<InventoryResponse>(`/api/v1/inventory/${operation}/packages?view=all`, signal),
  });

  const lots = useMemo(() => {
    const items = inventory.data?.items ?? [];
    if (!focus) return [];
    const explicitLots = new Set(focus.selections.map(row => row.lot_id).filter(Boolean));
    const products = new Set(focus.selections.map(row => row.product_id).filter(Boolean));
    return items.filter(row => explicitLots.size ? explicitLots.has(row.id) : products.has(row.product_id));
  }, [focus, inventory.data?.items]);

  const focusLabel = useMemo(() => {
    if (!focus) return "Focused inventory";
    if (focus.selections.length === 1) {
      const row = focus.selections[0];
      return row.product_name || row.sku || row.product_id || row.lot_id || "Focused inventory";
    }
    return `${focus.selections.length} selected inventory rows`;
  }, [focus]);

  const create = useMutation({
    mutationFn: () => apiPost<AuditSummary>(`/api/v1/inventory/${operation}/audits`, {
      audit_number: number,
      scope_label: focus?.selections.length === 1 ? `Product: ${focusLabel}` : `Selected inventory: ${focusLabel}`,
      notes: `Started from ${operation === "production" ? "Production" : "Retail"} Inventory audit focus`,
      lot_ids: lots.map(row => row.id),
      blind_count: blind,
      recount_tolerance: tolerance,
    }),
    onSuccess: async () => {
      sessionStorage.removeItem("buyer-dash-audit-product-focus");
      setFocus(null);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["audits", operation] }),
        client.invalidateQueries({ queryKey: ["audit-inventory", operation] }),
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
      <div className="eyebrow">{operation === "production" ? "PRODUCTION INVENTORY / AUDIT FOCUS" : "PRODUCT 360 / AUDIT FOCUS"}</div>
      <h3>{focus.selections.length === 1 ? "Audit this SKU" : "Audit selected inventory"}</h3>
      <p><strong>{focusLabel}</strong></p>
      {inventory.isLoading ? <div className="state">Loading the selected facility inventory…</div> : null}
      {inventory.isError ? <div className="state error">{inventory.error.message}</div> : null}
      {inventory.data ? <>
        <p className="section-note">{lots.length.toLocaleString()} package / lot row(s) in this {operation} facility will be selected. Other inventory is not included in this focused audit.</p>
        <div className="form-grid two">
          <label>Audit name / number<input value={number} onChange={event => setNumber(event.target.value)} /></label>
          <label>Recount tolerance<input type="number" min="0" step="0.1" value={tolerance} onChange={event => setTolerance(Number(event.target.value))} /></label>
        </div>
        <label className="toggle"><input type="checkbox" checked={blind} onChange={event => setBlind(event.target.checked)} />Blind first count</label>
        <div className="heading-actions">
          <button className="secondary" type="button" onClick={() => { sessionStorage.removeItem("buyer-dash-audit-product-focus"); setFocus(null); }}>Clear inventory focus</button>
          <button className="primary" type="button" disabled={!number.trim() || !lots.length || create.isPending} onClick={() => create.mutate()}>{create.isPending ? "Starting…" : "Start focused audit"}</button>
        </div>
        {create.isError ? <div className="form-error">We couldn&apos;t start the focused audit: {create.error.message}</div> : null}
      </> : null}
    </section> : null}
    <InventoryAudits operation={operation} />
  </>;
}
