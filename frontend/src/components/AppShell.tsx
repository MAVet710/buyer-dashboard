import { BarChart3, Boxes, Factory, Home, Menu, Moon, PackageOpen, Settings, ShieldCheck, ShoppingCart, Sun } from "lucide-react";
import { useEffect, useMemo, useState, type PropsWithChildren } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, clearTrialSession } from "../lib/api";
import { supabase } from "../lib/supabase";
import { GlobalSearch } from "./GlobalSearch";
import { WorkspaceAgent } from "./WorkspaceAgent";

type Capability = "retail" | "production" | "cultivation" | "commercial";
type Facility = { id: string; name: string; code: string; license_type?: string; capabilities?: Record<Capability, boolean> };
type AccessOrganization = { id: string; name: string; slug: string; facilities: Facility[] };
type AccountContext = { user: { display_name: string; email: string; role: string; must_change_password?: boolean }; organization: { id: string; name: string; slug?: string } | null; facility_id: string; capabilities: Record<Capability, boolean>; facilities: Facility[] };
type AccessOptions = { organizations: AccessOrganization[]; organization_id: string; facility_id: string };
type OperationMode = "Retail Ops" | "Production Ops";
type PrimaryCategory = "Home" | "Inventory" | "Purchasing" | "Orders" | "Production" | "Reports" | "Compliance" | "Data & Settings";
type SecondaryItem = { label: string; page: string; roles?: readonly string[] };
type PrimaryItem = { label: PrimaryCategory; icon: typeof Home; defaultPage: string };
type BuyerDataMode = "Uploads" | "Dutchie Live";

// Match modules/navigation/operation_context_bar.py exactly. Trial falls back
// to Retail Ops, but planner is production-only and read_only cannot open
// Production Ops unless Streamlit grants it there too.
const RETAIL_ROLES = ["dev", "admin", "buyer", "supervisor", "operator", "qa", "read_only", "trial"] as const;
const PRODUCTION_ROLES = ["dev", "admin", "planner", "supervisor", "operator", "qa"] as const;
const ADMIN = ["dev", "admin"] as const;
const DEV = ["dev"] as const;
const NON_DEV = ["admin", "buyer", "planner", "supervisor", "operator", "qa", "read_only", "trial"] as const;

const RETAIL_PRIMARY: PrimaryItem[] = [
  { label: "Home", icon: Home, defaultPage: "Home" },
  { label: "Inventory", icon: Boxes, defaultPage: "Inventory" },
  { label: "Purchasing", icon: ShoppingCart, defaultPage: "Buyer Operations" },
  { label: "Orders", icon: PackageOpen, defaultPage: "Orders" },
  { label: "Reports", icon: BarChart3, defaultPage: "Sales & Category Trends" },
  { label: "Compliance", icon: ShieldCheck, defaultPage: "Compliance Q&A" },
  { label: "Data & Settings", icon: Settings, defaultPage: "Data & Settings" },
];

const PRODUCTION_PRIMARY: PrimaryItem[] = [
  { label: "Home", icon: Home, defaultPage: "Home" },
  { label: "Inventory", icon: Boxes, defaultPage: "Production Inventory" },
  { label: "Production", icon: Factory, defaultPage: "Production" },
  { label: "Orders", icon: PackageOpen, defaultPage: "Orders" },
  { label: "Compliance", icon: ShieldCheck, defaultPage: "Compliance" },
  { label: "Data & Settings", icon: Settings, defaultPage: "Data & Settings" },
];

