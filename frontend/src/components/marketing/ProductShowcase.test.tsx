import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ProductShowcase } from "./ProductShowcase";
import { ProductPreviewDialog } from "./ProductPreviewDialog";

describe("homepage product inspection", () => {
  it("does not mount the dialog or the unselected screenshot on initial render", () => {
    const html = renderToStaticMarkup(<ProductShowcase />);
    expect(html).not.toContain("<dialog");
    expect(html).not.toContain("inventory-workspace.webp");
    expect(html.match(/<img\b/g)).toHaveLength(1);
  });

  it("keeps original image links as a fallback and labels the preview controls", () => {
    const html = renderToStaticMarkup(<ProductShowcase />);
    expect(html).toContain('href="/marketing/buyer-workspace.webp"');
    expect(html).toContain('aria-haspopup="dialog"');
    expect(html).toContain('aria-label="Choose product preview"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('srcSet="/marketing/buyer-workspace-480.webp 480w');
  });

  it("retains honest product context and synthetic-data disclosure", () => {
    const html = renderToStaticMarkup(<ProductShowcase />);
    expect(html).toContain("Actual product interface · Synthetic demo data · Beta");
    expect(html).toContain("See the buying picture.");
    expect(html).toContain("Review inventory pressure and purchasing context in the actual beta workspace.");
  });

  it("renders a labelled viewer with close, zoom, original-image and beta controls", () => {
    const html = renderToStaticMarkup(
      <ProductPreviewDialog
        name="Buyer workspace"
        image="buyer-workspace.webp"
        alt="Synthetic buyer screenshot"
        description="Review the buying picture."
        onClose={() => undefined}
      />,
    );
    expect(html).toContain("<dialog");
    expect(html).toContain("aria-labelledby=");
    expect(html).toContain("aria-describedby=");
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('aria-label="Close product preview"');
    expect(html).toContain("Zoom to full detail");
    expect(html).toContain("not a live workspace.");
    expect(html).toContain('aria-label="Open original Buyer workspace screenshot in a new tab"');
    expect(html).toContain('href="/beta#apply"');
  });
});
