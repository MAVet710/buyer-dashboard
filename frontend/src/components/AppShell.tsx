import { BarChart3, BookOpen, Boxes, ClipboardCheck, Combine, DollarSign, Factory, FileText, FlaskConical, Gauge, Menu, Moon, PackageOpen, Plug, Scale, Settings, ShieldCheck, ShoppingCart, Sparkles, Sun, Tags, Truck, Users, Wrench } from "lucide-react";
import { useEffect, useState, type PropsWithChildren } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, clearTrialSession } from "../lib/api";
import { supabase } from "../lib/supabase";

type Capability = "retail" | "production" | "cultivation" | "commercial";
type Facility = { id: string; name: string; code: string; license_type?: string; capabilities?: Record<Capability, boolean> };
type AccessOrganization = { id: string; name: string; slug: string; facilities: Facility[] };
type AccountContext = { user: { display_name: string; email: string; role: string; must_change_password?: boolean }; organization: { id: string; name: string; slug?: string } | null; facility_id: string; capabilities: Record<Capability, boolean>; facilities: Facility[] };
type AccessOptions = { organizations: AccessOrganization[]; organization_id: string; facility_id: string };
type NavigationLink = { icon: typeof Gauge; label: string; page: string; capability?: Capability; roles?: readonly string[] };
type NavigationItem = { section: string } | NavigationLink;

const DEV = ["dev"] as const;
const NON_DEV = ["admin", "buyer", "planner", "supervisor", "operator", "qa", "read_only"] as const;
const ADMIN = ["dev", "admin"] as const;
const DATA_ACCESS = ["dev", "admin", "buyer", "planner", "supervisor", "operator", "qa", "read_only", "trial"] as const;
const PLANNING = ["dev", "admin", "buyer", "planner", "supervisor", "trial"] as const;
const PRODUCTION = ["dev", "admin", "planner", "supervisor", "operator", "qa", "read_only", "trial"] as const;
const QUALITY = ["dev", "admin", "supervisor", "operator", "qa", "read_only", "trial"] as const;
const RETAIL = ["dev", "admin", "buyer", "planner", "supervisor", "qa", "read_only", "trial"] as const;

const navigation: NavigationItem[] = [
  { icon: Gauge, label: "Home", page: "Home" },
  { section: "Buyer Operations" },
  { icon: Gauge, label: "Buyer Operations", page: "Buyer Operations", capability: "retail", roles: RETAIL },
  { icon: Boxes, label: "Inventory", page: "Inventory", capability: "retail" },
  { icon: ClipboardCheck, label: "Inventory Audits", page: "Inventory Audits", capability: "retail" },
  { icon: BarChart3, label: "Slow Movers", page: "Slow Movers", capability: "retail", roles: RETAIL },
  { icon: Scale, label: "MA Flower Equivalency", page: "MA Flower Equivalency", capability: "retail", roles: RETAIL },
  { icon: Sparkles, label: "Buying Recommendations", page: "Buying Recommendations", capability: "retail", roles: PLANNING },
  { icon: Truck, label: "Delivery Performance", page: "Delivery Performance", capability: "retail", roles: RETAIL },
  { icon: ShoppingCart, label: "Purchase Orders", page: "Purchase Orders", capability: "retail", roles: PLANNING },
  { icon: DollarSign, label: "Buying Budget", page: "Buying Budget", capability: "retail", roles: PLANNING },
  { icon: BarChart3, label: "Sales & Category Trends", page: "Sales & Category Trends", capability: "retail", roles: RETAIL },
  { icon: BookOpen, label: "Product Master", page: "Retail Product Master", capability: "retail" },
  { icon: Tags, label: "Product Name Mapper", page: "Product Name Mapper", capability: "retail", roles: RETAIL },
  { icon: ShieldCheck, label: "Compliance Q&A", page: "Compliance Q&A", capability: "retail", roles: RETAIL },
  { icon: FileText, label: "Executive Reports", page: "Executive Reports", roles: PLANNING },
  { section: "Production Ops" },
  { icon: BookOpen, label: "Product Master", page: "Production Product Master", capability: "production", roles: PRODUCTION },
  { icon: Factory, label: "Production", page: "Production", capability: "production", roles: PRODUCTION },
  { icon: FlaskConical, label: "Extraction", page: "Extraction", capability: "production", roles: PRODUCTION },
  { icon: Combine, label: "White Label / Repack", page: "White Label / Repack", capability: "production", roles: QUALITY },
  { icon: Combine, label: "Package Studio", page: "Package Studio", capability: "production", roles: QUALITY },
  { section: "Commercial Ops" },
  { icon: PackageOpen, label: "Orders & Fulfillment", page: "Orders", capability: "commercial", roles: PLANNING },
  { section: "Compliance & Platform" },
  { icon: ClipboardCheck, label: "Traceability", page: "Compliance", roles: QUALITY },
  { icon: Sparkles, label: "Doobie", page: "Doobie", roles: PLANNING },
  { icon: Wrench, label: "Admin Tools", page: "Admin", roles: ADMIN },
  { icon: Plug, label: "AI & METRC Integrations", page: "Integrations", roles: DEV },
  { icon: Plug, label: "METRC Integrations", page: "Integrations", roles: NON_DEV },
  { icon: Settings, label: "Data & Settings", page: "Data & Settings", roles: DATA_ACCESS },
  { icon: Users, label: "Users & Access", page: "Admin", roles: ADMIN },
];

