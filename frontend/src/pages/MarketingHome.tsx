import {
  ArrowRight,
  BarChart3,
  Boxes,
  ClipboardCheck,
  Factory,
  PackageCheck,
  ShieldCheck,
  ShoppingCart,
  Sparkles,
  Warehouse,
} from "lucide-react";
import { APP_URL, BRAND_IMAGE_URL } from "../lib/brand";

const capabilities = [
  {
    icon: ShoppingCart,
    title: "Buy with the whole picture",
    body: "Turn inventory, sales velocity, days of supply, pricing, and purchasing budgets into clearer buying decisions.",
  },
  {
    icon: Warehouse,
    title: "Know what is actually on hand",
    body: "Receive inventory, run focused counts, pause and resume audits, track lots, and keep facility-level inventory separate.",
  },
  {
    icon: Factory,
    title: "Run production from the same system",
    body: "Plan production, extraction, packaging, Co-Man work, materials, outputs, costs, QA, and capacity without another spreadsheet stack.",
  },
  {
    icon: ShieldCheck,
    title: "Keep compliance close to the work",
    body: "Bring traceability, METRC-oriented workflows, product naming, compliance research, and operational evidence into the same daily workspace.",
  },
];

const workflow = [
  ["01", "Connect the operation", "Start with the facility, users, roles, and the operational data your team already works from."],
  ["02", "See the pressure points", "Surface inventory risk, buying needs, production constraints, slow movers, holds, and upcoming work."],
  ["03", "Act from the same workspace", "Receive, count, buy, produce, investigate, map, report, and document without bouncing between disconnected tools."],
  ["04", "Keep the receipts", "Preserve source context, operational history, user permissions, and facility boundaries as the work changes."],
];