function secondaryItems(category: PrimaryCategory, operation: OperationMode, role: string): SecondaryItem[] {
  if (category === "Home") return [
    { label: "Operations Control Tower", page: "Operations Control Tower" },
    { label: "Enterprise Control Tower", page: "Enterprise Control Tower", roles: ADMIN },
  ];
  if (operation === "Production Ops") {
    if (category === "Inventory") return [
      { label: "Materials", page: "Production Inventory" },
      { label: "Package 360", page: "Package 360" },
      { label: "Products", page: "Production Product Master" },
      { label: "Inventory Audits", page: "Inventory Audits" },
    ];
    if (category === "Production") return [
      { label: "Co-Man Production", page: "Production" },
      { label: "Production Run 360", page: "Production Run 360" },
      { label: "Extraction", page: "Extraction" },
      { label: "White Label / Repack", page: "White Label / Repack" },
    ];
    if (category === "Orders") return [
      { label: "Orders & Fulfillment", page: "Orders" },
      { label: "Warehouse Pick / Pack", page: "Warehouse Pick Pack" },
    ];
    if (category === "Compliance") return [
      { label: "Traceability", page: "Compliance" },
      { label: "State Actions", page: "Traceability Actions" },
    ];
    if (category === "Data & Settings") return dataSettingsItems(role);
    return [];
  }
  if (category === "Inventory") return [
    { label: "Inventory", page: "Inventory" },
    { label: "Product 360", page: "Retail Product 360" },
    { label: "Package 360", page: "Package 360" },
    { label: "Catalog Administration", page: "Retail Catalog Admin" },
    { label: "Inventory Audits", page: "Inventory Audits" },
    { label: "Slow Movers", page: "Slow Movers" },
    { label: "MA Flower Equivalency", page: "MA Flower Equivalency" },
  ];
  if (category === "Purchasing") return [
    { label: "Overview", page: "Buyer Operations" },
    { label: "Buying Recommendations", page: "Buying Recommendations" },
    { label: "Delivery Performance", page: "Delivery Performance" },
    { label: "Purchase Orders", page: "Purchase Orders" },
    { label: "Buying Budget", page: "Buying Budget" },
    { label: "Replenishment Policies", page: "Replenishment Policies" },
  ];
  if (category === "Orders") return [
    { label: "Orders & Fulfillment", page: "Orders" },
    { label: "Warehouse Pick / Pack", page: "Warehouse Pick Pack" },
  ];
  if (category === "Reports") return [
    { label: "Sales & Category Trends", page: "Sales & Category Trends" },
    { label: "Executive Reports", page: "Executive Reports" },
  ];
  if (category === "Compliance") return [
    { label: "Compliance Q&A", page: "Compliance Q&A" },
    { label: "Product Name Mapper", page: "Product Name Mapper" },
    { label: "Traceability", page: "Compliance" },
    { label: "State Actions", page: "Traceability Actions" },
  ];
  if (category === "Data & Settings") return dataSettingsItems(role);
  return [];
}

function dataSettingsItems(role: string): SecondaryItem[] {
  const rows: SecondaryItem[] = [
    { label: "Location", page: "Location Settings" },
    { label: "Imports & Data", page: "Data & Settings" },
  ];
  if (ADMIN.includes(role as never)) rows.push({ label: "Admin Tools", page: "Admin" });
  rows.push(role === "dev"
    ? { label: "AI & METRC Integrations", page: "Integrations", roles: DEV }
    : { label: "METRC Integrations", page: "Integrations", roles: NON_DEV });
  return rows;
}

function categoryForPage(page: string, operation: OperationMode): PrimaryCategory {
  if (["Home", "Operations Control Tower", "Enterprise Control Tower"].includes(page)) return "Home";
  if (["Inventory", "Retail Product Master", "Retail Product 360", "Package 360", "Retail Catalog Admin", "Inventory Audits", "Slow Movers", "MA Flower Equivalency", "Production Inventory", "Production Product Master"].includes(page)) return "Inventory";
  if (["Buyer Operations", "Buying Recommendations", "Delivery Performance", "Purchase Orders", "Buying Budget", "Purchasing", "Replenishment Policies"].includes(page)) return "Purchasing";
  if (["Orders", "Warehouse Pick Pack"].includes(page)) return "Orders";
  if (["Production", "Production Run 360", "Extraction", "White Label / Repack", "Package Studio"].includes(page)) return "Production";
  if (["Sales & Category Trends", "Reports", "Executive Reports"].includes(page)) return "Reports";
  if (["Compliance", "Compliance Q&A", "Traceability Actions", "Product Name Mapper", "Nomenclature Mapper"].includes(page)) return "Compliance";
  if (["Location Settings", "Data & Settings", "Admin", "Admin Tools", "Integrations", "AI & METRC Integrations", "METRC Integrations"].includes(page)) return "Data & Settings";
  return operation === "Production Ops" ? "Inventory" : "Inventory";
}

