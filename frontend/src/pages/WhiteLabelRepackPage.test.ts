import { describe, expect, it } from "vitest";
import { calculate, formDefaults, planDefaults, whiteLabelReportPayload } from "./whiteLabelRepackParity";

describe("White Label / Repack Streamlit parity", () => {
  it("keeps the canonical gram conversion, loss, allocation, and unit math", () => {
    const form = {
      ...formDefaults(),
      strain_name: "Blue Dream",
      bulk_weight_value: 1,
      bulk_weight_unit: "lb" as const,
      bulk_total_cost_usd: 1000,
      discount_pct: 10,
      freight_or_delivery_cost_usd: 25,
      sample_or_testing_cost_usd: 25,
      shrink_loss_pct: 10,
      trim_loss_pct: 5,
      qa_hold_loss_pct: 5,
      labor_cost_total_usd: 100,
      other_costs_usd: 50,
      compliance_admin_cost_usd: 50,
    };
    const result = calculate(form, planDefaults());

    expect(result.landedCost).toBe(950);
    expect(result.usableWeight).toBeCloseTo(453.59237 * 0.8, 8);
    expect(result.allocationTotal).toBe(100);
    expect(result.totalUnits).toBe(67);
    expect(result.rows).toHaveLength(4);
    expect(result.rows.every(row => row.status === "Complete")).toBe(true);
    expect(result.rows.map(row => row.size)).toEqual(["3.5g", "7g", "14g", "28g"]);
  });

  it("preserves missing-input readiness and the original report payload shape", () => {
    const form = { ...formDefaults(), strain_name: "Test Lot", bulk_weight_value: 100 };
    const result = calculate(form, planDefaults());
    const payload = whiteLabelReportPayload("Current Session", form, planDefaults(), result);

    expect(result.readiness.incomplete_rows).toBe(4);
    expect(result.rows.every(row => row.missing.includes("Bulk cost missing"))).toBe(true);
    expect(payload.package_output_summary[0]["Product Name"]).toBe("Test Lot Flower 3.5g");
    expect(payload.cost_breakdown.map(row => row["Cost Type"])).toEqual(["Landed Cost", "Packaging+Label", "Labor"]);
    expect(payload.compliance_checklist).toHaveLength(11);
  });
});
