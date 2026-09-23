import { ADVISORY_EVENTS, setMarketingAnalyticsConsent, setMarketingAnalyticsProvider } from "./marketingAnalytics";

const CONSENT_KEY = "doobielogic.analytics-consent";
const ATTRIBUTION_KEY = "doobielogic.advisory-attribution";
export interface AdvisoryAttribution {
  landing_page?: string; referrer?: string; utm_source?: string; utm_medium?: string;
  utm_campaign?: string; utm_term?: string; utm_content?: string;
}
const UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"] as const;
// Fixed public routes only: never retain a portal token, arbitrary path or query string.
const PUBLIC_PATH = /^\/(?:consulting(?:\/(?:inventory-profit-audit|fractional-purchasing|compliance-operational-audit|sop-workflow-development|metrc-technology|production-extraction|operational-diagnostic))?|resources(?:\/(?:days-on-hand-for-cannabis-inventory|inventory-reconciliation-checklist|metrc-api-readiness-checklist))?|tools\/(?:operations-score|inventory-health-check)|beta)?\/?$/;
export function sanitizeAdvisoryAttribution(value: AdvisoryAttribution): AdvisoryAttribution {
  const clean: AdvisoryAttribution = {};
  if (typeof value.landing_page === "string" && PUBLIC_PATH.test(value.landing_page)) clean.landing_page = value.landing_page;
  if (typeof value.referrer === "string") {
    try { const url = new URL(value.referrer); if (["https:", "http:"].includes(url.protocol)) clean.referrer = url.origin; } catch { /* Invalid referrer omitted. */ }
  }
  for (const key of UTM_KEYS) {
    const text = value[key];
    // Campaign labels only, not arbitrary URLs, emails or credential-like strings.
    if (typeof text === "string" && /^[a-zA-Z0-9][a-zA-Z0-9 _.-]{0,99}$/.test(text) && !/(?:token|secret|password|bearer|api.?key|eyJ)/i.test(text)) clean[key] = text;
  }
  return clean;
}
function captureCurrent(): AdvisoryAttribution {
  if (typeof window === "undefined") return {};
  const query = new URLSearchParams(window.location.search);
  const candidate: AdvisoryAttribution = { landing_page: window.location.pathname, referrer: typeof document === "undefined" ? undefined : document.referrer };
  for (const key of UTM_KEYS) candidate[key] = query.get(key) ?? undefined;
  return sanitizeAdvisoryAttribution(candidate);
}
let firstTouch: AdvisoryAttribution | undefined;
export function advisoryPrivacyBlocked(): boolean {
  const privacy = typeof navigator === "undefined" ? undefined : navigator as Navigator & { globalPrivacyControl?: boolean };
  return privacy?.doNotTrack === "1" || privacy?.globalPrivacyControl === true;
}
export function getAdvisoryAnalyticsConsent(): boolean {
  if (advisoryPrivacyBlocked()) return false;
  try { return localStorage.getItem(CONSENT_KEY) === "true"; } catch { return false; }
}
export function setAdvisoryAnalyticsConsent(allowed: boolean): void {
  const effective = allowed && !advisoryPrivacyBlocked();
  setMarketingAnalyticsConsent(effective);
  try { localStorage.setItem(CONSENT_KEY, String(effective)); } catch { /* Storage is optional. */ }
  try {
    if (effective) sessionStorage.setItem(ATTRIBUTION_KEY, JSON.stringify(firstTouch ?? captureCurrent()));
    else sessionStorage.removeItem(ATTRIBUTION_KEY);
  } catch { /* Storage is optional. */ }
}
/** Call only when submitting a lead with its separate explicit contact consent.
 * No analytics opt-in means no persisted cross-page attribution; current-page data only.
 */
export function getAdvisoryAttribution(): AdvisoryAttribution {
  if (advisoryPrivacyBlocked()) return {};
  if (getAdvisoryAnalyticsConsent()) {
    try { const raw = sessionStorage.getItem(ATTRIBUTION_KEY); if (raw) return sanitizeAdvisoryAttribution(JSON.parse(raw) as AdvisoryAttribution); } catch { /* Fall back to memory. */ }
  }
  return sanitizeAdvisoryAttribution(firstTouch ?? captureCurrent());
}
export function initializeAdvisoryAnalytics(): void {
  firstTouch ??= captureCurrent();
  setMarketingAnalyticsProvider({
    async track(event, context) {
      if (!ADVISORY_EVENTS.some(name => name === event) || !getAdvisoryAnalyticsConsent()) return;
      await fetch(`${import.meta.env.VITE_API_URL ?? ""}/api/v1/advisory/events`, {
        method: "POST", credentials: "omit", referrerPolicy: "no-referrer", keepalive: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event, placement: context.placement ?? "consulting", ...(context.item ? { item: context.item } : {}), consent: true }),
      });
    },
  });
  setMarketingAnalyticsConsent(getAdvisoryAnalyticsConsent());
}
