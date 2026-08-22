import { AppShell } from "./components/AppShell";
import { lazy, Suspense, useState } from "react";

const HomePage = lazy(() => import("./pages/HomePage").then(module => ({ default: module.HomePage })));
const InventoryPage = lazy(() => import("./pages/InventoryPage").then(module => ({ default: module.InventoryPage })));
const ProductMasterPage = lazy(() => import("./pages/ProductMasterPage").then(module => ({ default: module.ProductMasterPage })));
const RetailInsightsPage = lazy(() => import("./pages/RetailInsightsPage").then(module => ({ default: module.RetailInsightsPage })));
const PurchasingPage = lazy(() => import("./pages/PurchasingPage").then(module => ({ default: module.PurchasingPage })));
const ProductionPage = lazy(() => import("./pages/ProductionPage").then(module => ({ default: module.ProductionPage })));
const ExtractionPage = lazy(() => import("./pages/ExtractionPage").then(module => ({ default: module.ExtractionPage })));
const PackageStudioPage = lazy(() => import("./pages/PackageStudioPage").then(module => ({ default: module.PackageStudioPage })));
const OrdersPage = lazy(() => import("./pages/OrdersPage").then(module => ({ default: module.OrdersPage })));
const CompliancePage = lazy(() => import("./pages/CompliancePage").then(module => ({ default: module.CompliancePage })));
const DoobiePage = lazy(() => import("./pages/DoobiePage").then(module => ({ default: module.DoobiePage })));
const DataSettingsPage = lazy(() => import("./pages/DataSettingsPage").then(module => ({ default: module.DataSettingsPage })));
const AdminPage = lazy(() => import("./pages/AdminPage").then(module => ({ default: module.AdminPage })));
const IntegrationsPage = lazy(() => import("./pages/IntegrationsPage").then(module => ({ default: module.IntegrationsPage })));

export default function App() {
  const [page, setPage] = useState("Inventory");
  const content = page === "Home" ? <HomePage onNavigate={setPage} /> : page === "Retail Product Master" ? <ProductMasterPage key="retail-product-master" initialOperation="retail" /> : page === "Production Product Master" ? <ProductMasterPage key="production-product-master" initialOperation="production" /> : page === "Purchasing" ? <PurchasingPage /> : page === "Reports" ? <RetailInsightsPage /> : page === "Production" ? <ProductionPage /> : page === "Extraction" ? <ExtractionPage /> : page === "Package Studio" ? <PackageStudioPage /> : page === "Orders" ? <OrdersPage /> : page === "Compliance" ? <CompliancePage /> : page === "Doobie" ? <DoobiePage /> : page === "Integrations" ? <IntegrationsPage /> : page === "Admin" ? <AdminPage /> : page === "Data & Settings" ? <DataSettingsPage /> : <InventoryPage />;
  return <AppShell active={page} onNavigate={setPage}><Suspense fallback={<div className="state">Loading workspace…</div>}>{content}</Suspense></AppShell>;
}
