import { BarChart3, BookOpen, Boxes, ClipboardCheck, Combine, Factory, FileText, FlaskConical, Gauge, Menu, PackageOpen, Plug, Scale, Settings, ShieldCheck, ShoppingCart, Sparkles, Tags, Users } from "lucide-react";
import { useEffect, useState, type PropsWithChildren } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import { supabase } from "../lib/supabase";

type Capability = "retail" | "production" | "cultivation" | "commercial";
type Facility = { id: string; name: string; code: string; license_type?: string; capabilities?: Record<Capability, boolean> };
type AccountContext = { user: { display_name: string; email: string; role: string; must_change_password?: boolean }; organization: { id: string; name: string; slug?: string } | null; facility_id: string; capabilities: Record<Capability, boolean>; facilities: Facility[] };
type AccessOptions = { organizations: { id: string; name: string; slug: string; facilities: Facility[] }[]; organization_id: string; facility_id: string };
type NavigationItem = { section: string } | { icon: typeof Gauge; label: string; page: string; capability?: Capability; roles?: readonly string[] };

const ADMIN = ["dev", "admin"] as const;
const PLANNING = ["dev", "admin", "buyer", "planner", "supervisor"] as const;
const PRODUCTION = ["dev", "admin", "planner", "supervisor", "operator", "qa", "read_only"] as const;
const QUALITY = ["dev", "admin", "supervisor", "operator", "qa", "read_only"] as const;
const RETAIL = ["dev", "admin", "buyer", "planner", "supervisor", "qa", "read_only"] as const;

/* This list is deliberately broader than the first React migration. Every
   Streamlit destination remains discoverable instead of being collapsed away. */
const navigation: NavigationItem[] = [
  { icon: Gauge, label: "Home", page: "Home" },
  { section: "Retail Ops" },
  { icon: Boxes, label: "Inventory", page: "Inventory", capability: "retail" },
  { icon: BookOpen, label: "Product Master", page: "Retail Product Master", capability: "retail" },
  { icon: ShoppingCart, label: "Purchasing", page: "Purchasing", capability: "retail", roles: PLANNING },
  { icon: BarChart3, label: "Reports & Insights", page: "Reports", capability: "retail", roles: RETAIL },
  { icon: Scale, label: "MA Flower Equivalency", page: "MA Flower Equivalency", capability: "retail", roles: RETAIL },
  { icon: Tags, label: "Nomenclature Mapper", page: "Nomenclature Mapper", capability: "retail", roles: RETAIL },
  { icon: ShieldCheck, label: "Compliance Q&A", page: "Compliance Q&A", capability: "retail", roles: RETAIL },
  { section: "Production Ops" },
  { icon: BookOpen, label: "Product Master", page: "Production Product Master", capability: "production", roles: PRODUCTION },
  { icon: Factory, label: "Production", page: "Production", capability: "production", roles: PRODUCTION },
  { icon: FlaskConical, label: "Extraction", page: "Extraction", capability: "production", roles: PRODUCTION },
  { icon: Combine, label: "White Label / Repack", page: "White Label / Repack", capability: "production", roles: QUALITY },
  { icon: Combine, label: "Package Studio", page: "Package Studio", capability: "production", roles: QUALITY },
  { icon: FileText, label: "Executive Reports", page: "Executive Reports", roles: PLANNING },
  { section: "Commercial Ops" },
  { icon: PackageOpen, label: "Orders & Fulfillment", page: "Orders", capability: "commercial", roles: PLANNING },
  { section: "Compliance & Platform" },
  { icon: ClipboardCheck, label: "Traceability", page: "Compliance", roles: QUALITY },
  { icon: Sparkles, label: "Doobie", page: "Doobie", roles: PLANNING },
  { icon: Settings, label: "Data & Settings", page: "Data & Settings", roles: ADMIN },
  { icon: Plug, label: "Integrations", page: "Integrations" },
  { icon: Users, label: "Users & Access", page: "Admin", roles: ADMIN },
];

