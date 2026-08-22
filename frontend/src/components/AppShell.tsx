import { BarChart3, BookOpen, Boxes, ClipboardCheck, Combine, Factory, FlaskConical, Gauge, Menu, PackageOpen, Plug, Settings, ShoppingCart, Sparkles, Users } from "lucide-react";
import { useEffect, useState, type PropsWithChildren } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import { supabase } from "../lib/supabase";

type Capability = "retail" | "production" | "cultivation" | "commercial";
type AccountContext = { user: { display_name: string; email: string; role: string }; organization: { id: string; name: string } | null; facility_id: string; capabilities: Record<Capability, boolean>; facilities: { id: string; name: string; code: string }[] };
type NavigationItem = { section: string } | { icon: typeof Gauge; label: string; page: string; capability?: Capability; roles?: readonly string[] };

const ADMIN = ["dev", "admin"] as const;
const PLANNING = ["dev", "admin", "buyer", "planner", "supervisor"] as const;
const PRODUCTION = ["dev", "admin", "planner", "supervisor", "operator", "qa", "read_only"] as const;
const QUALITY = ["dev", "admin", "supervisor", "operator", "qa", "read_only"] as const;

const navigation: NavigationItem[] = [
  { icon: Gauge, label: "Home", page: "Home" },
  { section: "Retail Ops" },
  { icon: Boxes, label: "Inventory", page: "Inventory" },
  { icon: BookOpen, label: "Product Master", page: "Retail Product Master", capability: "retail" },
  { icon: ShoppingCart, label: "Purchasing", page: "Purchasing", capability: "retail", roles: PLANNING },
  { icon: BarChart3, label: "Reports", page: "Reports", capability: "retail" },
  { section: "Production Ops" },
  { icon: BookOpen, label: "Product Master", page: "Production Product Master", capability: "production", roles: PRODUCTION },
  { icon: Factory, label: "Production", page: "Production", capability: "production", roles: PRODUCTION },
  { icon: FlaskConical, label: "Extraction", page: "Extraction", capability: "production", roles: PRODUCTION },
  { icon: Combine, label: "Package Studio", page: "Package Studio", capability: "production", roles: QUALITY },
  { icon: PackageOpen, label: "Orders", page: "Orders", capability: "commercial", roles: PLANNING },
  { icon: ClipboardCheck, label: "Compliance", page: "Compliance", roles: QUALITY },
  { section: "Platform" },
  { icon: Sparkles, label: "Doobie", page: "Doobie", roles: PLANNING },
  { icon: Settings, label: "Data & Settings", page: "Data & Settings", roles: ADMIN },
  { icon: Plug, label: "Integrations", page: "Integrations" },
  { icon: Users, label: "Admin", page: "Admin", roles: ADMIN },
];

export function AppShell({ children, active, onNavigate }: PropsWithChildren<{ active: string; onNavigate: (page: string) => void }>) {
  const client = useQueryClient();
  const [navigationOpen, setNavigationOpen] = useState(false);
  const context = useQuery({ queryKey: ["account-context"], queryFn: ({ signal }) => apiGet<AccountContext>("/api/v1/account/context", signal) });
  const selectedFacility = context.data?.facilities.find(row => row.id === context.data?.facility_id);
  useEffect(() => {
    if (!navigationOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setNavigationOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [navigationOpen]);
  const navigate = (page: string) => { onNavigate(page); setNavigationOpen(false); };
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
          {context.data?.facilities.length ? <select className="facility-switch" value={context.data.facility_id} onChange={event => { localStorage.setItem("buyer-dash-facility", event.target.value); client.clear(); window.location.reload(); }}>{context.data.facilities.map(row => <option value={row.id} key={row.id}>{row.name}</option>)}</select> : null}
          <button className="user-chip" onClick={() => supabase?.auth.signOut()}>{context.data?.user.display_name || context.data?.user.email || "Developer"} · {context.data?.user.role ?? "dev"}</button>
        </header>
        <main>{children}</main>
      </section>
    </div>
  );
}
