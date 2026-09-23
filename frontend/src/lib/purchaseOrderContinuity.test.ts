import { describe, expect, it } from "vitest";
import { purchaseDraftSelection, validPurchaseDraft, type PurchaseProduct } from "./purchaseOrderContinuity";

const products: PurchaseProduct[] = [{ product_id: "product-one", sku: "ONE", product_name: "Canonical product", unit: "unit", unit_cost: 12.5 }];

describe("inventory to durable purchase-order continuity", () => {
  it("carries quantity and resolves identity, unit and cost from authorized products", () => {
    const result = purchaseDraftSelection([{ product_id: "product-one", quantity: 3, price: 999, description: "Untrusted snapshot", sku: "OTHER" }], products);
    expect(result.lines).toEqual([{ product_id: "product-one", quantity: 3, unit: "unit", unit_price: 12.5, description: "Canonical product", sku: "ONE" }]);
    expect(result.rejected).toBe(0);
    expect(validPurchaseDraft(result.lines)).toBe(true);
  });
  it("does not silently multiply quantities for duplicate package selections", () => {
    const result = purchaseDraftSelection([{product_id:"product-one",quantity:3},{product_id:"product-one",quantity:3}], products);
    expect(result.lines).toHaveLength(1);
    expect(result.lines[0].quantity).toBe(3);
    expect(result.duplicates).toBe(1);
  });
  it("rejects unknown products, incompatible units, and invalid quantities", () => {
    const result = purchaseDraftSelection([{product_id:"other-facility",quantity:3},{product_id:"product-one",quantity:0},{product_id:"product-one",quantity:NaN},{product_id:"product-one",quantity:3,unit:"g"}],products);
    expect(result.lines).toEqual([]);
    expect(result.rejected).toBe(4);
  });
  it("rejects oversized or malformed handoffs", () => {
    expect(purchaseDraftSelection(null,products).lines).toEqual([]);
    expect(purchaseDraftSelection(new Array(501).fill({product_id:"product-one",quantity:1}),products).lines).toEqual([]);
  });
  it("validates final editable quantities and prices without trusting stored totals", () => {
    const line = purchaseDraftSelection([{product_id:"product-one",quantity:3}],products).lines[0];
    expect(validPurchaseDraft([])).toBe(false);
    expect(validPurchaseDraft([line,line])).toBe(false);
    expect(validPurchaseDraft([{...line,quantity:Infinity}])).toBe(false);
    expect(validPurchaseDraft([{...line,unit_price:-1}])).toBe(false);
    expect(validPurchaseDraft([{...line,unit_price:0}])).toBe(true);
  });
});
