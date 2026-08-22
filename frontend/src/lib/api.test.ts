import { describe, expect, it } from "vitest";
import { errorMessage } from "./api";

describe("API error contract", () => {
  it("prefers the stable server error message", () => {
    expect(errorMessage({ detail: "legacy", error: { message: "Stable message" } }, 422)).toBe("Stable message");
  });
  it("does not stringify structured validation details", () => {
    expect(errorMessage({ detail: [{ field: "sku" }] }, 422)).toBe("Request failed (422)");
  });
});
