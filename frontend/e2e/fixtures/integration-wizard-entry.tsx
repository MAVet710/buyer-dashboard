import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { IntegrationWizardPage } from "../../src/pages/IntegrationWizardPage";
import { IntegrationsPage } from "../../src/pages/IntegrationsPage";
import { ImplementationReadinessPage } from "../../src/pages/ImplementationReadinessPage";
import { ScheduledReportsPage } from "../../src/pages/ScheduledReportsPage";
import "../../src/styles.css";
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
export function Fixture() {
  const [page, setPage] = useState("Implementation Readiness");
  return <><nav><button onClick={() => setPage("Implementation Readiness")}>Readiness</button><button onClick={() => setPage("Scheduled Reports")}>Reports</button></nav>{page === "Scheduled Reports" ? <ScheduledReportsPage /> : page.startsWith("/work?") ? <p role="status">Linked work: {page}</p> : page === "Integration Wizard" ? <IntegrationWizardPage onNavigate={setPage} /> : page.startsWith("/settings/integrations") || page === "Integrations" ? <IntegrationsPage onNavigate={setPage} initialProvider="metrc" /> : <ImplementationReadinessPage onNavigate={setPage} />}</>;
}
createRoot(document.getElementById("root")!).render(<React.StrictMode><QueryClientProvider client={client}><Fixture /></QueryClientProvider></React.StrictMode>);
