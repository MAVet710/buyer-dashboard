import { describe, expect, it } from "vitest";
import { errorMessage } from "./api";

describe("API error contract", () => {
  it("prefers actionable route detail over a generic envelope", () => {
    expect(errorMessage({ detail: "Choose an organization.", error: { message: "Request failed." } }, 422)).toBe("Choose an organization.");
  });

  it("shows FastAPI field validation details instead of hiding them", () => {
    const message = errorMessage({
      detail: [
        { loc: ["body", "facility_ids", 0], msg: "Input should be a valid string" },
        { loc: ["body", "email"], msg: "Value is not a valid email address" },
      ],
      error: { message: "One or more request fields are invalid." },
    }, 422);

    expect(message).toContain("Facility Ids: Input should be a valid string");
    expect(message).toContain("Email: Value is not a valid email address");
    expect(message).not.toBe("One or more request fields are invalid.");
  });

  it("falls back to the stable server error message when detail is unusable", () => {
    expect(errorMessage({ detail: [{ field: "sku" }], error: { message: "Stable message" } }, 422)).toBe("Stable message");
  });
});
