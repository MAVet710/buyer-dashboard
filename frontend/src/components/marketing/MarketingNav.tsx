import { useRef, useState } from "react";
import { ArrowUpRight, Menu, X } from "lucide-react";
import { APP_URL } from "../../lib/brand";
import { trackMarketingEvent } from "../../lib/marketingAnalytics";

export function MarketingBrand() {
  return (
    <a className="marketing-brand" href="/#top" aria-label="DoobieLogic home">
      <img src="/marketing/brand.webp" width="44" height="44" alt="" />
      <span>
        Doobie<em>Logic</em>
      </span>
    </a>
  );
}

export function MarketingNav() {
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  return (
    <header
      className="mh-header"
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          setOpen(false);
          toggle.current?.focus();
        }
      }}
    >
      <nav className="mh-nav mh-container" aria-label="Public navigation">
        <MarketingBrand />
        <button
          ref={toggle}
          className="mh-menu-toggle"
          type="button"
          aria-expanded={open}
          aria-controls="marketing-menu"
          onClick={() => setOpen(!open)}
        >
          {open ? <X size={20} /> : <Menu size={20} />}
          <span>{open ? "Close" : "Menu"}</span>
        </button>
        <div
          id="marketing-menu"
          className={`mh-nav-menu ${open ? "is-open" : ""}`}
        >
          <div className="mh-nav-links">
            {[
              ["Platform", "platform"],
              ["Solutions", "solutions"],
              ["Integrations", "integrations"],
              ["Resources", "resources"],
            ].map(([label, id]) => (
              <a href={`#${id}`} key={id} onClick={() => setOpen(false)}>
                {label}
              </a>
            ))}
          </div>
          <div className="mh-nav-actions">
            <a
              href={APP_URL}
              onClick={() =>
                trackMarketingEvent("login_click", { placement: "navigation" })
              }
            >
              Log in <ArrowUpRight size={14} />
            </a>
            <a
              className="mh-button mh-button-small"
              href="/beta#apply"
              onClick={() =>
                trackMarketingEvent("homepage_primary_cta", {
                  placement: "navigation",
                })
              }
            >
              Apply for beta <ArrowUpRight size={16} />
            </a>
          </div>
        </div>
      </nav>
    </header>
  );
}
