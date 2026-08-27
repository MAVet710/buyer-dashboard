import { useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ProductionCalendar } from "./components/ProductionCalendar";
import { ProductionNextActions } from "./components/ProductionNextActions";
import { ProductionPlanner } from "./components/ProductionPlanner";
import { WorkspaceWindow } from "./components/WorkspaceWindow";
import { entityContextForPath, pageForPath, pathForPage } from "./lib/workspaceRoutes";

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
const ProductionRun360Page = lazy(() => import("./pages/ProductionRun360Page").then(module => ({ default: module.ProductionRun360Page })));
const ExtractionUnifiedPage = lazy(() => import("./pages/ExtractionUnifiedPage").then(module => ({ default: module.ExtractionUnifiedPage })));
const WhiteLabelRepackPage = lazy(() => import("./pages/WhiteLabelRepackPage").then(module => ({ default: module.WhiteLabelRepackPage })));
const PackageStudioPage = lazy(() => import("./pages/PackageStudioPage").then(module => ({ default: module.PackageStudioPage })));
const Package360Page = lazy(() => import("./pages/Package360Page").then(module => ({ default: module.Package360Page })));
const OrdersPage = lazy(() => import("./pages/OrdersPage").then(module => ({ default: module.OrdersPage })));
const WarehousePickPackPage = lazy(() => import("./pages/WarehousePickPackPage").then(module => ({ default: module.WarehousePickPackPage })));
const CompliancePage = lazy(() => import("./pages/CompliancePage").then(module => ({ default: module.CompliancePage })));
const TraceabilityActionsPage = lazy(() => import("./pages/TraceabilityActionsPage").then(module => ({ default: module.TraceabilityActionsPage })));
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
const OperationsControlTowerPage = lazy(() => import("./pages/OperationsControlTowerPage").then(module => ({ default: module.OperationsControlTowerPage })));
const EnterpriseControlPage = lazy(() => import("./pages/EnterpriseControlPage").then(module => ({ default: module.EnterpriseControlPage })));
const LabelStudioPage = lazy(() => import("./pages/LabelStudioPage").then(module => ({ default: module.LabelStudioPage })));

function UnknownWorkspace({ path, onHome }: { path: string; onHome: () => void }) {
  return <section className="inventory-panel state error">
    <strong>Workspace unavailable</strong>
    <p>DoobieLogic could not restore the workspace at “{path}”. The app will not silently send you to a different module.</p>
    <button className="primary" type="button" onClick={onHome}>Return to Home</button>
  </section>;
}

