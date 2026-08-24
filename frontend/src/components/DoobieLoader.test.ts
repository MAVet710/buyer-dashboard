import { describe, expect, it } from "vitest";
import { DOOBIE_LOADER_VARIANTS } from "./DoobieLoader";

describe("DoobieLoader motion pack", () => {
  it("ships exactly fourteen unique loader variants", () => {
    expect(DOOBIE_LOADER_VARIANTS).toHaveLength(14);
    expect(new Set(DOOBIE_LOADER_VARIANTS).size).toBe(14);
  });
});
