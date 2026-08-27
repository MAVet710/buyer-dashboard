import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthGate } from "./components/AuthGate";
import { AppSupportButton, MarketingContactChannels } from "./components/ContactChannels";
import { MarketingHome } from "./pages/MarketingHome";
import { BetaPartnerPage } from "./pages/BetaPartnerPage";
import { CommercePortalPage } from "./pages/CommercePortalPage";
import { configureSeo } from "./lib/seo";
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
configureSeo(marketing);
const betaPage = marketing && /^\/beta\/?$/.test(window.location.pathname);
const portalMatch = window.location.pathname.match(/^\/portal\/([^/]+)\/?$/);
const portalToken = portalMatch ? decodeURIComponent(portalMatch[1]) : "";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      {portalToken ? <CommercePortalPage token={portalToken} /> : marketing ? <>
        {betaPage ? <BetaPartnerPage /> : <MarketingHome />}
        <MarketingContactChannels />
      </> : <AuthGate>
        <BrowserRouter>
          <>
            <App />
            <AppSupportButton />
          </>
        </BrowserRouter>
      </AuthGate>}
    </QueryClientProvider>
  </StrictMode>,
);