export default function App() {
  const client = useQueryClient();
  const location = useLocation();
  const routerNavigate = useNavigate();
  const [run360Open, setRun360Open] = useState(false);
  const [run360OrderId, setRun360OrderId] = useState("");
  const page = pageForPath(location.pathname);
  const entity = entityContextForPath(location.pathname);
  const productId = entity?.kind === "product" ? entity.id : "";
  const packageCode = entity?.kind === "package" ? entity.id : "";

  const openProductionRun360 = (orderId = "") => {
    setRun360OrderId(orderId);
    setRun360Open(true);
  };

  const navigate = (nextPage: string) => {
    if (nextPage === "Production Run 360" && page !== "Production Run 360") {
      openProductionRun360();
      return;
    }
    routerNavigate(pathForPage(nextPage));
  };
  const setPage = navigate;

  useEffect(() => {
    const pending = sessionStorage.getItem("buyer-dash-pending-page");
    if (pending) {
      const pendingPath = pathForPage(pending);
      if (pendingPath === location.pathname) {
        sessionStorage.removeItem("buyer-dash-pending-page");
      } else {
        routerNavigate(pendingPath, { replace: true });
      }
      return;
    }
    if (location.pathname === "/") routerNavigate("/home", { replace: true });
  }, [location.pathname, routerNavigate]);

  useEffect(() => {
    const refreshForDataMode = () => { void client.invalidateQueries(); };
    window.addEventListener("buyer-dash-data-mode", refreshForDataMode);
    return () => window.removeEventListener("buyer-dash-data-mode", refreshForDataMode);
  }, [client]);

  const content = page === "Home" ? <HomePage onNavigate={navigate} />
    : page === "Buyer Operations" || page === "Purchasing" ? <BuyerCommandCenterPage onNavigate={setPage} />
    : page === "Inventory" ? <InventoryPage initialOperation="retail" onNavigate={navigate} />
    : page === "Production Inventory" ? <InventoryPage initialOperation="production" onNavigate={navigate} />
    : page === "Inventory Audits" ? <FocusedInventoryAudits />
    : page === "Package 360" ? <Package360Page onNavigate={navigate} initialCode={packageCode} />
    : page === "Sales & Category Trends" ? <BuyerTrendsPage />
    : page === "Slow Movers" ? <SlowMoversPage />
    : page === "Delivery Performance" ? <DeliveryImpactPage />
    : page === "Buying Recommendations" ? <BuyingRecommendationsPage />
    : page === "Buying Budget" ? <BuyingBudgetPage />
    : page === "Purchase Orders" ? <PurchaseOrdersParityPage onNavigate={navigate} />
    : page === "Retail Product 360" || page === "Retail Product Master" ? <RetailProduct360Page onNavigate={navigate} initialProductId={productId} />
    : page === "Retail Catalog Admin" ? <ProductMasterPage key="retail-product-master" initialOperation="retail" />
    : page === "Production Product Master" ? <ProductMasterPage key="production-product-master" initialOperation="production" />
    : page === "Replenishment Policies" ? <PurchasingPage />
    : page === "Reports" ? <RetailInsightsPage />
    : page === "Production" ? <><ProductionPlanner onOpenRun={openProductionRun360}/><ProductionNextActions onOpenRun={openProductionRun360}/><ProductionPage /></>
    : page === "Production Calendar" ? <ProductionCalendar onOpenRun={openProductionRun360}/>
    : page === "Production Run 360" ? <ProductionRun360Page onNavigate={navigate} initialOrderId={run360OrderId} />
    : page === "Extraction" ? <ExtractionUnifiedPage onNavigate={navigate} />
    : page === "White Label / Repack" ? <WhiteLabelRepackPage />
    : page === "Package Studio" ? <PackageStudioPage />
    : page === "Orders" ? <OrdersPage />
    : page === "Warehouse Pick Pack" ? <WarehousePickPackPage onNavigate={navigate} />
    : page === "Compliance" ? <CompliancePage />
    : page === "Traceability Actions" ? <TraceabilityActionsPage onNavigate={navigate} />
    : page === "Compliance Q&A" ? <ComplianceQAPage />
    : page === "Label Studio" ? <LabelStudioPage />
    : page === "MA Flower Equivalency" ? <MAFlowerEquivalencyPage />
    : page === "Nomenclature Mapper" || page === "Product Name Mapper" ? <NomenclatureMapperPage />
    : page === "Executive Reports" ? <ExecutiveReportsPage />
    : page === "Operations Control Tower" ? <OperationsControlTowerPage />
    : page === "Enterprise Control Tower" ? <EnterpriseControlPage onNavigate={navigate} />
    : page === "Doobie" ? <DoobiePage />
    : page === "Integrations" || page === "AI & METRC Integrations" || page === "METRC Integrations" ? <><IntegrationsPage /><DeveloperConnectionsPanel /></>
    : page === "Admin" || page === "Admin Tools" ? <AdminToolsPage />
    : page === "Location Settings" ? <LocationSettingsPage />
    : page === "Data & Settings" ? <DataSettingsPage onNavigate={navigate} />
    : <UnknownWorkspace path={location.pathname} onHome={() => routerNavigate("/home")} />;

  return <>
    <AppShell active={page ?? location.pathname} onNavigate={navigate}>
      <Suspense fallback={<div className="state">Loading workspace…</div>}>{content}</Suspense>
    </AppShell>
    <WorkspaceWindow open={run360Open} onClose={() => { setRun360Open(false); setRun360OrderId(""); }} eyebrow="PRODUCTION · RUN 360" title="Production Run 360" subtitle="Inspect and work the run without leaving the production workspace." ariaLabel="Production Run 360" windowKey="production-run-360">
      <Suspense fallback={<div className="state">Loading Production Run 360…</div>}><ProductionRun360Page onNavigate={navigate} initialOrderId={run360OrderId}/></Suspense>
    </WorkspaceWindow>
  </>;
}
