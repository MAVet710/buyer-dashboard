import {
  ArrowRight,
  Bot,
  Boxes,
  CircleCheck,
  ClipboardCheck,
  Factory,
  FileCheck2,
  FlaskConical,
  LockKeyhole,
  PackageCheck,
  ShieldCheck,
  ShoppingCart,
  Store,
  Warehouse,
  Workflow,
} from "lucide-react";
import { APP_URL, BRAND_IMAGE_URL } from "../lib/brand";

const modules = [
  [ShoppingCart, "Buying"],
  [Warehouse, "Inventory"],
  [PackageCheck, "Receiving"],
  [FlaskConical, "Extraction"],
  [Factory, "Production"],
  [Store, "Wholesale + Portal"],
  [Workflow, "METRC"],
  [ShieldCheck, "Compliance"],
  [Bot, "Doobie Agent"],
] as const;

const featureCards = [
  {
    icon: FlaskConical,
    title: "Extraction Command Center",
    body: "Track inputs, outputs, yields, recovery, cost, and run status while the work is happening. No Friday-afternoon scavenger hunt through notebooks, texts, and somebody's mystery spreadsheet.",
  },
  {
    icon: Store,
    title: "Wholesale & Customer Portal",
    body: "Give licensed buyers a branded place to order, then bring approved orders straight into inventory allocation and fulfillment. Fewer screenshots. Fewer retyped orders. Much less 'did anyone enter that yet?'",
  },
  {
    icon: Bot,
    title: "Doobie Agent",
    body: "Ask what's going on across the facility and get answers tied to the operation, not generic chatbot filler. Doobie can surface issues and prepare the next move; regulated actions still stay under employee control.",
  },
  {
    icon: Workflow,
    title: "METRC Integration",
    body: "Keep packages, transfers, manifests, facility mappings, reconciliation, and controlled actions tied to the workflow that created them instead of treating METRC like a second job with worse hours.",
  },
  {
    icon: Warehouse,
    title: "Inventory & Receiving",
    body: "See what you have, what moved, what is aging, what needs a count, and what purchasing should care about before the answer becomes 'we're out.'",
  },
  {
    icon: Factory,
    title: "Production & QA",
    body: "Plan work, follow bulk material into finished goods, track yields and QA, and keep production inventory connected to what sales and wholesale can actually promise.",
  },
  {
    icon: FileCheck2,
    title: "Compliance Evidence & Reporting",
    body: "Keep the record behind the work: who did it, when, what changed, what data supported it, and what you can hand over when someone asks six months later.",
  },
];

const workflow = [
  ["01", "Set up the operation you actually have", "Facilities, licenses, roles, people, and the systems your team already uses. DoobieLogic should fit the operation, not make the operation cosplay as software."],
  ["02", "See what needs attention", "Inventory pressure, purchasing needs, active runs, holds, receiving work, customer orders, and compliance issues show up where the team can act on them."],
  ["03", "Do the work in context", "Receive it, count it, buy it, make it, extract it, sell it, investigate it, and report it without rebuilding the same story in five places."],
  ["04", "Keep people in control", "Doobie can point out the problem and prepare the next step. High-value and regulated actions keep approval, submission, and reconciliation visible."],
];

