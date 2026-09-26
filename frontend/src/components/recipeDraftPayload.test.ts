import { describe, expect, it } from "vitest";
import { recipeDraftPayload } from "./recipeDraftPayload";

const returnedStage = {
  id: "immutable-stage", stage_key: "facility-stage", display_name: "Facility stage", sequence: 4,
  targets: [{ id: "immutable-target", metric: "temperature", minimum: 20, maximum: 24,
    unit: "C", threshold_seconds: 900, alert_threshold_status: "configured" }],
};

describe("recipe draft contract", () => {
  it("copies approved standards without resubmitting derived fields or immutable IDs", () => {
    const before = JSON.stringify(returnedStage);
    const draft = recipeDraftPayload("Facility recipe", "New version", [returnedStage]);
    expect(draft).toEqual({ name: "Facility recipe", description: "New version", stages: [{
      stage_key: "facility-stage", display_name: "Facility stage", sequence: 0,
      targets: [{ metric: "temperature", minimum: 20, maximum: 24, unit: "C", threshold_seconds: 900 }],
    }] });
    expect(JSON.stringify(returnedStage)).toBe(before);
  });
  it("leaves an absent facility alert duration unconfigured", () => {
    const stage = { ...returnedStage, targets: [{ metric: "temperature", minimum: null, maximum: 24, unit: "C" }] };
    expect(recipeDraftPayload("Name", "", [stage]).stages[0].targets[0].threshold_seconds).toBeNull();
  });
});
