import { describe, expect, it } from "vitest";
import { isMarketingHost } from "./siteMode";

describe("isMarketingHost", () => {
  it("serves the public site on the apex and www hosts", () => {
    expect(isMarketingHost("doobielogic.io")).toBe(true);
    expect(isMarketingHost("www.doobielogic.io")).toBe(true);
    expect(isMarketingHost("DOOBIELOGIC.IO.")).toBe(true);
  });

  it("keeps the secured application on ops and local hosts", () => {
    expect(isMarketingHost("ops.doobielogic.io")).toBe(false);
    expect(isMarketingHost("localhost")).toBe(false);
    expect(isMarketingHost("127.0.0.1")).toBe(false);
  });
});
