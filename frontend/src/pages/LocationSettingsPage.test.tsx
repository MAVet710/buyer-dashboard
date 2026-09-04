import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("./LocationSettingsPage.tsx", import.meta.url), "utf8");

describe("sandbox facility validation controls", () => {
  it("offers explicit validation for a trusted sandbox mapping without collecting keys", () => {
    expect(source).toContain('setup.data.metrc.environment === "sandbox" && setup.data.metrc.trusted_mapping');
    expect(source).toContain('"/api/v1/integrations/metrc/test", {}');
    expect(source).toContain("Validate this sandbox facility");
    expect(source).toContain("onClick={() => validateMetrc.mutate()}");
  });

  it("clears stale live-read errors and explains switching instead of editing the license", () => {
    expect(source).toContain('client.resetQueries({ queryKey: ["facility-setup"] })');
    expect(source).toContain("Switch sandbox facilities using the Facility selector above.");
    expect(source).toContain("A placeholder or unmapped facility must be discovered and linked");
  });
});
