import { useEffect, useRef } from "react";
import { ArrowUpRight, ChartNoAxesCombined, FlaskConical, PackageSearch } from "lucide-react";
import { trackMarketingEvent } from "../../lib/marketingAnalytics";

export type ProductWorkspaceId = "buyer" | "inventory" | "extraction";

type ProductView =
  | {
      id: ProductWorkspaceId;
      name: string;
      icon: typeof ChartNoAxesCombined;
      media: "image";
      image: string;
      title: string;
      description: string;
      alt: string;
    }
  | {
      id: ProductWorkspaceId;
      name: string;
      icon: typeof ChartNoAxesCombined;
      media: "video";
      video: string;
      fallbackVideo: string;
      poster: string;
      title: string;
      description: string;
      alt: string;
    };

const views: ProductView[] = [
  {
    id: "buyer",
    name: "Buyer workspace",
    icon: ChartNoAxesCombined,
    media: "image",
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
    media: "image",
    image: "inventory-workspace.webp",
    title: "Get closer to the stock.",
    description:
      "Inspect inventory records and product detail in the actual beta workspace.",
    alt: "DoobieLogic Inventory workspace showing product records and inventory tools with synthetic demo data",
  },
  {
    id: "extraction",
    name: "Extraction workspace",
    icon: FlaskConical,
    media: "video",
    video: "extraction-workspace.webm",
    fallbackVideo: "extraction-workspace.mp4",
    poster: "extraction-workspace-poster.png",
    title: "See the run in motion.",
    description:
      "Follow a real DoobieLogic extraction workflow through run context, process stages, outputs, QA, and traceability using synthetic demo data.",
    alt: "DoobieLogic Extraction workspace real-use demo with synthetic data",
  },
];

export function ProductShowcase({
  activeView,
  onViewChange,
}: {
  activeView: ProductWorkspaceId;
  onViewChange: (view: ProductWorkspaceId) => void;
}) {
  const view = views.find(item => item.id === activeView) ?? views[0];
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    if (view.media !== "video") return;
    const video = videoRef.current;
    if (!video) return;
    const startPlayback = () => {
      video.muted = true;
      video.defaultMuted = true;
      void video.play().catch(() => undefined);
    };
    startPlayback();
    video.addEventListener("canplay", startPlayback, { once: true });
    return () => video.removeEventListener("canplay", startPlayback);
  }, [view]);

  return (
    <div className="mh-product-showcase">
      <div className="mh-product-toolbar">
        <span>
          <i /> DOOBIELOGIC / WORKSPACE
        </span>
        <span className="mh-label">BETA PREVIEW</span>
      </div>
      <div className="mh-product-switch" role="tablist" aria-label="Choose product preview">
        {views.map(({ id, name, icon: Icon }) => (
          <button
            type="button"
            role="tab"
            id={`product-tab-${id}`}
            aria-selected={id === activeView}
            aria-controls="product-preview-panel"
            key={id}
            onClick={() => {
              onViewChange(id);
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
      <figure
        id="product-preview-panel"
        role="tabpanel"
        aria-labelledby={`product-tab-${view.id}`}
      >
        {view.media === "video" ? (
          <video
            ref={videoRef}
            key={view.video}
            className="mh-product-video"
            poster={`/marketing/${view.poster}`}
            autoPlay
            muted
            loop
            playsInline
            controls
            preload="metadata"
            aria-label={view.alt}
          >
            <source src={`/marketing/${view.video}`} type="video/webm" />
            <source src={`/marketing/${view.fallbackVideo}`} type="video/mp4" />
            Your browser does not support the Extraction workspace preview video.
          </video>
        ) : (
          <a
            href={`/marketing/${view.image}`}
            target="_blank"
            rel="noreferrer"
            aria-label={`Open full-size ${view.name} screenshot`}
          >
            <img
              src={`/marketing/${view.image}`}
              srcSet={`/marketing/${view.image.replace(".webp", "-480.webp")} 480w, /marketing/${view.image.replace(".webp", "-960.webp")} 960w, /marketing/${view.image} 1440w`}
              sizes="(max-width: 600px) calc(100vw - 36px), (max-width: 900px) calc(100vw - 48px), (min-width: 1500px) 1360px, (max-width: 1320px) calc(100vw - 80px), 1240px"
              width="1440"
              height="1000"
              alt={view.alt}
              fetchPriority={activeView === "buyer" ? "high" : "auto"}
            />
          </a>
        )}
        <figcaption>
          <span>Actual product interface · Synthetic demo data · Beta</span>
          <a
            href={view.media === "video" ? `/marketing/${view.fallbackVideo}` : `/marketing/${view.image}`}
            target="_blank"
            rel="noreferrer"
          >
            View full size <ArrowUpRight size={14} />
          </a>
        </figcaption>
      </figure>
      <div className="mh-product-caption" aria-live="polite">
        <strong>{view.title}</strong>
        <p>{view.description}</p>
      </div>
    </div>
  );
}
