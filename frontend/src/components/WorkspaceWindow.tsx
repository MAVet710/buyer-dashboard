import { Maximize2, Minimize2, X } from "lucide-react";
import { createPortal } from "react-dom";
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type PropsWithChildren, type ReactNode } from "react";
import "./workspace-window.css";

type Position = { left: number; top: number };
type DragState = Position & { pointerId: number; width: number; height: number; startX: number; startY: number };

type Props = PropsWithChildren<{
  open: boolean;
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  ariaLabel?: string;
  windowKey?: string;
  className?: string;
}>;

export function WorkspaceWindow({ open, eyebrow, title, subtitle, footer, onClose, ariaLabel, windowKey = "workspace", className = "", children }: Props) {
  const [maximized, setMaximized] = useState(false);
  const [position, setPosition] = useState<Position | null>(null);
  const windowRef = useRef<HTMLElement | null>(null);
  const dragRef = useRef<DragState | null>(null);

  useEffect(() => {
    if (!open) {
      setMaximized(false);
      setPosition(null);
      return;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const clamp = () => {
      if (!position || maximized || window.innerWidth <= 720) return;
      const rect = windowRef.current?.getBoundingClientRect();
      if (!rect) return;
      const margin = 12;
      setPosition(current => current ? {
        left: Math.min(Math.max(margin, window.innerWidth - rect.width - margin), Math.max(margin, current.left)),
        top: Math.min(Math.max(margin, window.innerHeight - rect.height - margin), Math.max(margin, current.top)),
      } : current);
    };
    window.addEventListener("resize", clamp);
    return () => window.removeEventListener("resize", clamp);
  }, [maximized, open, position]);

  const beginDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (maximized || event.button !== 0 || window.innerWidth <= 720 || (event.target as HTMLElement).closest("button,a,input,select,textarea")) return;
    const rect = windowRef.current?.getBoundingClientRect();
    if (!rect) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const drag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const state = dragRef.current;
    if (!state || state.pointerId !== event.pointerId || maximized) return;
    const margin = 12;
    const maxLeft = Math.max(margin, window.innerWidth - state.width - margin);
    const maxTop = Math.max(margin, window.innerHeight - state.height - margin);
    setPosition({
      left: Math.min(maxLeft, Math.max(margin, state.left + event.clientX - state.startX)),
      top: Math.min(maxTop, Math.max(margin, state.top + event.clientY - state.startY)),
    });
  };

  const endDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  if (!open || typeof document === "undefined") return null;
  const style = position && !maximized ? ({ "--workspace-window-left": `${position.left}px`, "--workspace-window-top": `${position.top}px` } as CSSProperties) : undefined;
  const label = ariaLabel ?? (typeof title === "string" ? title : "DoobieLogic contextual workspace");

  return createPortal(
    <aside
      ref={windowRef}
      style={style}
      className={`workspace-window open ${maximized ? "maximized" : ""} ${position && !maximized ? "has-custom-position" : ""} ${className}`.trim()}
      role="dialog"
      aria-modal="false"
      aria-label={label}
      data-window-key={windowKey}
    >
      <div
        className="workspace-window-header"
        onPointerDown={beginDrag}
        onPointerMove={drag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={event => { if (!(event.target as HTMLElement).closest("button") && window.innerWidth > 720) setMaximized(value => !value); }}
      >
        <div className="workspace-window-heading">
          {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        <div className="workspace-window-actions">
          <button className="icon-button workspace-window-maximize" type="button" aria-label={maximized ? "Restore window" : "Maximize window"} title={maximized ? "Restore" : "Maximize"} onClick={() => setMaximized(value => !value)}>
            {maximized ? <Minimize2 size={18}/> : <Maximize2 size={18}/>}
          </button>
          <button className="icon-button" type="button" aria-label="Close window" onClick={onClose}><X size={19}/></button>
        </div>
      </div>
      <div className="workspace-window-body">{children}</div>
      {footer ? <div className="workspace-window-footer">{footer}</div> : null}
    </aside>,
    document.body,
  );
}
