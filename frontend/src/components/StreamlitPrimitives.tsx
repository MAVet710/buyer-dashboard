import { createPortal } from "react-dom";
import { useEffect, useRef, useState, type PropsWithChildren, type ReactNode } from "react";

type DialogSize = "compact" | "default" | "wide";

export function StreamlitDialog({ title, subtitle, onClose, size = "default", children }: PropsWithChildren<{ title: string; subtitle?: string; onClose: () => void; size?: DialogSize }>) {
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => { document.body.style.overflow = previous; window.removeEventListener("keydown", closeOnEscape); };
  }, [onClose]);
  const body = <div className="streamlit-overlay-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={`streamlit-dialog ${size === "default" ? "" : size}`} role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal-heading"><div>{subtitle ? <div className="eyebrow">{subtitle}</div> : null}<h2>{title}</h2></div><button type="button" className="secondary" onClick={onClose}>Close</button></div>
      {children}
    </section>
  </div>;
  return createPortal(body, document.body);
}

export function StreamlitPopover({ label, children, align = "left", className = "" }: PropsWithChildren<{ label: ReactNode; align?: "left" | "right"; className?: string }>) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => { if (root.current && !root.current.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    window.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", close); window.removeEventListener("keydown", escape); };
  }, [open]);
  return <div className={`streamlit-popover ${align} ${className}`} ref={root}>
    <button type="button" className="streamlit-popover-trigger" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(value => !value)}>{label}</button>
    {open ? <div className="streamlit-popover-panel" role="dialog">{children}</div> : null}
  </div>;
}

export function StreamlitExpander({ title, children, defaultOpen = false, className = "" }: PropsWithChildren<{ title: ReactNode; defaultOpen?: boolean; className?: string }>) {
  return <details className={`streamlit-expander ${className}`} open={defaultOpen || undefined}>
    <summary>{title}</summary>
    <div className="streamlit-expander-content">{children}</div>
  </details>;
}

export function StreamlitGlassPanel({ children, className = "" }: PropsWithChildren<{ className?: string }>) {
  return <section className={`streamlit-glass-panel ${className}`}>{children}</section>;
}

export function StreamlitMetric({ label, value, help, tone = "copper" }: { label: ReactNode; value: ReactNode; help?: ReactNode; tone?: "copper" | "green" | "blue" | "yellow" | "red" }) {
  return <article className={`metric streamlit-metric tone-${tone}`}><span>{label}</span><strong>{value}</strong>{help ? <small>{help}</small> : null}</article>;
}
