import { useQueryClient } from "@tanstack/react-query";
import { AppShell } from "./components/AppShell";
import { lazy, Suspense, useEffect, useState } from "react";

const HomePage = lazy(() => import("./pages/HomePage").then(module => ({ default: module.HomePage })));
const InventoryPage = lazy(() => import("./pages/InventoryPage").then(module => ({ default: module.InventoryPage })));
const FocusedInventoryAudits = lazy(() => import("./components/FocusedInventoryAudits").then(module => ({ default: module.FocusedInventoryAudits })));
const BuyerCommandCenterPage = lazy(() => import("./pages/BuyerCommandCenterPage").then(module => ({ default: module.BuyerCommandCenterPage })));
const BuyerTrendsPage = lazy(() => import("./pages/BuyerTrendsPage").then(module => ({ default: module.BuyerTrendsPage })));
const SlowMoversPage = lazy(() => import("./pages/SlowMoversPage").then(module => ({ default: module.SlowMoversPage })));
const DeliveryImpactPage = lazy(() => import("./pages/DeliveryImpactPage").then(module => ({ default: module.DeliveryImpactPage })));
const BuyingRecommendationsPage = lazy(() => import("./pages/BuyingRecommendationsPage").then(module => ({ default: module.BuyingRecommendationsPage })));
const BuyingBudgetPage = lazy(() => import("./pages/BuyingBudgetPage").then(module => ({ default: module.BuyingBudgetPage })));
const PurchaseOrdersParityPage = lazy(() => import("./pages/PurchaseOrdersParityPage").then(module => ({ default: module.PurchaseOrdersParityPage })));
const ProductMasterPage = lazy(() => import("./pages/ProductMasterPage").then(module => ({ default: module.ProductMasterPage })));
const RetailProduct360Page = lazy(() => import("./pages/RetailProduct360Page").then(module => ({ default: module.RetailProduct360Page })));
const RetailInsightsPage = lazy(() => import("./pages/RetailInsightsPage").then(module => ({ default: module.RetailInsightsPage })));
const PurchasingPage = lazy(() => import("./pages/PurchasingPage").then(module => ({ default: module.PurchasingPage })));
const ProductionPage = lazy(() => import("./pages/ProductionPage").then(module => ({ default: module.ProductionPage })));
const ExtractionUnifiedPage = lazy(() => import("./pages/ExtractionUnifiedPage").then(module => ({ default: module.ExtractionUnifiedPage })));
const WhiteLabelRepackPage = lazy(() => import("./pages/WhiteLabelRepackPage").then(module => ({ default: module.WhiteLabelRepackPage })));
const PackageStudioPage = lazy(() => import("./pages/PackageStudioPage").then(module => ({ default: module.PackageStudioPage })));
const OrdersPage = lazy(() => import("./pages/OrdersPage").then(module => ({ default: module.OrdersPage })));
const CompliancePage = lazy(() => import("./pages/CompliancePage").then(module => ({ default: module.CompliancePage })));
const DoobiePage = lazy(() => import("./pages/DoobiePage").then(module => ({ default: module.DoobiePage })));
const DataSettingsPage = lazy(() => import("./pages/DataSettingsPage").then(module => ({ default: module.DataSettingsPage })));
const LocationSettingsPage = lazy(() => import("./pages/LocationSettingsPage").then(module => ({ default: module.LocationSettingsPage })));
const AdminToolsPage = lazy(() => import("./pages/AdminToolsPage").then(module => ({ default: module.AdminToolsPage })));
const IntegrationsPage = lazy(() => import("./pages/IntegrationsPage").then(module => ({ default: module.IntegrationsPage })));
const DeveloperConnectionsPanel = lazy(() => import("./components/DeveloperConnectionsPanel").then(module => ({ default: module.DeveloperConnectionsPanel })));
const MAFlowerEquivalencyPage = lazy(() => import("./pages/MAFlowerEquivalencyPage").then(module => ({ default: module.MAFlowerEquivalencyPage })));
const NomenclatureMapperPage = lazy(() => import("./pages/NomenclatureMapperPage").then(module => ({ default: module.NomenclatureMapperPage })));
const ExecutiveReportsPage = lazy(() => import("./pages/ExecutiveReportsPage").then(module => ({ default: module.ExecutiveReportsPage })));
const ComplianceQAPage = lazy(() => import("./pages/ComplianceQAPage").then(module => ({ default: module.ComplianceQAPage })));

