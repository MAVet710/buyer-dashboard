import { afterEach, describe, expect, it, vi } from "vitest";
import { setMarketingAnalyticsConsent, setMarketingAnalyticsProvider, trackMarketingEvent } from "./marketingAnalytics";

afterEach(() => {
  setMarketingAnalyticsConsent(false);
  setMarketingAnalyticsProvider(null);
  vi.unstubAllGlobals();
});

describe("marketing analytics privacy boundary", () => {
  it("does not collect without explicit consent", () => {
    const track = vi.fn();
    setMarketingAnalyticsProvider({ track });
    trackMarketingEvent("homepage_primary_cta", { placement: "hero" });
    expect(track).not.toHaveBeenCalled();
    setMarketingAnalyticsConsent(true);
    trackMarketingEvent("homepage_primary_cta", { placement: "hero" });
    expect(track).toHaveBeenCalledWith("homepage_primary_cta", { placement: "hero" });
  });
  it.each([{ doNotTrack: "1" }, { globalPrivacyControl: true }])("honors browser privacy signals: %j", (privacy) => {
    vi.stubGlobal("navigator", privacy);
    const track = vi.fn();
    setMarketingAnalyticsProvider({ track });
    setMarketingAnalyticsConsent(true);
    trackMarketingEvent("login_click");
    expect(track).not.toHaveBeenCalled();
  });
  it("drops unknown runtime fields and non-slug content", () => {
    const track = vi.fn();
    setMarketingAnalyticsProvider({ track });
    setMarketingAnalyticsConsent(true);
    const payload = { placement: "hero" as const, item: "person@example.com", email: "person@example.com", url: "https://example.com/?token=private" };
    trackMarketingEvent("beta_apply", payload);
    expect(track).toHaveBeenCalledWith("beta_apply", { placement: "hero" });
  });
  it("allows replacement and removal without queueing or interrupting UI", () => {
    const replacement = vi.fn();
    setMarketingAnalyticsConsent(true);
    setMarketingAnalyticsProvider({ track: () => { throw new Error("provider unavailable"); } });
    expect(() => trackMarketingEvent("faq_expand")).not.toThrow();
    setMarketingAnalyticsProvider({ track: replacement });
    trackMarketingEvent("faq_expand", { item: "metrc" });
    setMarketingAnalyticsProvider(null);
    trackMarketingEvent("faq_expand");
    expect(replacement).toHaveBeenCalledTimes(1);
  });
});
