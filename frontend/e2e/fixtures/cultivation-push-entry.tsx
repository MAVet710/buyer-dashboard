import { lazy, Suspense, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "../../src/styles.css";
import "../../src/table-filters.css";
import "../../src/parity.css";
import "../../src/parity-workspaces.css";
import "../../src/streamlit-exact.css";
import "../../src/streamlit-shell.css";
import "../../src/buyer-streamlit.css";
import "../../src/white-label-streamlit.css";
import "../../src/home-streamlit.css";
import "../../src/inventory-receiving.css";
import "../../src/auth-streamlit.css";
import "../../src/brand-image.css";
import "../../src/marketing-home.css";
import "../../src/beta-partner.css";
import "../../src/contact-channels.css";
import "../../src/commerce-storefront.css";
import "../../src/cowboy-storefront.css";
import "../../src/commerce-launcher.css";
import "../../src/offline.css";
import "../../src/popup-surfaces.css";
// Same global CSS order as main.tsx; component CSS arrives after global CSS.
const Connections = lazy(() => import("../../src/components/CultivationConnections").then(module => ({ default: module.CultivationConnections })));
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
localStorage.setItem("buyer-dash-organization", "fixture-org");
localStorage.setItem("buyer-dash-facility", "fixture-a");
export function Fixture() {
  const [scope, setScope] = useState("fixture-a");
  const [cache, setCache] = useState("");
  return <QueryClientProvider client={client}><main className="page"><p>Network-mocked component fixture. No live receiver or release acceptance.</p><button onClick={() => { const next = scope === "fixture-a" ? "fixture-b" : "fixture-a"; localStorage.setItem("buyer-dash-facility", next); setScope(next); }}>Switch fixture facility</button><button onClick={() => setCache(JSON.stringify({ queries: client.getQueryCache().getAll().map(q => ({ key: q.queryKey, data: q.state.data })), mutations: client.getMutationCache().getAll().map(m => m.state.data) }))}>Inspect fixture cache</button><output hidden aria-label="Fixture cache">{cache}</output><Suspense fallback={<p>Loading fixture</p>}><Connections key={scope} /></Suspense></main></QueryClientProvider>;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
