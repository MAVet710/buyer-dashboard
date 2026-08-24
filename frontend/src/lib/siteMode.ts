const PUBLIC_MARKETING_HOSTS = new Set(["doobielogic.io", "www.doobielogic.io"]);

export function isMarketingHost(hostname: string): boolean {
  const normalized = String(hostname || "").trim().toLowerCase().replace(/\.$/, "");
  return PUBLIC_MARKETING_HOSTS.has(normalized);
}
