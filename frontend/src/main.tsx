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
import { StorefrontPage } from "./pages/StorefrontPage";
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
import "./commerce-storefront.css";

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } });
const hostname = window.location.hostname.trim().toLowerCase().replace(/\.$/, "");
const marketing = isMarketingHost(hostname);
configureSeo(marketing);
const betaPage = marketing && /^\/beta\/?$/.test(window.location.pathname);
const portalMatch = window.location.pathname.match(/^\/portal\/([^/]+)\/?$/);
const portalToken = portalMatch ? decodeURIComponent(portalMatch[1]) : "";
const pathStorefrontMatch = window.location.pathname.match(/^\/store\/([^/]+)\/?$/);
const subdomainMatch = hostname.match(/^([a-z0-9-]+)\.doobielogic\.io$/);
const reservedHosts = new Set(["www", "ops", "api", "app", "admin", "beta", "support", "status", "mail", "store", "portal"]);
const hostStorefront = subdomainMatch && !reservedHosts.has(subdomainMatch[1]) ? subdomainMatch[1] : "";
const storefrontSlug = pathStorefrontMatch ? decodeURIComponent(pathStorefrontMatch[1]) : hostStorefront;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      {portalToken ? <CommercePortalPage token={portalToken} /> : storefrontSlug ? <StorefrontPage slug={storefrontSlug} /> : marketing ? <>
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
