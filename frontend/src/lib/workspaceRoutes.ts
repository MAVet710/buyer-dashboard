export type WorkspaceEntityContext = {
  kind: "product" | "package" | "production-run" | "compliance-issue";
  id: string;
};

type RouteEntry = {
  page: string;
  path: string;
  aliases?: string[];
};

const ROUTES: RouteEntry[] = [
  { page: "Home", path: "/home", aliases: ["/"] },
  { page: "Operations Control Tower", path: "/home/control-tower" },
  { page: "Enterprise Control Tower", path: "/home/enterprise" },

  { page: "Buyer Operations", path: "/buying", aliases: ["/purchasing"] },
  { page: "Purchasing", path: "/buying" },
  { page: "Buying Recommendations", path: "/buying/recommendations" },
  { page: "Delivery Performance", path: "/buying/delivery-performance" },
  { page: "Purchase Orders", path: "/buying/purchase-orders" },
  { page: "Buying Budget", path: "/buying/budget" },
  { page: "Replenishment Policies", path: "/buying/planning-settings" },

  { page: "Inventory", path: "/inventory" },
  { page: "Inventory Audits", path: "/inventory/audits" },
  { page: "Retail Product 360", path: "/inventory/products" },
  { page: "Retail Product Master", path: "/inventory/products" },
  { page: "Package 360", path: "/inventory/packages" },
  { page: "Retail Catalog Admin", path: "/inventory/catalog" },
  { page: "Slow Movers", path: "/inventory/slow-movers" },

  { page: "Production Inventory", path: "/production/inventory" },
  { page: "Production Product Master", path: "/production/products" },
  { page: "Production", path: "/production" },
  { page: "Production Calendar", path: "/production/calendar" },
  { page: "Production Run 360", path: "/production/runs" },
  { page: "Extraction", path: "/production/extraction" },
  { page: "White Label / Repack", path: "/production/repack" },
  { page: "Package Studio", path: "/production/package-studio" },
  { page: "Orders", path: "/production/orders" },
  { page: "Warehouse Pick Pack", path: "/production/fulfillment" },

  { page: "Compliance", path: "/compliance" },
  { page: "Traceability Actions", path: "/compliance/actions" },
  { page: "Compliance Q&A", path: "/compliance/qa" },
  { page: "Label Studio", path: "/compliance/labels" },
  { page: "MA Flower Equivalency", path: "/compliance/ma-flower-equivalency" },
  { page: "Product Name Mapper", path: "/compliance/nomenclature" },
  { page: "Nomenclature Mapper", path: "/compliance/nomenclature" },

  { page: "Reports", path: "/reports" },
  { page: "Sales & Category Trends", path: "/reports/sales-category-trends" },
  { page: "Executive Reports", path: "/reports/executive" },

  { page: "Data & Settings", path: "/settings/data" },
  { page: "Location Settings", path: "/settings/location" },
  { page: "Admin", path: "/settings/admin" },
  { page: "Admin Tools", path: "/settings/admin" },
  { page: "Integrations", path: "/settings/integrations" },
  { page: "AI & METRC Integrations", path: "/settings/integrations" },
  { page: "METRC Integrations", path: "/settings/integrations" },

  // Kept as a compatibility route. Doobie Agent remains available as a
  // persistent contextual pop-out and is not dependent on this standalone page.
  { page: "Doobie", path: "/doobie" },
];

const normalize = (path: string): string => {
  if (!path) return "/";
  const withoutQuery = path.split("?", 1)[0].split("#", 1)[0];
  if (withoutQuery === "/") return "/";
  return withoutQuery.replace(/\/+$/, "") || "/";
};

const exactPageByPath = new Map<string, string>();
for (const entry of ROUTES) {
  if (!exactPageByPath.has(entry.path)) exactPageByPath.set(entry.path, entry.page);
  for (const alias of entry.aliases ?? []) {
    if (!exactPageByPath.has(alias)) exactPageByPath.set(alias, entry.page);
  }
}

const canonicalPathByPage = new Map(ROUTES.map(entry => [entry.page, entry.path]));

export function pageForPath(pathname: string): string | null {
  const path = normalize(pathname);
  const exact = exactPageByPath.get(path);
  if (exact) return exact;
  if (/^\/inventory\/products\/[^/]+$/.test(path)) return "Retail Product 360";
  if (/^\/inventory\/packages\/[^/]+$/.test(path)) return "Package 360";
  if (/^\/production\/runs\/[^/]+$/.test(path)) return "Production Run 360";
  if (/^\/compliance\/issues\/[^/]+$/.test(path)) return "Compliance";
  return null;
}

export function pathForPage(page: string): string {
  return canonicalPathByPage.get(page) ?? `/workspace/${encodeURIComponent(page)}`;
}

export function entityContextForPath(pathname: string): WorkspaceEntityContext | null {
  const path = normalize(pathname);
  const patterns: Array<{ regex: RegExp; kind: WorkspaceEntityContext["kind"] }> = [
    { regex: /^\/inventory\/products\/([^/]+)$/, kind: "product" },
    { regex: /^\/inventory\/packages\/([^/]+)$/, kind: "package" },
    { regex: /^\/production\/runs\/([^/]+)$/, kind: "production-run" },
    { regex: /^\/compliance\/issues\/([^/]+)$/, kind: "compliance-issue" },
  ];
  for (const pattern of patterns) {
    const match = path.match(pattern.regex);
    if (match) return { kind: pattern.kind, id: decodeURIComponent(match[1]) };
  }
  return null;
}

export function canonicalWorkspaceRoutes(): ReadonlyArray<RouteEntry> {
  return ROUTES;
}
