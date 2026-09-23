import { describe, expect, it } from "vitest";
import { labelIndices, labelReprintBlock, validLabelRange } from "./labelReprints";

describe("saved label reprints", () => {
  it("prints only requested replacements using their original numbers", () => {
    expect(labelIndices(24, 2, 7)).toEqual([6, 7]);
    expect(labelIndices(24, 24, 1)).toHaveLength(24);
    expect(labelIndices(24, 1, 24)).toEqual([23]);
  });
  it.each([[24,0,1], [24,2,24], [24,1,0], [24,1.5,1], [24,1,1.5], [24,NaN,1], [24,501,1], [0,1,1]])("rejects invalid ranges %s/%s/%s", (original,copies,first) => {
    expect(validLabelRange(original,copies,first)).toBe(false);
    expect(labelIndices(original,copies,first)).toEqual([]);
  });
  it("explains archived runs instead of asking for a new tag", () => {
    expect(labelReprintBlock("archived")).toContain("read-only");
    expect(labelReprintBlock("archived")).not.toContain("Assign");
    for (const state of ["tagged","printed","applied","released","fulfilled"]) expect(labelReprintBlock(state)).toBe("");
    expect(labelReprintBlock("validated")).toContain("Assign");
  });
});