export function MarketingHome() {
  return (
    <div className="marketing-page">
      <header className="marketing-nav-wrap">
        <nav className="marketing-nav" aria-label="Public navigation">
          <a className="marketing-brand" href="#top" aria-label="DoobieLogic home">
            <img className="marketing-brand-image" src={BRAND_IMAGE_URL} alt="DoobieLogic" />
            <span className="marketing-brand-copy"><strong>DoobieLogic</strong><small>Cannabis Operations Intelligence</small></span>
          </a>
          <div className="marketing-nav-links">
            <a href="#platform">Platform</a>
            <a href="#operations">Operations</a>
            <a href="#workflow">How it works</a>
          </div>
          <a className="marketing-login" href={APP_URL}>Log in <ArrowRight size={15} /></a>
        </nav>
      </header>

      <main id="top">
        <section className="marketing-hero">
          <div className="marketing-hero-copy">
            <div className="marketing-eyebrow">Built for cannabis retail, production, and compliance teams</div>
            <h1>One operating system for the work between the menu and the manifest.</h1>
            <p>
              DoobieLogic brings buying, inventory, receiving, audits, production, extraction,
              compliance, reporting, and facility controls into one connected workspace.
            </p>
            <div className="marketing-cta-row">
              <a className="marketing-primary" href={APP_URL}>Open DoobieLogic <ArrowRight size={17} /></a>
              <a className="marketing-secondary" href="#platform">Explore the platform</a>
            </div>
            <div className="marketing-proof-line">
              <span><ClipboardCheck size={15} /> Facility-aware</span>
              <span><ShieldCheck size={15} /> Permission-aware</span>
              <span><Sparkles size={15} /> AI where it helps, deterministic workflows where it matters</span>
            </div>
          </div>

          <div className="marketing-product-frame" aria-label="DoobieLogic operations dashboard preview">
            <div className="marketing-product-topbar">
              <div className="marketing-mini-brand"><img src={BRAND_IMAGE_URL} alt="" /><strong>DoobieLogic</strong></div>
              <div className="marketing-context-pill">Retail Ops · Sandbox Facility</div>
            </div>
            <div className="marketing-product-body">
              <aside className="marketing-product-sidebar">
                {['Home','Inventory','Purchasing','Orders','Production','Reports','Compliance'].map((item, index) => (
                  <div key={item} className={index === 0 ? "active" : ""}>{item}</div>
                ))}
              </aside>
              <div className="marketing-product-content">
                <div className="marketing-preview-heading">
                  <div><small>OPERATIONS HOME</small><h3>What needs attention today</h3></div>
                  <span>Live workspace</span>
                </div>
                <div className="marketing-kpis">
                  <article><span>Reorder now</span><strong>12</strong><small>6 urgent</small></article>
                  <article><span>Inventory value</span><strong>$184k</strong><small>across active lots</small></article>
                  <article><span>Production queue</span><strong>8</strong><small>3 due this week</small></article>
                  <article><span>Compliance holds</span><strong>2</strong><small>review required</small></article>
                </div>
                <div className="marketing-preview-grid">
                  <section>
                    <div className="marketing-preview-section-title"><strong>Inventory pressure</strong><span>Buyer view</span></div>
                    {[['GMO Pre-Roll 1g','11 DOS','Reorder'],['Blue Dream Flower 3.5g','19 DOS','Watch'],['Live Resin Cart 1g','96 DOS','Overstock']].map(([name,dos,state]) => (
                      <div className="marketing-preview-row" key={name}><span>{name}</span><small>{dos}</small><em>{state}</em></div>
                    ))}
                  </section>
                  <section>
                    <div className="marketing-preview-section-title"><strong>Production pulse</strong><span>Production Ops</span></div>
                    <div className="marketing-run-card"><Factory size={18}/><div><strong>PR-2048 · Infused Pre-Rolls</strong><small>Packaging · 72% complete</small></div><b>On track</b></div>
                    <div className="marketing-run-card"><PackageCheck size={18}/><div><strong>EXT-118 · Live Resin</strong><small>QA review · output pending</small></div><b className="warn">Review</b></div>
                  </section>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="marketing-signal-strip" aria-label="DoobieLogic workspaces">
          {['Buying','Inventory','Receiving','Audits','Production','Extraction','Compliance','Reports'].map(item => <span key={item}>{item}</span>)}
        </section>

        <section className="marketing-section" id="platform">
          <div className="marketing-section-heading">
            <div className="marketing-eyebrow">The platform</div>
            <h2>The operational layer cannabis teams keep rebuilding in spreadsheets.</h2>
            <p>DoobieLogic is designed around the jobs operators actually have to finish, not a collection of disconnected dashboards.</p>
          </div>
          <div className="marketing-capability-grid">
            {capabilities.map(({ icon: Icon, title, body }) => (
              <article className="marketing-capability-card" key={title}>
                <span className="marketing-icon"><Icon size={20}/></span>
                <h3>{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="marketing-operations" id="operations">
          <div className="marketing-operations-copy">
            <div className="marketing-eyebrow">Retail Ops + Production Ops</div>
            <h2>Different licenses. Different inventory. One operating language.</h2>
            <p>
              Retail teams need sellable inventory, purchasing, receiving, sales intelligence, and store-level controls.
              Production and cultivation teams need bulk cannabis, plants, materials, extraction, production runs, QA, and their own license context.
            </p>
            <div className="marketing-operation-list">
              <span><Boxes size={17}/> Retail inventory and buying workflows</span>
              <span><Factory size={17}/> Production, extraction, packaging, and Co-Man</span>
              <span><ClipboardCheck size={17}/> Audits, receiving, traceability, and compliance evidence</span>
              <span><BarChart3 size={17}/> Operational and executive reporting</span>
            </div>
          </div>
          <div className="marketing-operations-panel">
            <div className="marketing-panel-label">Facility context</div>
            <article className="marketing-license-card retail"><span>Retail</span><strong>Adult-use store</strong><p>Sellable inventory, purchasing, sales, receiving, counts, compliance, reports.</p></article>
            <article className="marketing-license-card production"><span>Production</span><strong>Manufacturing / cultivation</strong><p>Bulk inventory, plants, production runs, extraction, QA, costing, capacity, traceability.</p></article>
          </div>
        </section>

        <section className="marketing-section" id="workflow">
          <div className="marketing-section-heading compact">
            <div className="marketing-eyebrow">How it works</div>
            <h2>From source data to the next operational decision.</h2>
          </div>
          <div className="marketing-workflow-grid">
            {workflow.map(([number,title,body]) => (
              <article key={number}><span>{number}</span><h3>{title}</h3><p>{body}</p></article>
            ))}
          </div>
        </section>

        <section className="marketing-final-cta">
          <div>
            <div className="marketing-eyebrow">DoobieLogic</div>
            <h2>Less swivel-chair operations. More time running the business.</h2>
            <p>The application lives at ops.doobielogic.io. Your public site stays clean; your operational workspace stays secured behind login.</p>
          </div>
          <a className="marketing-primary" href={APP_URL}>Log in to DoobieLogic <ArrowRight size={17}/></a>
        </section>
      </main>

      <footer className="marketing-footer">
        <div className="marketing-brand"><img className="marketing-brand-image" src={BRAND_IMAGE_URL} alt="DoobieLogic" /><span className="marketing-brand-copy"><strong>DoobieLogic</strong><small>Cannabis Operations Intelligence</small></span></div>
        <div><a href="#platform">Platform</a><a href="#workflow">How it works</a><a href={APP_URL}>Log in</a></div>
        <small>© {new Date().getFullYear()} DoobieLogic</small>
      </footer>
    </div>
  );
}
