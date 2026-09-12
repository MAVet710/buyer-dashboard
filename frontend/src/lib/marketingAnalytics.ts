/** No provider, persistence, identifiers, or network requests are installed by default.
 * Configure an adapter and explicit consent before collection. Never pass form values.
 */
export const MARKETING_EVENTS = [
  "homepage_primary_cta", "homepage_secondary_cta", "solution_cultivation",
  "solution_production", "solution_retail", "solution_vertical", "product_tour_start",
  "integration_view", "faq_expand", "beta_apply", "login_click",
] as const;
export type MarketingEventName = typeof MARKETING_EVENTS[number];
export type MarketingEventContext = {
  placement?: "navigation" | "hero" | "product" | "solutions" | "integrations" | "trust" | "faq" | "final" | "footer" | "beta";
  /** Fixed content slug only; never user input, URL, query string, or personal data. */
  item?: string;
};
export interface MarketingAnalyticsProvider {
  track(name: MarketingEventName, context: Readonly<MarketingEventContext>): void | Promise<void>;
}
let provider: MarketingAnalyticsProvider | null = null;
let consent = false;

export function setMarketingAnalyticsProvider(next: MarketingAnalyticsProvider | null): void {
  provider = next;
}

export function setMarketingAnalyticsConsent(allowed: boolean): void {
  consent = allowed;
}

export function trackMarketingEvent(name: MarketingEventName, context: MarketingEventContext = {}): void {
  const privacy = typeof navigator === "undefined" ? undefined : navigator as Navigator & { globalPrivacyControl?: boolean };
  if (!provider || !consent || privacy?.doNotTrack === "1" || privacy?.globalPrivacyControl) return;
  if (!MARKETING_EVENTS.includes(name)) return;
  // Construct the payload explicitly so arbitrary runtime fields cannot escape.
  const payload: MarketingEventContext = {};
  if (context.placement && ["navigation", "hero", "product", "solutions", "integrations", "trust", "faq", "final", "footer", "beta"].includes(context.placement)) {
    payload.placement = context.placement;
  }
  if (context.item && /^[a-z][a-z0-9-]{0,63}$/.test(context.item)) payload.item = context.item;
  try {
    void Promise.resolve(provider.track(name, Object.freeze(payload))).catch(() => undefined);
  } catch {
    // Analytics must never block navigation or the beta conversion path.
  }
}
