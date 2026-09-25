import { describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { IntegrationWizardPage, type WizardData } from "./IntegrationWizardPage";
import { pageForPath, pathForPage } from "../lib/workspaceRoutes";

const data: WizardData = {
  facility: { id: "one", name: "Facility One", license_number: "TEST-LICENSE", license_type: "Processor", capabilities: ["production"] },
  mode: { effective_mode: "metrc_sandbox", message: "Sandbox only" }, step: "summary", can_manage: true,
  items: [{ key: "metrc", label: "Metrc", required: true, status: "needs_mapping", evidence: "Verify the exact facility mapping", environment: "sandbox", last_validated_at: null, test_path: "/api/v1/integrations/metrc/test", settings_path: "/settings/integrations?provider=metrc", mapping_route: "Integrations", managed_entities: [], manual_mapping_required: [] }],
};
function render(value = data) {
  const client = new QueryClient();
  client.setQueryData(["integration-wizard"], value);
  return renderToStaticMarkup(<QueryClientProvider client={client}><IntegrationWizardPage onNavigate={() => {}} /></QueryClientProvider>);
}
describe("Integration Wizard", () => {
  it("routes wizard and provider deep links", () => {
    expect(pathForPage("Integration Wizard")).toBe("/settings/integration-wizard");
    expect(pageForPath("/settings/integration-wizard")).toBe("Integration Wizard");
    expect(pageForPath(data.items[0].settings_path)).toBe("Integrations");
  });
  it("resumes the durable step and displays evidence rather than completion", () => {
    const html = render();
    expect(html).toContain("Readiness summary</h2>");
    expect(html).toContain("1 required provider(s) remain incomplete");
    expect(html).toContain("Needs mapping");
    expect(html).toContain("Sandbox validation is not production acceptance");
    expect(html).not.toContain('type="password"');
  });
  it("readers have no mutation actions", () => {
    expect(render({ ...data, can_manage: false })).not.toContain("Test / Validate Metrc");
  });
  it("shows optional skip and all final state names honestly", () => {
    for (const [status, label] of Object.entries({ connected: "Connected", needs_validation: "Needs validation", needs_mapping: "Needs mapping", optional_skipped: "Optional skipped", not_applicable: "Not applicable", blocked: "Blocked" })) {
      expect(render({ ...data, items: [{ ...data.items[0], status }] })).toContain(label);
    }
    const html = render({ ...data, step: "systems", items: [{ ...data.items[0], key: "quickbooks", label: "QuickBooks", required: false, status: "optional_skipped" }] });
    expect(html).toContain("Optional skipped");
    expect(html).toContain("Include QuickBooks");
    expect(html).not.toContain("Test / Validate QuickBooks");
  });
});