export function MarketingHome() {
  return (
    <div className="marketing-page">
      <header className="marketing-nav-wrap">
        <nav className="marketing-nav" aria-label="Public navigation">
          <a className="marketing-brand" href="#top" aria-label="DoobieLogic home">
            <img className="marketing-brand-image" src={BRAND_IMAGE_URL} alt="DoobieLogic" />
            <span className="marketing-wordmark"><strong>Doobie</strong><em>Logic</em></span>
          </a>

          <div className="marketing-nav-links">
            <a href="#platform">Platform</a>
            <a href="#extraction">Operations</a>
            <a href="#compliance">Compliance</a>
            <a href="#workflow">How it works</a>
          </div>

          <div className="marketing-nav-actions">
            <a className="marketing-nav-login" href={APP_URL}>Log In</a>
            <a className="marketing-nav-primary" href="/beta">Join the Beta</a>
          </div>
        </nav>
      </header>

      <main id="top">
        <section className="marketing-hero">
          <div className="marketing-hero-copy">
            <div className="marketing-eyebrow">Cannabis operations, minus the scavenger hunt</div>
            <h1>
              Run <span>buying, inventory, production, extraction, wholesale,</span> and compliance without stitching the story together by hand.
            </h1>
            <p>
              DoobieLogic brings the work that actually runs a cannabis business into one place. Purchasing. Receiving. Production. Extraction. Wholesale. Traceability. Reporting. Compliance. And an agent that understands the facility it is talking about.
            </p>

            <div className="marketing-cta-row">
              <a className="marketing-primary" href="/beta">Join the DoobieLogic Beta <ArrowRight size={18} /></a>
              <a className="marketing-secondary" href="#platform">See how it works</a>
            </div>

            <div className="marketing-proof-line">
              <span><CircleCheck size={16} /> Facility-scoped</span>
              <span><LockKeyhole size={16} /> User-permission controlled</span>
              <span><ShieldCheck size={16} /> Human-approved regulated actions</span>
            </div>
          </div>

          <div className="marketing-product-frame" aria-label="DoobieLogic operations dashboard preview">
            <aside className="marketing-product-sidebar">
              <div className="marketing-mini-brand">
                <img src={BRAND_IMAGE_URL} alt="" />
                <span className="marketing-mini-wordmark"><strong>Doobie</strong><em>Logic</em></span>
              </div>
              {['Home','Inventory','Purchasing','Extraction','Production','Wholesale','Compliance','Doobie Agent'].map((item, index) => (
                <div key={item} className={`marketing-product-nav-item ${index === 0 ? "active" : ""}`}>{item}</div>
              ))}
              <div className="marketing-user-card">
                <span>DL</span>
                <div><strong>Operations Admin</strong><small>Sandbox Facility</small></div>
              </div>
            </aside>

            <div className="marketing-product-content">
              <div className="marketing-preview-heading">
                <div>
                  <small>OPERATIONS HOME</small>
                  <h3>Morning. Here&apos;s what needs your attention.</h3>
                  <p>The important stuff, before it turns into everybody&apos;s problem.</p>
                </div>
                <span>Live workspace</span>
              </div>

              <div className="marketing-kpis">
                <article><span>Active Runs</span><strong>14</strong><small>3 need a look</small></article>
                <article><span>Inventory Risk</span><strong>12</strong><small>6 urgent reorders</small></article>
                <article><span>Open Orders</span><strong>8</strong><small>2 ready to fulfill</small></article>
                <article><span>Compliance Flags</span><strong>2</strong><small>better now than later</small></article>
              </div>

              <div className="marketing-preview-grid">
                <section>
                  <div className="marketing-preview-section-title"><strong>Extraction Command Center</strong><span>View all runs →</span></div>
                  <div className="marketing-table-head"><span>Run ID</span><span>Product</span><span>Stage</span><span>Status</span></div>
                  {[
                    ['EXT-118','Live Resin','Purging','In Progress'],
                    ['PR-2048','Infused Pre-Rolls','Packaging','In Progress'],
                    ['EXT-117','Live Resin','Pressing','Completed'],
                    ['EXT-116','Distillate','Distillation','Completed'],
                  ].map(([id, product, stage, status]) => (
                    <div className="marketing-preview-row" key={id}>
                      <span>{id}</span><span>{product}</span><small>{stage}</small><em className={status === 'Completed' ? 'done' : ''}>{status}</em>
                    </div>
                  ))}
                </section>

                <section>
                  <div className="marketing-preview-section-title"><strong>Regulatory Control</strong><span>View details →</span></div>
                  {[
                    ['Facility mapping','Verified'],
                    ['Package reconciliation','Ready'],
                    ['Manifest workflow','Human controlled'],
                    ['Action attempts','Audited'],
                    ['Doobie recommendations','Read only'],
                  ].map(([label, state]) => (
                    <div className="marketing-status-row" key={label}><span>{label}</span><b>{state} <CircleCheck size={12}/></b></div>
                  ))}
                </section>
              </div>

              <div className="marketing-sync-bar">
                <div><ShieldCheck size={19}/><span><strong>Same facility. Same story.</strong><small>Inventory, production, commerce, and compliance read from the same operating context.</small></span></div>
                <div className="marketing-sync-stat"><strong>8</strong><small>Open orders</small></div>
                <div className="marketing-sync-stat"><strong>1</strong><small>Approval waiting</small></div>
                <div className="marketing-sync-stat"><strong>2 mins</strong><small>Last sync</small></div>
              </div>
            </div>
          </div>
        </section>

        <section className="marketing-module-strip" aria-label="DoobieLogic workspaces">
          {modules.map(([Icon, label]) => <span key={label}><Icon size={18}/>{label}</span>)}
        </section>

        <section className="marketing-section marketing-feature-section" id="platform">
          <div className="marketing-section-heading">
            <div className="marketing-eyebrow">One place to run the work</div>
            <h2>Because “check the spreadsheet” is not an operating system.</h2>
            <p>Most cannabis teams are already running the business across METRC, POS exports, spreadsheets, whiteboards, texts, email, sales portals, and the one employee everyone asks because they somehow know where everything is. DoobieLogic connects that work without pretending every license operates the same way.</p>
          </div>

          <div className="marketing-feature-grid">
            {featureCards.map(({ icon: Icon, title, body }) => (
              <article className="marketing-feature-card" key={title}>
                <span className="marketing-icon"><Icon size={24}/></span>
                <h3>{title}</h3>
                <p>{body}</p>
                <a href="#workflow">See the flow <ArrowRight size={15}/></a>
              </article>
            ))}
          </div>
        </section>

        <section className="marketing-operations" id="extraction">
          <div className="marketing-operations-copy">
            <div className="marketing-eyebrow">Retail + Production + Wholesale</div>
            <h2>A dispensary vault, an extraction lab, and a pallet of bulk flower are not the same inventory problem.</h2>
            <p>
              Retail cares about sellable units, turns, receiving, and reorders. Production and cultivation care about bulk material,
              plants, runs, yields, QA, and traceability. Wholesale cares about customers, pricing, allocations, fulfillment, transport, and manifests. DoobieLogic keeps those workflows distinct while still connecting the operation behind them.
            </p>
            <div className="marketing-operation-list">
              <span><Boxes size={18}/> Retail inventory, buying, receiving, and sales</span>
              <span><FlaskConical size={18}/> Extraction runs, yields, inputs, outputs, and costing</span>
              <span><Factory size={18}/> Production, packaging, QA, planning, and Co-Man</span>
              <span><Store size={18}/> Wholesale storefronts, pricing, customer orders, fulfillment, and manifest readiness</span>
            </div>
          </div>

          <div className="marketing-operations-panel">
            <div className="marketing-panel-label">License context matters</div>
            <article className="marketing-license-card retail"><span>Retail</span><strong>Adult-use store</strong><p>Sellable inventory, buying, sales, receiving, counts, compliance, and the day-to-day work that keeps the store moving.</p></article>
            <article className="marketing-license-card production"><span>Production</span><strong>Manufacturing / cultivation / wholesale</strong><p>Bulk inventory, plants, extraction, runs, QA, materials, costing, production planning, customer orders, capacity, fulfillment, and traceability. No retail-shaped square peg.</p></article>
          </div>
        </section>

        <section className="marketing-trust-band" id="compliance">
          <div className="marketing-trust-intro">
            <span className="marketing-trust-shield"><ShieldCheck size={28}/></span>
            <div><h3>Built for cannabis, where “close enough” can get expensive.</h3><p>Make the right thing easier to do and the history easier to prove.</p></div>
          </div>
          <article><ShieldCheck size={21}/><div><strong>State Compliance</strong><p>Keep regulated work tied to the correct facility, verified context, and the rules that actually apply there.</p></div></article>
          <article><Workflow size={21}/><div><strong>Controlled Traceability</strong><p>Keep recommendation, employee approval, provider submission, and reconciliation separate so “we clicked it” never gets mistaken for “it is reconciled.”</p></div></article>
          <article><ClipboardCheck size={21}/><div><strong>Audit Ready</strong><p>When somebody asks what happened, pull the record instead of assembling a group chat and hoping for the best.</p></div></article>
          <article><LockKeyhole size={21}/><div><strong>User & Facility Controls</strong><p>People see the facilities and functions they are actually allowed to use. Pricing, approvals, and sensitive operations can be permission-controlled down to the user.</p></div></article>
        </section>

        <section className="marketing-section" id="workflow">
          <div className="marketing-section-heading compact">
            <div className="marketing-eyebrow">How it works</div>
            <h2>Less hunting for answers. More running the operation.</h2>
          </div>
          <div className="marketing-workflow-grid">
            {workflow.map(([number,title,body]) => (
              <article key={number}><span>{number}</span><h3>{title}</h3><p>{body}</p></article>
            ))}
          </div>
        </section>

        <section className="marketing-final-cta">
          <div>
            <div className="marketing-eyebrow">DoobieLogic Beta</div>
            <h2>Good weed deserves better operations.</h2>
            <p>Put DoobieLogic through real cannabis workflows, tell us where it still annoys you, and help shape what ships next.</p>
          </div>
          <a className="marketing-primary" href="/beta">Apply for Beta Access <ArrowRight size={18}/></a>
        </section>
      </main>

      <footer className="marketing-footer">
        <div className="marketing-footer-brand">
          <div className="marketing-brand"><img className="marketing-brand-image" src={BRAND_IMAGE_URL} alt="DoobieLogic" /><span className="marketing-wordmark"><strong>Doobie</strong><em>Logic</em></span></div>
          <small>Cannabis Operations Software</small>
        </div>
        <div className="marketing-footer-links"><a href="#platform">Platform</a><a href="#extraction">Operations</a><a href="#compliance">Compliance</a><a href="/beta">Join Beta</a><a href={APP_URL}>Log in</a></div>
        <div className="marketing-footer-motto"><strong>Semper Paratus</strong><span>•</span><span>Powered by Good Weed and Data</span></div>
        <small className="marketing-copyright">© {new Date().getFullYear()} DoobieLogic</small>
      </footer>
    </div>
  );
}
