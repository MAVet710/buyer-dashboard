import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, StrictMode, Suspense, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { OfflineStatusBar } from "./components/OfflineStatusBar";
import { registerDoobieLogicServiceWorker } from "./lib/pwa";
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
import "./cowboy-storefront.css";
import "./commerce-launcher.css";
import "./offline.css";

const App = lazy(() => import("./App"));
const AuthGate = lazy(() => import("./components/AuthGate").then(module => ({ default: module.AuthGate })));
const CommerceStorefrontLauncher = lazy(() => import("./components/CommerceStorefrontLauncher").then(module => ({ default: module.CommerceStorefrontLauncher })));
const AppSupportButton = lazy(() => import("./components/ContactChannels").then(module => ({ default: module.AppSupportButton })));
const MarketingContactChannels = lazy(() => import("./components/ContactChannels").then(module => ({ default: module.MarketingContactChannels })));
const PublicStorefrontAgeGate = lazy(() => import("./components/PublicStorefrontAgeGate").then(module => ({ default: module.PublicStorefrontAgeGate })));
const MarketingHome = lazy(() => import("./pages/MarketingHome").then(module => ({ default: module.MarketingHome })));
const BetaPartnerPage = lazy(() => import("./pages/BetaPartnerPage").then(module => ({ default: module.BetaPartnerPage })));
const CommercePortalPage = lazy(() => import("./pages/CommercePortalPage").then(module => ({ default: module.CommercePortalPage })));
const StorefrontPage = lazy(() => import("./pages/StorefrontPage").then(module => ({ default: module.StorefrontPage })));

const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
const hostname = window.location.hostname.trim().toLowerCase().replace(/\.$/, "");
const marketing = isMarketingHost(window.location.hostname);
configureSeo(marketing);
const betaPage = marketing && /^\/beta\/?$/.test(window.location.pathname);
const portalMatch = window.location.pathname.match(/^\/portal\/([^/]+)\/?$/);
const portalToken = portalMatch ? decodeURIComponent(portalMatch[1]) : "";
const pathStorefrontMatch = window.location.pathname.match(/^\/store\/([^/]+)\/?$/);
const subdomainMatch = hostname.match(/^([a-z0-9-]+)\.doobielogic\.io$/);
const reservedHosts = new Set(["www", "ops", "api", "app", "admin", "beta", "support", "status", "mail", "store", "portal"]);
const hostStorefront = subdomainMatch && !reservedHosts.has(subdomainMatch[1]) ? subdomainMatch[1] : "";
const storefrontSlug = pathStorefrontMatch ? decodeURIComponent(pathStorefrontMatch[1]) : hostStorefront;

function ModeBoundary({ children }: { children: ReactNode }) {
  return <Suspense fallback={<div className="state">Loading DoobieLogic…</div>}>{children}</Suspense>;
}

function SiteMode() {
  if (portalToken) return <CommercePortalPage token={portalToken} />;
  if (storefrontSlug) return <PublicStorefrontAgeGate><StorefrontPage slug={storefrontSlug} /></PublicStorefrontAgeGate>;
  if (marketing) return <>{betaPage ? <BetaPartnerPage /> : <MarketingHome />}<MarketingContactChannels /></>;
  return <AuthGate>
    <BrowserRouter>
      <>
        <App />
        <CommerceStorefrontLauncher />
        <AppSupportButton />
        <OfflineStatusBar />
      </>
    </BrowserRouter>
  </AuthGate>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <ModeBoundary><SiteMode /></ModeBoundary>
    </QueryClientProvider>
  </StrictMode>,
);

void registerDoobieLogicServiceWorker();