export function AppShell({ children, active, onNavigate }: PropsWithChildren<{ active: string; onNavigate: (page: string) => void }>) {
  const client = useQueryClient();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<AccountContext>("/api/v1/account/context", signal) });
  const access = useQuery({ queryKey: ["access-options"], queryFn: ({ signal }) => apiGet<AccessOptions>("/api/v1/account/access-options", signal), enabled: Boolean(context.data) });
  const selectedFacility = context.data?.facilities.find(row => row.id === context.data?.facility_id);
  const selectedOrganization = access.data?.organizations.find(row => row.id === context.data?.organization?.id);

  useEffect(() => {
    if (!navigationOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setNavigationOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [navigationOpen]);

  const navigate = (page: string) => { onNavigate(page); setNavigationOpen(false); };
  const switchOrganization = (organizationId: string) => {
    const organization = access.data?.organizations.find(row => row.id === organizationId);
    const firstFacility = organization?.facilities[0];
    if (!organization || !firstFacility) return;
    localStorage.setItem("buyer-dash-organization", organization.id);
    localStorage.setItem("buyer-dash-facility", firstFacility.id);
    client.clear();
    window.location.reload();
  };
  const switchFacility = (facilityId: string) => {
    localStorage.setItem("buyer-dash-organization", context.data?.organization?.id ?? "");
    localStorage.setItem("buyer-dash-facility", facilityId);
    client.clear();
    window.location.reload();
  };
  const signOut = async () => {
    localStorage.removeItem("buyer-dash-organization");
    localStorage.removeItem("buyer-dash-facility");
    client.clear();
    await supabase?.auth.signOut();
  };

  return (
    <div className="app-shell">
      {navigationOpen ? <button className="navigation-backdrop" aria-label="Close navigation" onClick={() => setNavigationOpen(false)} /> : null}
      <aside className={navigationOpen ? "sidebar open" : "sidebar"} id="primary-navigation" aria-label="Primary navigation">
        <div className="brand"><span>BD</span><strong>Buyer Dash</strong></div>
        <nav>
          {navigation.map((item, index) => {
            if ("section" in item) return <div className="operation-label" key={item.section}>{item.section}</div>;
            if (item.roles && context.data && !item.roles.includes(context.data.user.role)) return null;
            if (item.capability && context.data && !context.data.capabilities[item.capability]) return null;
            const Icon = item.icon;
            return <button className={item.page === active ? "nav-item active" : "nav-item"} key={`${item.page}-${index}`} onClick={() => navigate(item.page)}>
              <Icon size={18} /><span>{item.label}</span>
            </button>;
          })}
        </nav>
      </aside>
      <section className="workspace">
        <header className="topbar">
          <button className="icon-button" aria-label={navigationOpen ? "Close navigation" : "Open navigation"} aria-expanded={navigationOpen} aria-controls="primary-navigation" onClick={() => setNavigationOpen(open => !open)}><Menu size={19} /></button>
          <div className="context"><strong>{context.data?.organization?.name ?? "Buyer Dash"}</strong><span>{selectedFacility?.name ?? "Loading facility…"}</span></div>
          <div className="context-switchers" aria-label="Access Context">
            {context.data?.user.role === "dev" && access.data && access.data.organizations.length > 1 ? <select className="organization-switch" aria-label="Organization" value={context.data.organization?.id ?? ""} onChange={event => switchOrganization(event.target.value)}>{access.data.organizations.map(row => <option value={row.id} key={row.id}>{row.name}{row.slug === "dev-sandbox" ? " · Sandbox" : ""}</option>)}</select> : null}
            {context.data?.facilities.length ? <select className="facility-switch" aria-label="Facility" value={context.data.facility_id} onChange={event => switchFacility(event.target.value)}>{context.data.facilities.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select> : null}
            {selectedOrganization?.slug === "dev-sandbox" ? <span className="access-badge">DEV Sandbox</span> : null}
          </div>
          <button className="user-chip" onClick={signOut}>{context.data?.user.display_name || context.data?.user.email || "Developer"} · {context.data?.user.role ?? "dev"}</button>
        </header>
        <main>{children}</main>
      </section>
    </div>
  );
}