export function AppShell({ children, active, onNavigate }: PropsWithChildren<{ active: string; onNavigate: (page: string) => void }>) {
  const client = useQueryClient();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">(() => localStorage.getItem("buyer-dash-theme") === "light" ? "light" : "dark");
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<AccountContext>("/api/v1/account/context", signal) });
  const access = useQuery({ queryKey: ["access-options"], queryFn: ({ signal }) => apiGet<AccessOptions>("/api/v1/account/access-options", signal), enabled: Boolean(context.data) });
  const selectedFacility = context.data?.facilities.find(row => row.id === context.data?.facility_id);
  const selectedOrganization = access.data?.organizations.find(row => row.id === context.data?.organization?.id);
  const isTrial = context.data?.user.role === "trial";

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("buyer-dash-theme", theme); }, [theme]);
  useEffect(() => { if (!navigationOpen) return; const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setNavigationOpen(false); }; window.addEventListener("keydown", closeOnEscape); return () => window.removeEventListener("keydown", closeOnEscape); }, [navigationOpen]);

  const navigate = (page: string) => { onNavigate(page); setNavigationOpen(false); };
  const findCapabilityTarget = (capability: Capability): { organizationId: string; facilityId: string } | null => {
    if (!context.data || isTrial) return null;
    if (context.data.capabilities[capability]) return { organizationId: context.data.organization?.id ?? "", facilityId: context.data.facility_id };
    const organizations = access.data?.organizations ?? [];
    const currentOrganizationId = context.data.organization?.id ?? "";
    const currentOrganization = organizations.find(row => row.id === currentOrganizationId);
    const currentFacility = currentOrganization?.facilities.find(row => Boolean(row.capabilities?.[capability]));
    if (currentOrganization && currentFacility) return { organizationId: currentOrganization.id, facilityId: currentFacility.id };
    if (context.data.user.role === "dev") {
      for (const organization of organizations) {
        const facility = organization.facilities.find(row => Boolean(row.capabilities?.[capability]));
        if (facility) return { organizationId: organization.id, facilityId: facility.id };
      }
    }
    return null;
  };
  const capabilityAvailable = (capability: Capability): boolean => {
    if (!context.data) return true;
    if (context.data.capabilities[capability]) return true;
    return Boolean(findCapabilityTarget(capability));
  };
  const navigateItem = (item: NavigationLink) => {
    if (item.capability && context.data && !context.data.capabilities[item.capability]) {
      const target = findCapabilityTarget(item.capability);
      if (target) {
        sessionStorage.setItem("buyer-dash-pending-page", item.page);
        localStorage.setItem("buyer-dash-organization", target.organizationId);
        localStorage.setItem("buyer-dash-facility", target.facilityId);
        client.clear();
        window.location.reload();
        return;
      }
    }
    navigate(item.page);
  };
  const switchOrganization = (organizationId: string) => { if (isTrial) return; const organization = access.data?.organizations.find(row => row.id === organizationId); const firstFacility = organization?.facilities[0]; if (!organization || !firstFacility) return; localStorage.setItem("buyer-dash-organization", organization.id); localStorage.setItem("buyer-dash-facility", firstFacility.id); client.clear(); window.location.reload(); };
  const switchFacility = (facilityId: string) => { if (isTrial) return; localStorage.setItem("buyer-dash-organization", context.data?.organization?.id ?? ""); localStorage.setItem("buyer-dash-facility", facilityId); client.clear(); window.location.reload(); };
  const signOut = async () => { localStorage.removeItem("buyer-dash-organization"); localStorage.removeItem("buyer-dash-facility"); sessionStorage.removeItem("buyer-dash-pending-page"); clearTrialSession(); client.clear(); if (isTrial) { window.location.reload(); return; } await supabase?.auth.signOut(); };

  return <div className="app-shell">{navigationOpen ? <button className="navigation-backdrop" aria-label="Close navigation" onClick={() => setNavigationOpen(false)} /> : null}<aside className={navigationOpen ? "sidebar open" : "sidebar"} id="primary-navigation" aria-label="Primary navigation"><div className="brand"><span>BD</span><strong>Buyer Dash</strong></div><nav>{navigation.map((item,index) => { if ("section" in item) return <div className="operation-label" key={item.section}>{item.section}</div>; if (item.roles && context.data && !item.roles.includes(context.data.user.role)) return null; if (item.capability && !capabilityAvailable(item.capability)) return null; const Icon=item.icon; return <button className={item.page===active?"nav-item active":"nav-item"} key={`${item.page}-${index}`} onClick={()=>navigateItem(item)}><Icon size={18}/><span>{item.label}</span></button>; })}</nav></aside><section className="workspace"><header className="topbar"><button className="icon-button" aria-label={navigationOpen?"Close navigation":"Open navigation"} aria-expanded={navigationOpen} aria-controls="primary-navigation" onClick={()=>setNavigationOpen(open=>!open)}><Menu size={19}/></button><div className="context"><strong>{context.data?.organization?.name??"Buyer Dash"}</strong><span>{selectedFacility?.name??"Loading facility…"}</span></div><div className="context-switchers" aria-label="Access Context">{context.data?.user.role==="dev"&&access.data&&access.data.organizations.length>1?<select className="organization-switch" aria-label="Organization" value={context.data.organization?.id??""} onChange={event=>switchOrganization(event.target.value)}>{access.data.organizations.map(row=><option value={row.id} key={row.id}>{row.name}{row.slug==="dev-sandbox"?" · Sandbox":""}</option>)}</select>:null}{!isTrial&&context.data?.facilities.length?<select className="facility-switch" aria-label="Facility" value={context.data.facility_id} onChange={event=>switchFacility(event.target.value)}>{context.data.facilities.map(row=><option value={row.id} key={row.id}>{row.name}</option>)}</select>:null}{selectedOrganization?.slug==="dev-sandbox"?<span className="access-badge">{isTrial?"24-hour Trial":"DEV Sandbox"}</span>:null}</div><button className="icon-button theme-toggle" title={`Switch to ${theme==="dark"?"light":"dark"} theme`} aria-label={`Switch to ${theme==="dark"?"light":"dark"} theme`} onClick={()=>setTheme(current=>current==="dark"?"light":"dark")}>{theme==="dark"?<Sun size={18}/>:<Moon size={18}/>}</button><button className="user-chip" onClick={signOut}>{context.data?.user.display_name||context.data?.user.email||"Developer"} · {context.data?.user.role??"dev"}</button></header><main>{children}</main></section></div>;
}
