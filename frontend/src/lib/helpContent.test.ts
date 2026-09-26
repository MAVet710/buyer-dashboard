import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { helpArticleByPath, helpArticles, helpCategories, helpSearch } from "./helpContent";
import { seoPage } from "./seo";

describe("DoobieLogic Help Center content contract", () => {
  it("publishes unique help routes with public SEO metadata", () => {
    const paths = helpArticles.map(article => article.path);
    expect(new Set(paths).size).toBe(paths.length);
    expect(paths.length).toBeGreaterThanOrEqual(40);
    for (const path of paths) {
      expect(path.startsWith("/help/")).toBe(true);
      expect(seoPage(true, path)).toMatchObject({ publicPage: true, canonical: `https://doobielogic.io${path}` });
    }
  });

  it("keeps every category link backed by a real article", () => {
    for (const category of helpCategories) {
      expect(category.articles.length).toBeGreaterThan(0);
      for (const path of category.articles) expect(helpArticleByPath.has(path)).toBe(true);
    }
  });

  it("uses a genuinely different real-workspace capture for every guide", () => {
    const screenshots = helpArticles.map(article => article.screenshot);
    const digests = new Set<string>();
    expect(new Set(screenshots).size).toBe(helpArticles.length);
    for (const article of helpArticles) {
      expect(article.screenshot).toMatch(/^\/help\/screens\/[a-z0-9-]+-guide\.webp$/);
      const file = new URL(`../../public${article.screenshot}`, import.meta.url);
      expect(existsSync(file)).toBe(true);
      const bytes = readFileSync(file);
      expect(bytes.length).toBeGreaterThan(10_000);
      digests.add(createHash("sha256").update(bytes).digest("hex"));
    }
    expect(digests.size).toBe(helpArticles.length);
  });

  it("searches across titles, tasks, navigation, and step text", () => {
    expect(helpSearch("receive inventory").some(article => article.path === "/help/inventory/receiving")).toBe(true);
    expect(helpSearch("Metrc").some(article => article.path === "/help/settings/integrations")).toBe(true);
    expect(helpSearch("label history").some(article => article.path === "/help/compliance/label-studio")).toBe(true);
  });
});
