export type RecentWorkspace = {
  page: string;
  path: string;
  visited_at: string;
};

const PREFIX = "doobielogic-recent-workspaces";
const MAX_RECENT = 5;

function key(organizationId?: string | null, facilityId?: string | null): string {
  const organization = organizationId || localStorage.getItem("buyer-dash-organization") || "current-org";
  const facility = facilityId || localStorage.getItem("buyer-dash-facility") || "current-facility";
  return `${PREFIX}:${organization}|${facility}`;
}

function parse(value: string | null): RecentWorkspace[] {
  try {
    const rows = JSON.parse(value || "[]") as RecentWorkspace[];
    if (!Array.isArray(rows)) return [];
    return rows.filter(row => row && typeof row.page === "string" && typeof row.path === "string" && typeof row.visited_at === "string").slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

export function rememberWorkspace(page: string, path: string): void {
  if (!page || page === "Home" || !path || path === "/" || path === "/home") return;
  try {
    const storageKey = key();
    const current = parse(sessionStorage.getItem(storageKey));
    const next: RecentWorkspace[] = [
      { page, path, visited_at: new Date().toISOString() },
      ...current.filter(row => row.page !== page && row.path !== path),
    ].slice(0, MAX_RECENT);
    sessionStorage.setItem(storageKey, JSON.stringify(next));
  } catch {
    // Session storage can be unavailable in hardened browser contexts.
  }
}

export function readRecentWorkspaces(organizationId?: string | null, facilityId?: string | null): RecentWorkspace[] {
  try {
    return parse(sessionStorage.getItem(key(organizationId, facilityId)));
  } catch {
    return [];
  }
}
