import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { marketingFaqs } from "../components/marketing/content";
import { MARKETING_DESCRIPTION, MARKETING_TITLE, marketingStructuredData, seoPage } from "./seo";

describe("public marketing SEO and private boundaries", () => {
  it("indexes the homepage with a canonical URL and transparent beta positioning", () => {
    expect(seoPage(true, "/")).toMatchObject({ publicPage: true, canonical: "https://doobielogic.io/", title: MARKETING_TITLE });
    expect(seoPage(true, "/").robots).not.toContain("noindex");
    expect(MARKETING_DESCRIPTION).toContain("in beta");
  });
  it("gives beta its own canonical and excludes homepage FAQ markup", () => {
    expect(seoPage(true, "/beta/")).toMatchObject({ canonical: "https://doobielogic.io/beta", homepage: false });
  });
  it.each([[false, "/"], [false, "/inventory"], [true, "/portal/private-token"], [true, "/store/demo"]] as const)("keeps private workspace metadata private (%s, %s)", (marketing, path) => {
    expect(seoPage(marketing, path)).toMatchObject({ publicPage: false, canonical: null, homepage: false });
    expect(seoPage(marketing, path).robots).toContain("noindex");
  });
  it("uses visible FAQ content and omits unsupported schema claims", () => {
    const data = marketingStructuredData();
    const faq = data["@graph"].find((entry) => entry["@type"] === "FAQPage");
    expect(faq?.mainEntity).toEqual(marketingFaqs.map(({ question, answer }) => ({ "@type": "Question", name: question, acceptedAnswer: { "@type": "Answer", text: answer } })));
    expect(JSON.stringify(data)).not.toMatch(/aggregateRating|reviewCount|price|featureList/);
    expect(data["@graph"].map((entry) => entry["@type"])).toEqual(["Organization", "SoftwareApplication", "FAQPage"]);
  });
  it("keeps sitemap discovery public and excludes workspace URLs", () => {
    const sitemap = readFileSync(new URL("../../public/sitemap.xml", import.meta.url), "utf8");
    const nginx = readFileSync(new URL("../../nginx.conf", import.meta.url), "utf8");
    expect(sitemap).toContain("https://doobielogic.io/beta");
    expect(sitemap).not.toMatch(/ops\.doobielogic|\/portal\//);
    expect(nginx).toContain("Sitemap: https://doobielogic.io/sitemap.xml");
    expect(nginx).toContain('0 "User-agent: *\\nDisallow: /\\n"');
  });
});
