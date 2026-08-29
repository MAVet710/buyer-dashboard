import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const gateSource = readFileSync(new URL("./components/PublicStorefrontAgeGate.tsx", import.meta.url), "utf8");
const mainSource = readFileSync(new URL("./main.tsx", import.meta.url), "utf8");

describe("public wholesale storefront age gate", () => {
  it("wraps every public storefront before StorefrontPage mounts", () => {
    expect(mainSource).toContain("<PublicStorefrontAgeGate><StorefrontPage slug={storefrontSlug} /></PublicStorefrontAgeGate>");
  });

  it("requires affirmative 21+ self-attestation and preserves the licensed-buyer boundary", () => {
    expect(gateSource).toContain("I am 21 or older");
    expect(gateSource).toContain("I am under 21");
    expect(gateSource).toContain("Age confirmation does not replace cannabis-license verification or supplier approval");
  });

  it("persists confirmed adults but keeps an under-21 denial session scoped", () => {
    expect(gateSource).toContain("window.localStorage.setItem(AGE_GATE_KEY, \"confirmed\")");
    expect(gateSource).toContain("window.sessionStorage.setItem(`${AGE_GATE_KEY}:denied`, \"1\")");
  });
});
