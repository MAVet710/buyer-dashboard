import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

const source=readFileSync(new URL("./StorefrontPage.tsx",import.meta.url),"utf8");

describe("Storefront input focus regression",()=>{
  it("renders local storefront helpers as functions instead of remounting inline components",()=>{
    expect(source).toContain("{Controls()}");
    expect(source).toContain("{OrderStatus()}{SectionFlow()}");
    expect(source).toContain("{Catalog()}{Cart()}");
    expect(source).not.toContain("<Controls/>");
    expect(source).not.toContain("<Cart/>");
    expect(source).not.toContain("<OrderStatus/>");
    expect(source).not.toContain("<SectionFlow/>");
  });

  it("uses the star line for strain type instead of product category",()=>{
    expect(source).toContain("<small>{strainTypeLabel(item)}</small>");
    expect(source).toContain('"Sativa Hybrid"');
    expect(source).toContain('"Indica Hybrid"');
  });
});
