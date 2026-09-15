import { useCallback, useState, type MouseEvent } from "react";
import { ArrowUpRight, ChartNoAxesCombined, PackageSearch } from "lucide-react";
import { trackMarketingEvent } from "../../lib/marketingAnalytics";
import { ProductPreviewDialog } from "./ProductPreviewDialog";

const views = [
  {
    id: "buyer",
    name: "Buyer workspace",
    icon: ChartNoAxesCombined,
    image: "buyer-workspace.webp",
    title: "See the buying picture.",
    description:
      "Review inventory pressure and purchasing context in the actual beta workspace.",
    alt: "DoobieLogic Buyer workspace showing operational metrics and purchasing context with synthetic demo data",
  },
  {
    id: "inventory",
    name: "Inventory workspace",
    icon: PackageSearch,
    image: "inventory-workspace.webp",
    title: "Get closer to the stock.",
    description:
      "Inspect inventory records and product detail in the actual beta workspace.",
    alt: "DoobieLogic Inventory workspace showing product records and inventory tools with synthetic demo data",
  },
] as const;

export function ProductShowcase() {
  const [active, setActive] = useState(0);
  const [preview, setPreview] = useState<(typeof views)[number] | null>(null);
  const closePreview = useCallback(() => setPreview(null), []);
  const view = views[active];

  function inspectPreview(event: MouseEvent<HTMLAnchorElement>) {
    // Preserve modified clicks and the original-image fallback in older browsers.
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      typeof HTMLDialogElement === "undefined" ||
      typeof HTMLDialogElement.prototype.showModal !== "function"
    ) {
      return;
    }
    event.preventDefault();
    setPreview(view);
    trackMarketingEvent("product_tour_start", {
      placement: "product",
      item: `${view.id}-inspect`,
    });
  }

  return (
    <div className="mh-product-showcase">
      <div className="mh-product-toolbar">
        <span>
          <i /> DOOBIELOGIC / WORKSPACE
        </span>
        <span className="mh-label">BETA PREVIEW</span>
      </div>
      <div className="mh-product-switch" role="group" aria-label="Choose product preview">
        {views.map(({ id, name, icon: Icon }, index) => (
          <button
            type="button"
            aria-pressed={index === active}
            key={id}
            onClick={() => {
              setActive(index);
              trackMarketingEvent("product_tour_start", {
                placement: "product",
                item: id,
              });
            }}
          >
            <Icon size={16} />
            {name}
          </button>
        ))}
      </div>
      <figure>
        <a
          href={`/marketing/${view.image}`}
          target="_blank"
          rel="noreferrer"
          aria-label={`Open full-size ${view.name} screenshot`}
          aria-haspopup="dialog"
          onClick={inspectPreview}
        >
          <img
            src={`/marketing/${view.image}`}
            srcSet={`/marketing/${view.image.replace(".webp", "-480.webp")} 480w, /marketing/${view.image.replace(".webp", "-960.webp")} 960w, /marketing/${view.image} 1440w`}
            sizes="(max-width: 600px) calc(100vw - 36px), (max-width: 900px) calc(100vw - 48px), (min-width: 1500px) 1360px, (max-width: 1320px) calc(100vw - 80px), 1240px"
            width="1440"
            height="1000"
            alt={view.alt}
            fetchPriority={active === 0 ? "high" : "auto"}
          />
        </a>
        <figcaption>
          <span>Actual product interface · Synthetic demo data · Beta</span>
          <a
            href={`/marketing/${view.image}`}
            target="_blank"
            rel="noreferrer"
            aria-haspopup="dialog"
            onClick={inspectPreview}
          >
            View full size <ArrowUpRight size={14} />
          </a>
        </figcaption>
      </figure>
      <div className="mh-product-caption" aria-live="polite">
        <strong>{view.title}</strong>
        <p>{view.description}</p>
      </div>
      {preview && (
        <ProductPreviewDialog
          name={preview.name}
          image={preview.image}
          alt={preview.alt}
          description={preview.description}
          onClose={closePreview}
        />
      )}
    </div>
  );
}
