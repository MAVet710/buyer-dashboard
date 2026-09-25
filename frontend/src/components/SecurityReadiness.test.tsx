import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { SecurityReadiness } from "./SecurityReadiness";

vi.mock("../lib/api", () => ({ apiGet: vi.fn() }));

describe("Security Readiness", () => {
  it("renders capability limits without presenting unsupported identity features as configured", () => {
    const client = new QueryClient();
    client.setQueryData(["security-readiness"], {
      scope: "Local configuration only, not a security certification.",
      controls: [
        { key: "mfa", label: "MFA enforcement", status: "unsupported", detail: "App enforcement is not implemented." },
        { key: "encryption", label: "Integration encryption", status: "not_configured", detail: "Server key is missing." },
      ],
    });
    const html = renderToStaticMarkup(<QueryClientProvider client={client}><SecurityReadiness /></QueryClientProvider>);
    expect(html).toContain("Security Readiness");
    expect(html).toContain("not a security certification");
    expect(html).toContain("unsupported");
    expect(html).toContain("not configured");
    expect(html).toContain("App enforcement is not implemented.");
    expect(html).not.toContain("production-ready");
    client.clear();
  });
});