function initialPage(): string {
  const pending = sessionStorage.getItem("buyer-dash-pending-page");
  if (pending) {
    sessionStorage.removeItem("buyer-dash-pending-page");
    return pending;
  }
  return "Home";
}

function UnknownWorkspace({ page, onHome }: { page: string; onHome: () => void }) {
  return <section className="inventory-panel state error">
    <strong>Workspace unavailable</strong>
    <p>DoobieLogic could not restore the saved workspace “{page}”. The app will not silently send you to a different module.</p>
    <button className="primary" type="button" onClick={onHome}>Return to Home</button>
  </section>;
}

export default function App() {
  const client = useQueryClient();
  const [page, setPage] = useState(initialPage);
  useEffect(() => {
    const refreshForDataMode = () => { void client.invalidateQueries(); };
    window.addEventListener("buyer-dash-data-mode", refreshForDataMode);
    return () => window.removeEventListener("buyer-dash-data-mode", refreshForDataMode);
  }, [client]);
  const content = page === "Home" ? <HomePage onNavigate={setPage} />
    : page === "Buyer Operations" || page === "Purchasing" ? <BuyerCommandCenterPage onNavigate={setPage} />
    : page === "Inventory" ? <InventoryPage initialOperation="retail" onNavigate={setPage} />
    : page === "Production Inventory" ? <InventoryPage initialOperation="production" onNavigate={setPage} />
    : page === "Inventory Audits" ? <FocusedInventoryAudits />
    : page === "Sales & Category Trends" ? <BuyerTrendsPage />
    : page === "Slow Movers" ? <SlowMoversPage />
    : page === "Delivery Performance" ? <DeliveryImpactPage />
    : page === "Buying Recommendations" ? <BuyingRecommendationsPage />
    : page === "Buying Budget" ? <BuyingBudgetPage />
    : page === "Purchase Orders" ? <PurchaseOrdersParityPage onNavigate={setPage} />
    : page === "Retail Product 360" || page === "Retail Product Master" ? <RetailProduct360Page onNavigate={setPage} />
    : page === "Retail Catalog Admin" ? <ProductMasterPage key="retail-product-master" initialOperation="retail" />
    : page === "Production Product Master" ? <ProductMasterPage key="production-product-master" initialOperation="production" />
    : page === "Replenishment Policies" ? <PurchasingPage />
    : page === "Reports" ? <RetailInsightsPage />
    : page === "Production" ? <ProductionPage />
    : page === "Extraction" ? <ExtractionUnifiedPage onNavigate={setPage} />
    : page === "White Label / Repack" ? <WhiteLabelRepackPage />
    : page === "Package Studio" ? <PackageStudioPage />
    : page === "Orders" ? <OrdersPage />
    : page === "Compliance" ? <CompliancePage />
    : page === "Compliance Q&A" ? <ComplianceQAPage />
    : page === "MA Flower Equivalency" ? <MAFlowerEquivalencyPage />
    : page === "Nomenclature Mapper" || page === "Product Name Mapper" ? <NomenclatureMapperPage />
    : page === "Executive Reports" ? <ExecutiveReportsPage />
    : page === "Doobie" ? <DoobiePage />
    : page === "Integrations" || page === "AI & METRC Integrations" || page === "METRC Integrations" ? <><IntegrationsPage /><DeveloperConnectionsPanel /></>
    : page === "Admin" || page === "Admin Tools" ? <AdminToolsPage />
    : page === "Location Settings" ? <LocationSettingsPage />
    : page === "Data & Settings" ? <DataSettingsPage onNavigate={setPage} />
    : <UnknownWorkspace page={page} onHome={() => setPage("Home")} />;
  return <AppShell active={page} onNavigate={setPage}><Suspense fallback={<div className="state">Loading workspace…</div>}>{content}</Suspense></AppShell>;
}
