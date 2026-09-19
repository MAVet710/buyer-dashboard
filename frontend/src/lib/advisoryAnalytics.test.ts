import { afterEach, describe, expect, it, vi } from "vitest";
import { getAdvisoryAttribution, initializeAdvisoryAnalytics, sanitizeAdvisoryAttribution, setAdvisoryAnalyticsConsent } from "./advisoryAnalytics";
import { setMarketingAnalyticsConsent, setMarketingAnalyticsProvider, trackMarketingEvent } from "./marketingAnalytics";

const memoryStorage = () => { const values = new Map<string, string>(); return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); }, removeItem: (key: string) => { values.delete(key); } }; };
afterEach(() => { setMarketingAnalyticsConsent(false); setMarketingAnalyticsProvider(null); vi.unstubAllGlobals(); });
describe("advisory first-party measurement", () => {
  it("sends only the approved event contract after consent and stops on withdrawal", async () => {
    vi.stubGlobal("localStorage", memoryStorage()); vi.stubGlobal("sessionStorage", memoryStorage());
    const fetch = vi.fn().mockResolvedValue({ ok: true }); vi.stubGlobal("fetch", fetch);
    initializeAdvisoryAnalytics();
    trackMarketingEvent("consultation_cta_clicked", { placement: "hero" });
    expect(fetch).not.toHaveBeenCalled();
    setAdvisoryAnalyticsConsent(true);
    trackMarketingEvent("consultation_cta_clicked", { placement: "hero", item: "inventory-profit-audit" });
    expect(fetch).toHaveBeenCalledTimes(1);
    const options = fetch.mock.calls[0][1];
    expect(JSON.parse(options.body)).toEqual({ event: "consultation_cta_clicked", placement: "hero", item: "inventory-profit-audit", consent: true });
    expect(options).toMatchObject({ credentials: "omit", referrerPolicy: "no-referrer" });
    setAdvisoryAnalyticsConsent(false);
    trackMarketingEvent("consultation_form_submitted");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("honors privacy signals for attribution as well as measurement", () => {
    vi.stubGlobal("navigator", { globalPrivacyControl: true });
    expect(getAdvisoryAttribution()).toEqual({});
  });
  it("keeps only public paths, referrer origins and bounded campaign labels", () => {
    expect(sanitizeAdvisoryAttribution({ landing_page: "/consulting", referrer: "https://user:pass@example.com/private?token=secret#part", utm_source: "trade-news", utm_campaign: "Fall 2026", utm_term: "person@example.com", utm_content: "api-key-secret" })).toEqual({ landing_page: "/consulting", referrer: "https://example.com", utm_source: "trade-news", utm_campaign: "Fall 2026" });
    expect(sanitizeAdvisoryAttribution({ utm_source: "a".repeat(100) })).toEqual({ utm_source: "a".repeat(100) });
    expect(sanitizeAdvisoryAttribution({ landing_page: "/portal/private-token", utm_source: "a".repeat(101), referrer: "javascript:alert(1)" })).toEqual({});
  });
});
