import { Maximize2, Minimize2, Minus, X } from "lucide-react";
import { createPortal } from "react-dom";
import { useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent, type PropsWithChildren, type ReactNode } from "react";
import "./workspace-window.css";

type Position = { left: number; top: number };
type DragState = Position & { pointerId: number; width: number; height: number; startX: number; startY: number };

let workspaceWindowZIndex = 90;
const workspaceWindowRegistry = new Map<string, number>();
function nextWorkspaceWindowZIndex() {
  workspaceWindowZIndex += 1;
  return workspaceWindowZIndex;
}
function topWorkspaceWindowKey() {
  let topKey = "";
  let topZIndex = -Infinity;
  for (const [key, zIndex] of workspaceWindowRegistry.entries()) {
    if (zIndex > topZIndex) {
      topKey = key;
      topZIndex = zIndex;
    }
  }
  return topKey;
}

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
  const [minimized, setMinimized] = useState(false);
  const [position, setPosition] = useState<Position | null>(null);
  const [zIndex, setZIndex] = useState(() => nextWorkspaceWindowZIndex());
  const windowRef = useRef<HTMLElement | null>(null);
  const dragRef = useRef<DragState | null>(null);

  const bringToFront = useCallback(() => {
    const nextZIndex = nextWorkspaceWindowZIndex();
    workspaceWindowRegistry.set(windowKey, nextZIndex);
    setZIndex(nextZIndex);
  }, [windowKey]);

  useEffect(() => {
    if (!open) {
      workspaceWindowRegistry.delete(windowKey);
      setMaximized(false);
      setMinimized(false);
      setPosition(null);
      return;
    }
    bringToFront();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && topWorkspaceWindowKey() === windowKey) onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      workspaceWindowRegistry.delete(windowKey);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [bringToFront, open, onClose, windowKey]);

  useEffect(() => {
    if (!open) return;
    const clamp = () => {
      if (window.innerWidth <= 720) {
        if (minimized) setMinimized(false);
        return;
      }
      if (!position || maximized) return;
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
  }, [maximized, minimized, open, position]);

  const beginDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    bringToFront();
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

  const toggleMaximized = () => {
    setMinimized(false);
    setMaximized(value => !value);
  };
  const toggleMinimized = () => {
    setMaximized(false);
    setMinimized(value => !value);
  };

  if (!open || typeof document === "undefined") return null;
  const style = {
    ...(position && !maximized ? { "--workspace-window-left": `${position.left}px`, "--workspace-window-top": `${position.top}px` } : {}),
    zIndex,
  } as CSSProperties;
  const label = ariaLabel ?? (typeof title === "string" ? title : "DoobieLogic contextual workspace");

  return createPortal(
    <aside
      ref={windowRef}
      style={style}
      className={`workspace-window open ${maximized ? "maximized" : ""} ${minimized ? "minimized" : ""} ${position && !maximized ? "has-custom-position" : ""} ${className}`.trim()}
      role="dialog"
      aria-modal="false"
      aria-label={label}
      aria-expanded={!minimized}
      data-window-key={windowKey}
      onPointerDownCapture={bringToFront}
      onFocusCapture={bringToFront}
    >
      <div
        className="workspace-window-header"
        onPointerDown={beginDrag}
        onPointerMove={drag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onDoubleClick={event => {
          if ((event.target as HTMLElement).closest("button") || window.innerWidth <= 720) return;
          if (minimized) {
            setMinimized(false);
            return;
          }
          toggleMaximized();
        }}
      >
        <div className="workspace-window-heading">
          {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        <div className="workspace-window-actions">
          <button className="icon-button workspace-window-minimize" type="button" aria-label={minimized ? "Restore window" : "Minimize window"} title={minimized ? "Restore" : "Minimize"} onClick={toggleMinimized}>
            <Minus size={19}/>
          </button>
          {!minimized ? <button className="icon-button workspace-window-maximize" type="button" aria-label={maximized ? "Restore window" : "Maximize window"} title={maximized ? "Restore" : "Maximize"} onClick={toggleMaximized}>
            {maximized ? <Minimize2 size={18}/> : <Maximize2 size={18}/>}
          </button> : null}
          <button className="icon-button workspace-window-close" type="button" aria-label="Close window" title="Close" onClick={onClose}><X size={20}/></button>
        </div>
      </div>
      <div className="workspace-window-body">{children}</div>
      {footer ? <div className="workspace-window-footer">{footer}</div> : null}
    </aside>,
    document.body,
  );
}
