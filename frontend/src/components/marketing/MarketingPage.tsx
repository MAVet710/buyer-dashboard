import "../../advisory.css";
import { AnalyticsConsent } from "./AnalyticsConsent";
import type { ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";
import { MarketingBrand, MarketingNav } from "./MarketingNav";
import { APP_URL, INFO_EMAIL } from "../../lib/brand";
import {
  trackMarketingEvent,
  type MarketingEventContext,
} from "../../lib/marketingAnalytics";

export function ConsultationCTA({
  service,
  href,
  children = "Book a free 20-minute consultation",
  placement = "hero",
}: {
  service?: string;
  href?: string;
  children?: ReactNode;
  placement?: MarketingEventContext["placement"];
}) {
  return (
    <a
      className="mh-button"
      href={
        href ??
        `/consulting${service ? `?service=${encodeURIComponent(service)}` : ""}#consultation`
      }
      onClick={() =>
        trackMarketingEvent("consultation_cta_clicked", {
          placement,
          item: service,
        })
      }
    >
      {children}
      <ArrowUpRight size={18} aria-hidden="true" />
    </a>
  );
}

export function MarketingFooter() {
  return (
    <footer className="mh-footer mh-container">
      <div className="mh-footer-main">
        <div>
          <MarketingBrand />
          <p>Cannabis Operations Intelligence</p>
          <a className="mh-text-link" href={`mailto:${INFO_EMAIL}`}>
            {INFO_EMAIL}
            <ArrowUpRight size={15} />
          </a>
        </div>
        <div>
          <h2>Platform</h2>
          <a href="/#platform">Product proof</a>
          <a href="/#extraction">Extraction</a>
          <a href="/#solutions">Operations &amp; solutions</a>
        </div>
        <div>
          <h2>Context</h2>
          <a href="/#intelligence">Doobie Agent</a>
          <a href="/#integrations">Integration approach</a>
          <a href="/#compliance">Controls &amp; compliance</a>
        </div>
        <div>
          <h2>Get to know us</h2>
          <a href="/#resources">Questions &amp; answers</a>
          <a href="/consulting">Consulting</a>
          <a href="/resources">Operator resources</a>
          <a href="/help">Help Center</a>
          <a href="/beta#program">Beta Partner Program</a>
          <a
            href={APP_URL}
            onClick={() =>
              trackMarketingEvent("login_click", { placement: "footer" })
            }
          >
            Operator login <ArrowUpRight size={13} />
          </a>
        </div>
      </div>
      <AnalyticsConsent />
      <div className="mh-footer-bottom">
        <span>© {new Date().getFullYear()} DoobieLogic</span>
        <span>
          Semper Paratus <i /> Powered by Good Weed and Data
        </span>
        <a href="#top">Back to top ↑</a>
      </div>
    </footer>
  );
}

export function MarketingPage({ children }: { children: ReactNode }) {
  return (
    <div className="marketing-page mh-page advisory-page">
      <a className="mh-skip" href="#main-content">
        Skip to content
      </a>
      <MarketingNav />
      <main id="main-content" tabIndex={-1}>
        <div id="top" />
        {children}
      </main>
      <MarketingFooter />
    </div>
  );
}
