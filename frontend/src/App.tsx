import { AppShell } from "./components/AppShell";
import { lazy, Suspense, useState } from "react";

const HomePage = lazy(() => import("./pages/HomePage").then(module => ({ default: module.HomePage })));
const InventoryPage = lazy(() => import("./pages/InventoryPage").then(module => ({ default: module.InventoryPage })));
const BuyerOperationsPage = lazy(() => import("./pages/BuyerOperationsPage").then(module => ({ default: module.BuyerOperationsPage })));
const BuyerTrendsPage = lazy(() => import("./pages/BuyerTrendsPage").then(module => ({ default: module.BuyerTrendsPage })));
const SlowMoversPage = lazy(() => import("./pages/SlowMoversPage").then(module => ({ default: module.SlowMoversPage })));
const DeliveryImpactPage = lazy(() => import("./pages/DeliveryImpactPage").then(module => ({ default: module.DeliveryImpactPage })));
const BuyingRecommendationsPage = lazy(() => import("./pages/BuyingRecommendationsPage").then(module => ({ default: module.BuyingRecommendationsPage })));
const BuyingBudgetPage = lazy(() => import("./pages/BuyingBudgetPage").then(module => ({ default: module.BuyingBudgetPage })));
const PurchaseOrdersParityPage = lazy(() => import("./pages/PurchaseOrdersParityPage").then(module => ({ default: module.PurchaseOrdersParityPage })));
const ProductMasterPage = lazy(() => import("./pages/ProductMasterPage").then(module => ({ default: module.ProductMasterPage })));
const RetailInsightsPage = lazy(() => import("./pages/RetailInsightsPage").then(module => ({ default: module.RetailInsightsPage })));
const PurchasingPage = lazy(() => import("./pages/PurchasingPage").then(module => ({ default: module.PurchasingPage })));
const ProductionPage = lazy(() => import("./pages/ProductionPage").then(module => ({ default: module.ProductionPage })));
const ExtractionCommandCenterPage = lazy(() => import("./pages/ExtractionCommandCenterPage").then(module => ({ default: module.ExtractionCommandCenterPage })));
const WhiteLabelRepackPage = lazy(() => import("./pages/WhiteLabelRepackPage").then(module => ({ default: module.WhiteLabelRepackPage })));
const PackageStudioPage = lazy(() => import("./pages/PackageStudioPage").then(module => ({ default: module.PackageStudioPage })));
const OrdersPage = lazy(() => import("./pages/OrdersPage").then(module => ({ default: module.OrdersPage })));
const CompliancePage = lazy(() => import("./pages/CompliancePage").then(module => ({ default: module.CompliancePage })));
const DoobiePage = lazy(() => import("./pages/DoobiePage").then(module => ({ default: module.DoobiePage })));
const DataSettingsPage = lazy(() => import("./pages/DataSettingsPage").then(module => ({ default: module.DataSettingsPage })));
const LocationSettingsPage = lazy(() => import("./pages/LocationSettingsPage").then(module => ({ default: module.LocationSettingsPage })));
const AdminPage = lazy(() => import("./pages/AdminPage").then(module => ({ default: module.AdminPage })));
const IntegrationsPage = lazy(() => import("./pages/IntegrationsPage").then(module => ({ default: module.IntegrationsPage })));
const MAFlowerEquivalencyPage = lazy(() => import("./pages/MAFlowerEquivalencyPage").then(module => ({ default: module.MAFlowerEquivalencyPage })));
const NomenclatureMapperPage = lazy(() => import("./pages/NomenclatureMapperPage").then(module => ({ default: module.NomenclatureMapperPage })));
const ExecutiveReportsPage = lazy(() => import("./pages/ExecutiveReportsPage").then(module => ({ default: module.ExecutiveReportsPage })));
const ComplianceQAPage = lazy(() => import("./pages/ComplianceQAPage").then(module => ({ default: module.ComplianceQAPage })));

export default function App() {
  const [page, setPage] = useState("Home");
  const content = page === "Home" ? <HomePage onNavigate={setPage} />
    : page === "Buyer Operations" ? <BuyerOperationsPage onNavigate={setPage} />
    : page === "Inventory" ? <InventoryPage initialOperation="retail" />
    : page === "Production Inventory" ? <InventoryPage initialOperation="production" />
    : page === "Inventory Audits" ? <InventoryPage initialOperation="retail" initialAudits />
    : page === "Sales & Category Trends" ? <BuyerTrendsPage />
    : page === "Slow Movers" ? <SlowMoversPage />
    : page === "Delivery Performance" ? <DeliveryImpactPage />
    : page === "Buying Recommendations" ? <BuyingRecommendationsPage onNavigate={setPage} />
    : page === "Buying Budget" ? <BuyingBudgetPage />
    : page === "Purchase Orders" ? <PurchaseOrdersParityPage onNavigate={setPage} />
    : page === "Retail Product Master" ? <ProductMasterPage key="retail-product-master" initialOperation="retail" />
    : page === "Production Product Master" ? <ProductMasterPage key="production-product-master" initialOperation="production" />
    : page === "Purchasing" ? <PurchasingPage />
    : page === "Reports" ? <RetailInsightsPage />
    : page === "Production" ? <ProductionPage />
    : page === "Extraction" ? <ExtractionCommandCenterPage onNavigate={setPage} />
    : page === "White Label / Repack" ? <WhiteLabelRepackPage />
    : page === "Package Studio" ? <PackageStudioPage />
    : page === "Orders" ? <OrdersPage />
    : page === "Compliance" ? <CompliancePage />
    : page === "Compliance Q&A" ? <ComplianceQAPage />
    : page === "MA Flower Equivalency" ? <MAFlowerEquivalencyPage />
    : page === "Nomenclature Mapper" || page === "Product Name Mapper" ? <NomenclatureMapperPage />
    : page === "Executive Reports" ? <ExecutiveReportsPage />
    : page === "Doobie" ? <DoobiePage />
    : page === "Integrations" || page === "AI & METRC Integrations" || page === "METRC Integrations" ? <IntegrationsPage />
    : page === "Admin" || page === "Admin Tools" ? <AdminPage />
    : page === "Location Settings" ? <LocationSettingsPage />
    : page === "Data & Settings" ? <DataSettingsPage />
    : <InventoryPage initialOperation="retail" />;
  return <AppShell active={page} onNavigate={setPage}><Suspense fallback={<div className="state">Loading workspace…</div>}>{content}</Suspense></AppShell>;
}
