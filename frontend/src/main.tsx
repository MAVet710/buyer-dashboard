import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthGate } from "./components/AuthGate";
import { MarketingHome } from "./pages/MarketingHome";
import { isMarketingHost } from "./lib/siteMode";
import "./styles.css";
import "./parity.css";
import "./parity-workspaces.css";
import "./streamlit-exact.css";
import "./streamlit-shell.css";
import "./buyer-streamlit.css";
import "./white-label-streamlit.css";
import "./home-streamlit.css";
import "./inventory-receiving.css";
import "./auth-streamlit.css";
import "./marketing-home.css";

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } });
const marketing = isMarketingHost(window.location.hostname);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      {marketing ? <MarketingHome /> : <AuthGate><App /></AuthGate>}
    </QueryClientProvider>
  </StrictMode>,
);
