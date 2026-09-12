import { useEffect, useId, useRef, useState } from "react";
import { ArrowUpRight, X, ZoomIn, ZoomOut } from "lucide-react";
import { trackMarketingEvent } from "../../lib/marketingAnalytics";
import "./product-preview.css";

type ProductPreviewDialogProps = {
  name: string;
  image: string;
  alt: string;
  description: string;
  onClose: () => void;
};

/** Marketing screenshots only. Never mounts an operator workspace or requests live data. */
export function ProductPreviewDialog({
  name,
  image,
  alt,
  description,
  onClose,
}: ProductPreviewDialogProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const [zoomed, setZoomed] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;

    const trigger = document.activeElement;
    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    element.showModal();
    root.style.overflow = "hidden";
    closeButton.current?.focus();

    return () => {
      if (element.open) element.close();
      root.style.overflow = previousOverflow;
      if (trigger instanceof HTMLElement && trigger.isConnected) {
        trigger.focus({ preventScroll: true });
      }
    };
  }, [onClose]);

  return (
    <dialog
      ref={dialog}
      className="mh-preview-dialog"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      aria-modal="true"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return;
        const bounds = event.currentTarget.getBoundingClientRect();
        if (
          event.clientX < bounds.left ||
          event.clientX > bounds.right ||
          event.clientY < bounds.top ||
          event.clientY > bounds.bottom
        ) {
          onClose();
        }
      }}
    >
      <div className="mh-preview-heading">
        <div>
          <span className="mh-label">DOOBIELOGIC / PRODUCT PREVIEW</span>
          <h2 id={titleId}>{name}</h2>
        </div>
        <button
          ref={closeButton}
          type="button"
          className="mh-preview-control"
          onClick={onClose}
          aria-label="Close product preview"
        >
          <X size={20} aria-hidden="true" />
          Close
        </button>
      </div>
      <p className="mh-preview-description" id={descriptionId}>
        {description} Actual product interface with synthetic demo data. Beta,
        not a live workspace.
      </p>
      <div className="mh-preview-tools">
        <button
          type="button"
          className="mh-preview-control"
          aria-pressed={zoomed}
          disabled={imageFailed}
          onClick={() => setZoomed((value) => !value)}
        >
          {zoomed ? (
            <ZoomOut size={17} aria-hidden="true" />
          ) : (
            <ZoomIn size={17} aria-hidden="true" />
          )}
          {zoomed ? "Fit to window" : "Zoom to full detail"}
        </button>
        <a
          className="mh-preview-control"
          href={`/marketing/${image}`}
          target="_blank"
          rel="noreferrer"
          aria-label={`Open original ${name} screenshot in a new tab`}
        >
          Open original <ArrowUpRight size={16} aria-hidden="true" />
        </a>
        <span aria-live="polite">
          {zoomed ? "Scroll or use arrow keys to explore." : "Select zoom to inspect smaller details."}
        </span>
      </div>
      <div
        className={`mh-preview-stage${zoomed ? " is-zoomed" : ""}`}
        tabIndex={0}
        role="region"
        aria-label={`${name} screenshot${zoomed ? ", scroll to explore full detail" : ""}`}
      >
        {imageFailed ? (
          <p role="status">
            This screenshot could not load. Close the preview to continue
            exploring DoobieLogic.
          </p>
        ) : (
          <img
            src={`/marketing/${image}`}
            width="1440"
            height="1000"
            alt={alt}
            onError={() => setImageFailed(true)}
          />
        )}
      </div>
      <div className="mh-preview-footer">
        <p>Start with a conversation about your workflow.</p>
        <a
          className="mh-button mh-button-small"
          href="/beta#apply"
          onClick={() =>
            trackMarketingEvent("homepage_primary_cta", { placement: "product" })
          }
        >
          Apply for beta <ArrowUpRight size={16} aria-hidden="true" />
        </a>
      </div>
    </dialog>
  );
}
