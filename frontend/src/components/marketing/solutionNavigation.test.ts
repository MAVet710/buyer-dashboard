import { describe, expect, it, vi } from "vitest";
import { replaceSolutionHash } from "./solutionNavigation";

describe("homepage operation navigation", () => {
  it.each(["cultivation", "production", "retail", "vertical"])(
    "preserves the complete browser history state for %s",
    (id) => {
      const state = { idx: 4, key: "existing-entry", usr: { source: "homepage" } };
      const replaceState = vi.fn();
      replaceSolutionHash(id, { state, replaceState });
      expect(replaceState).toHaveBeenCalledExactlyOnceWith(state, "", `#solution-${id}`);
      expect(replaceState.mock.calls[0][0]).toBe(state);
    },
  );

  it("preserves a null history state rather than fabricating router metadata", () => {
    const replaceState = vi.fn();
    replaceSolutionHash("retail", { state: null, replaceState });
    expect(replaceState).toHaveBeenCalledExactlyOnceWith(null, "", "#solution-retail");
  });

  it("keeps special characters inside the hash value", () => {
    const replaceState = vi.fn();
    replaceSolutionHash("a/b?c", { state: null, replaceState });
    expect(replaceState).toHaveBeenCalledExactlyOnceWith(null, "", "#solution-a%2Fb%3Fc");
  });
});
