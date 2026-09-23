export const STAGED_PO_KEY = "buyer-dash-po-inventory-selection";
export type PurchaseProduct = { product_id: string; sku: string; product_name: string; unit: string; unit_cost: number; suggested_quantity?: number; preferred_vendor_id?: string | null };
export type PurchaseDraftLine = { product_id: string; sku: string; description: string; quantity: number; unit: string; unit_price: number };

export function purchaseDraftSelection(raw: unknown, authorizedProducts: PurchaseProduct[]): { lines: PurchaseDraftLine[]; rejected: number; duplicates: number } {
  if (!Array.isArray(raw) || raw.length > 500) return { lines: [], rejected: Array.isArray(raw) ? raw.length : 1, duplicates: 0 };
  const products = new Map(authorizedProducts.map(product => [product.product_id, product]));
  const seen = new Set<string>();
  const lines: PurchaseDraftLine[] = [];
  let rejected = 0, duplicates = 0;
  for (const value of raw) {
    if (!value || typeof value !== "object") { rejected++; continue; }
    const item = value as Record<string, unknown>;
    const product = products.get(String(item.product_id ?? ""));
    const quantity = Number(item.quantity);
    if (!product || !Number.isFinite(quantity) || quantity <= 0 || (item.unit && item.unit !== product.unit) || !Number.isFinite(product.unit_cost) || product.unit_cost < 0) { rejected++; continue; }
    if (seen.has(product.product_id)) { duplicates++; continue; }
    seen.add(product.product_id);
    // Session storage is a handoff, not an identity, description, unit, or price authority.
    lines.push({ product_id: product.product_id, sku: product.sku, description: product.product_name, quantity, unit: product.unit, unit_price: product.unit_cost });
  }
  return { lines, rejected, duplicates };
}

export function validPurchaseDraft(lines: PurchaseDraftLine[]): boolean {
  return lines.length > 0 && lines.length <= 500 && new Set(lines.map(line => line.product_id)).size === lines.length
    && lines.every(line => Boolean(line.product_id && line.unit) && Number.isFinite(line.quantity) && line.quantity > 0 && Number.isFinite(line.unit_price) && line.unit_price >= 0);
}
