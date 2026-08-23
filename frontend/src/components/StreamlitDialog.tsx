import { useEffect, type PropsWithChildren, type ReactNode } from "react";

type Props = PropsWithChildren<{
  open: boolean;
  title: ReactNode;
  subtitle?: ReactNode;
  eyebrow?: ReactNode;
  onClose: () => void;
  footer?: ReactNode;
}>;

export function StreamlitDialog({ open, title, subtitle, eyebrow, onClose, footer, children }: Props) {
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
    <section className="modal" role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : "Buyer Dash detail"} onMouseDown={(event) => event.stopPropagation()}>
      <div className="modal-heading">
        <div>{eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}<h2>{title}</h2>{subtitle ? <p>{subtitle}</p> : null}</div>
        <button className="secondary" type="button" onClick={onClose}>Close</button>
      </div>
      {children}
      {footer ? <div className="audit-actions">{footer}</div> : null}
    </section>
  </div>;
}
