import { describe, expect, it } from "vitest";
import { isOfflineReplayAllowed } from "./offlineQueue";

describe("offline replay safety policy", () => {
  it("allows explicitly classified local capture endpoints", () => {
    expect(isOfflineReplayAllowed("/api/v1/inventory/audits/123/counts", "physical_capture")).toBe(true);
    expect(isOfflineReplayAllowed("/api/v1/production/drafts", "local_draft")).toBe(true);
  });

  it("blocks regulatory and provider-changing routes", () => {
    const blocked = [
      "/api/v1/traceability/actions",
      "/api/v1/inventory/regulatory",
      "/api/v1/metrc/packages",
      "/api/v1/integrations/metrc",
      "/api/v1/wholesale/manifest/create",
      "/api/v1/transfer/dispatch",
    ];
    for (const path of blocked) {
      expect(isOfflineReplayAllowed(path, "physical_capture")).toBe(false);
    }
  });

  it("rejects non-DoobieLogic API paths", () => {
    expect(isOfflineReplayAllowed("https://example.com/write", "local_draft")).toBe(false);
    expect(isOfflineReplayAllowed("/health", "physical_capture")).toBe(false);
  });
});
