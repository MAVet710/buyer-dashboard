import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthGate } from "./components/AuthGate";
import { AppSupportButton, MarketingContactChannels } from "./components/ContactChannels";
import { MarketingHome } from "./pages/MarketingHome";
import { BetaPartnerPage } from "./pages/BetaPartnerPage";
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
import "./brand-image.css";
import "./marketing-home.css";
import "./beta-partner.css";
import "./contact-channels.css";

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } });
const marketing = isMarketingHost(window.location.hostname);
const betaPage = marketing && /^\/beta\/?$/.test(window.location.pathname);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      {marketing ? <>
        {betaPage ? <BetaPartnerPage /> : <MarketingHome />}
        <MarketingContactChannels />
      </> : <AuthGate><>
        <App />
        <AppSupportButton />
      </></AuthGate>}
    </QueryClientProvider>
  </StrictMode>,
);