export function AppShell({ children, active, onNavigate }: PropsWithChildren<{ active: string; onNavigate: (page: string) => void }>) {
  const client = useQueryClient();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">(() => localStorage.getItem("buyer-dash-theme") === "light" ? "light" : "dark");
  const [operation, setOperation] = useState<OperationMode>(() => localStorage.getItem("buyer-dash-operation") === "Production Ops" ? "Production Ops" : "Retail Ops");
  const [dataMode, setDataMode] = useState<BuyerDataMode>(() => localStorage.getItem("buyer-dash-data-mode") === "Dutchie Live" ? "Dutchie Live" : "Uploads");
  const [classicNavigation, setClassicNavigation] = useState(() => localStorage.getItem("buyer-dash-classic-navigation") === "true");
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<AccountContext>("/api/v1/account/context", signal) });
  const access = useQuery({ queryKey: ["access-options"], queryFn: ({ signal }) => apiGet<AccessOptions>("/api/v1/account/access-options", signal), enabled: Boolean(context.data) });
  const selectedFacility = context.data?.facilities.find(row => row.id === context.data?.facility_id);
  const selectedOrganization = access.data?.organizations.find(row => row.id === context.data?.organization?.id);
  const role = context.data?.user.role ?? "trial";
  const isTrial = role === "trial";

  const operationAllowed = (mode: OperationMode): boolean => mode === "Retail Ops"
    ? RETAIL_ROLES.includes(role as never)
    : PRODUCTION_ROLES.includes(role as never);
  const facilitySupports = (facility: Facility | undefined, mode: OperationMode): boolean => {
    if (!facility) return false;
    return mode === "Retail Ops"
      ? Boolean(facility.capabilities?.retail)
      : Boolean(facility.capabilities?.production || facility.capabilities?.cultivation);
  };
  const currentSupports = (mode: OperationMode): boolean => mode === "Retail Ops"
    ? Boolean(context.data?.capabilities.retail)
    : Boolean(context.data && (context.data.capabilities.production || context.data.capabilities.cultivation));
  const findOperationTarget = (mode: OperationMode): { organizationId: string; facilityId: string } | null => {
    if (!context.data || !operationAllowed(mode)) return null;
    if (currentSupports(mode)) return { organizationId: context.data.organization?.id ?? "", facilityId: context.data.facility_id };
    if (isTrial) return null;
    const organizations = access.data?.organizations ?? [];
    const currentOrganizationId = context.data.organization?.id ?? "";
    const currentOrganization = organizations.find(row => row.id === currentOrganizationId);
    const currentOrganizationFacility = currentOrganization?.facilities.find(row => facilitySupports(row, mode));
    if (currentOrganization && currentOrganizationFacility) return { organizationId: currentOrganization.id, facilityId: currentOrganizationFacility.id };
    if (role === "dev") {
      for (const organizationRow of organizations) {
        const facility = organizationRow.facilities.find(row => facilitySupports(row, mode));
        if (facility) return { organizationId: organizationRow.id, facilityId: facility.id };
      }
    }
    return null;
  };
  const canRetail = Boolean(findOperationTarget("Retail Ops"));
  const canProduction = Boolean(findOperationTarget("Production Ops"));
  const operationModes = useMemo<OperationMode[]>(() => {
    const modes: OperationMode[] = [];
    if (canRetail) modes.push("Retail Ops");
    if (canProduction) modes.push("Production Ops");
    return modes.length ? modes : ["Retail Ops"];
  }, [canRetail, canProduction]);

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("buyer-dash-theme", theme); }, [theme]);
  useEffect(() => {
    if (!operationModes.includes(operation)) setOperation(operationModes[0]);
  }, [operation, operationModes]);
  useEffect(() => { localStorage.setItem("buyer-dash-operation", operation); }, [operation]);
  useEffect(() => { localStorage.setItem("buyer-dash-data-mode", dataMode); window.dispatchEvent(new CustomEvent("buyer-dash-data-mode", { detail: dataMode })); }, [dataMode]);
  useEffect(() => { localStorage.setItem("buyer-dash-classic-navigation", String(classicNavigation)); }, [classicNavigation]);
  useEffect(() => {
    if (!navigationOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setNavigationOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [navigationOpen]);

  const primary = operation === "Production Ops" ? PRODUCTION_PRIMARY : RETAIL_PRIMARY;
  const activeCategory = categoryForPage(active, operation);
  const secondary = secondaryItems(activeCategory, operation, role).filter(item => !item.roles || item.roles.includes(role as never));
  const routeToOperation = (page: string, mode: OperationMode) => {
    const target = findOperationTarget(mode);
    if (target && target.facilityId !== context.data?.facility_id) {
      sessionStorage.setItem("buyer-dash-pending-page", page);
      localStorage.setItem("buyer-dash-operation", mode);
      localStorage.setItem("buyer-dash-organization", target.organizationId);
      localStorage.setItem("buyer-dash-facility", target.facilityId);
      client.clear();
      window.location.reload();
      return;
    }
    onNavigate(page);
    setNavigationOpen(false);
  };
  const navigate = (page: string) => routeToOperation(page, operation);
  const chooseCategory = (row: PrimaryItem) => {
    const nextSecondary = secondaryItems(row.label, operation, role).filter(item => !item.roles || item.roles.includes(role as never));
    navigate(nextSecondary[0]?.page ?? row.defaultPage);
  };
  const changeOperation = (next: OperationMode) => {
    setOperation(next);
    localStorage.setItem("buyer-dash-operation", next);
    const nextPrimary = next === "Production Ops" ? PRODUCTION_PRIMARY : RETAIL_PRIMARY;
    const target = nextPrimary.find(row => row.label === "Inventory") ?? nextPrimary[0];
    const nextSecondary = secondaryItems(target.label, next, role).filter(item => !item.roles || item.roles.includes(role as never));
    routeToOperation(nextSecondary[0]?.page ?? target.defaultPage, next);
  };
  const changeDataMode = (next: BuyerDataMode) => setDataMode(next);
  const switchOrganization = (organizationId: string) => {
    if (isTrial) return;
    const organizationRow = access.data?.organizations.find(row => row.id === organizationId);
    const firstFacility = organizationRow?.facilities[0];
    if (!organizationRow || !firstFacility) return;
    sessionStorage.setItem("buyer-dash-pending-page", active);
    localStorage.setItem("buyer-dash-organization", organizationRow.id);
    localStorage.setItem("buyer-dash-facility", firstFacility.id);
    client.clear();
    window.location.reload();
  };
  const switchFacility = (facilityId: string) => {
    if (isTrial) return;
    sessionStorage.setItem("buyer-dash-pending-page", active);
    localStorage.setItem("buyer-dash-organization", context.data?.organization?.id ?? "");
    localStorage.setItem("buyer-dash-facility", facilityId);
    client.clear();
    window.location.reload();
  };
  const signOut = async () => {
    localStorage.removeItem("buyer-dash-organization");
    localStorage.removeItem("buyer-dash-facility");
    sessionStorage.removeItem("buyer-dash-pending-page");
    clearTrialSession();
    client.clear();
    if (isTrial) { window.location.reload(); return; }
    await supabase?.auth.signOut();
  };

  return <div className="app-shell">
    {navigationOpen ? <button className="navigation-backdrop" aria-label="Close navigation" onClick={() => setNavigationOpen(false)} /> : null}
    <aside className={navigationOpen ? "sidebar open" : "sidebar"} id="primary-navigation" aria-label="Primary navigation">
      <div className="brand"><span>DL</span><strong>DoobieLogic</strong></div>
      <div className="dl-nav-context"><strong>Active</strong><br/>{context.data?.organization?.name ?? "DoobieLogic"} · {selectedFacility?.name ?? "Loading facility…"} · {operation}</div>
      <div className="sidebar-caption">Choose the work, not the architecture.</div>
      {!classicNavigation ? <>
        <nav aria-label="Work areas">{primary.map(row => { const Icon = row.icon; return <button className={row.label === activeCategory ? "nav-item active" : "nav-item"} key={row.label} onClick={() => chooseCategory(row)}><Icon size={18}/><span>{row.label}</span></button>; })}</nav>
        {secondary.length ? <><div className="operation-label">Current area</div><nav className="secondary-nav" aria-label={`${activeCategory} tools`}>{secondary.map(row => <button className={row.page === active ? "nav-item active" : "nav-item"} key={row.page} onClick={() => navigate(row.page)}><span>{row.label}</span></button>)}</nav></> : null}
        {operation === "Retail Ops" ? <details className="sidebar-expander"><summary>Data source</summary><div><label className="compact-field">Buyer data mode<select className="data-mode-select" value={dataMode} onChange={event => changeDataMode(event.target.value === "Dutchie Live" ? "Dutchie Live" : "Uploads")}><option value="Uploads">📁 Uploads</option><option value="Dutchie Live">🔴 Dutchie Live</option></select></label></div></details> : null}
      </> : <ClassicNavigation operation={operation} role={role} active={active} onNavigate={navigate}/>} 
      <WorkspaceAgent activePage={active} operation={operation} onNavigate={navigate}/>
      <details className="sidebar-expander"><summary>Navigation options</summary><div><label className="toggle"><input type="checkbox" checked={classicNavigation} onChange={event => setClassicNavigation(event.target.checked)}/> Use classic navigation</label></div></details>
    </aside>
    <section className="workspace">
      <header className="topbar">
        <button className="icon-button nav-toggle" aria-label={navigationOpen ? "Close navigation" : "Open navigation"} aria-expanded={navigationOpen} aria-controls="primary-navigation" onClick={() => setNavigationOpen(open => !open)}><Menu size={19}/></button>
        <span className="context-status">{selectedOrganization?.slug === "dev-sandbox" ? "Sandbox synced" : "Facility synced"}</span>
        <div className="context-switchers" aria-label="Access Context">
          {role === "dev" && access.data && access.data.organizations.length > 1 ? <select className="organization-switch" aria-label="Organization" value={context.data?.organization?.id ?? ""} onChange={event => switchOrganization(event.target.value)}>{access.data.organizations.map(row => <option value={row.id} key={row.id}>{row.slug === "dev-sandbox" ? "DEV Sandbox" : row.name}</option>)}</select> : <span className="access-badge">{context.data?.organization?.name ?? "Organization"}</span>}
          {!isTrial && context.data?.facilities.length ? <select className="facility-switch" aria-label="Facility" value={context.data.facility_id} onChange={event => switchFacility(event.target.value)}>{context.data.facilities.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select> : <span className="access-badge">{selectedFacility?.name ?? "Facility"}</span>}
          <select className="operation-switch-select" aria-label="Operation" value={operation} onChange={event => changeOperation(event.target.value as OperationMode)}>{operationModes.map(row => <option value={row} key={row}>{row}</option>)}</select>
          {selectedOrganization?.slug === "dev-sandbox" ? <span className="access-badge">{isTrial ? "24-hour Trial" : "DEV Sandbox"}</span> : null}
        </div>
        <button className="icon-button theme-toggle" title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} onClick={() => setTheme(current => current === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={18}/> : <Moon size={18}/>}</button>
        <button className="user-chip" onClick={signOut}>{context.data?.user.display_name || context.data?.user.email || "Developer"} · {role}</button>
      </header>
      <main><MobileNavigation primary={primary} category={activeCategory} secondary={secondary} active={active} operation={operation} dataMode={dataMode} onDataMode={changeDataMode} onCategory={chooseCategory} onNavigate={navigate}/><GlobalSearch onNavigate={navigate}/>{children}</main>
    </section>
  </div>;
}

function MobileNavigation({ primary, category, secondary, active, operation, dataMode, onDataMode, onCategory, onNavigate }: { primary: PrimaryItem[]; category: PrimaryCategory; secondary: SecondaryItem[]; active: string; operation: OperationMode; dataMode: BuyerDataMode; onDataMode: (mode: BuyerDataMode) => void; onCategory: (item: PrimaryItem) => void; onNavigate: (page: string) => void }) {
  return <section className="mobile-flat-navigation"><div className="eyebrow">DoobieLogic</div><select aria-label="Navigate" value={category} onChange={event => { const row = primary.find(item => item.label === event.target.value); if (row) onCategory(row); }}>{primary.map(row => <option key={row.label} value={row.label}>{row.label}</option>)}</select>{secondary.length ? <select aria-label="Tool" value={secondary.some(row => row.page === active) ? active : secondary[0].page} onChange={event => onNavigate(event.target.value)}>{secondary.map(row => <option key={row.page} value={row.page}>{row.label}</option>)}</select> : null}{operation === "Retail Ops" ? <select className="mobile-data-mode-select" aria-label="Buyer data mode" value={dataMode} onChange={event => onDataMode(event.target.value === "Dutchie Live" ? "Dutchie Live" : "Uploads")}><option value="Uploads">📁 Uploads</option><option value="Dutchie Live">🔴 Dutchie Live</option></select> : null}</section>;
}

function ClassicNavigation({ operation, role, active, onNavigate }: { operation: OperationMode; role: string; active: string; onNavigate: (page: string) => void }) {
  const groups = operation === "Production Ops"
    ? [
      { label: "Operations Home", pages: secondaryItems("Home", operation, role) },
      { label: "Production Inventory", pages: secondaryItems("Inventory", operation, role) },
      { label: "Production Ops", pages: secondaryItems("Production", operation, role) },
      { label: "Orders", pages: secondaryItems("Orders", operation, role) },
      { label: "Compliance", pages: secondaryItems("Compliance", operation, role) },
      { label: "Data & Integrations", pages: dataSettingsItems(role) },
    ]
    : [
      { label: "Operations Home", pages: secondaryItems("Home", operation, role) },
      { label: "Retail Inventory", pages: secondaryItems("Inventory", operation, role) },
      { label: "Purchasing", pages: secondaryItems("Purchasing", operation, role) },
      { label: "Orders", pages: secondaryItems("Orders", operation, role) },
      { label: "Reports", pages: secondaryItems("Reports", operation, role) },
      { label: "Compliance", pages: secondaryItems("Compliance", operation, role) },
      { label: "Data & Integrations", pages: dataSettingsItems(role) },
    ];
  return <>{groups.map(group => <div key={group.label}><div className="operation-label">{group.label}</div><nav>{group.pages.filter(row => !row.roles || row.roles.includes(role as never)).map(row => <button className={active === row.page ? "nav-item active" : "nav-item"} key={`${group.label}-${row.page}`} onClick={() => onNavigate(row.page)}>{row.label}</button>)}</nav></div>)}</>;
}
