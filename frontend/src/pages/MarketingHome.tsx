import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  FileCheck2,
  Fingerprint,
  Layers3,
  LockKeyhole,
  ShieldCheck,
} from "lucide-react";
import { APP_URL, INFO_EMAIL } from "../lib/brand";
import { trackMarketingEvent } from "../lib/marketingAnalytics";
import {
  MarketingBrand,
  MarketingNav,
} from "../components/marketing/MarketingNav";
import { ProductShowcase } from "../components/marketing/ProductShowcase";
import { Solutions } from "../components/marketing/Solutions";
import { MarketingContactChannels } from "../components/ContactChannels";
import { marketingFaqs } from "../components/marketing/content";

const lifecycle = [
  ["Cultivation", "Plant & room context"],
  ["Harvest", "Material handoff"],
  ["Production", "Inputs & outputs"],
  ["Packaging", "Finished goods"],
  ["Wholesale", "Commercial handoff"],
  ["Retail", "Stock & buying"],
];
const controls = [
  {
    icon: Layers3,
    title: "Facility context",
    body: "Beta workspaces keep the facility and license in view as teams move between operations.",
  },
  {
    icon: LockKeyhole,
    title: "Role-based access",
    body: "Access controls support different responsibilities. Validate your team’s permissions during onboarding.",
  },
  {
    icon: Fingerprint,
    title: "Action records",
    body: "Audit records capture context for supported workflows. Review the record coverage your operation needs.",
  },
];
const onboarding = [
  [
    "Tell us about the operation.",
    "Share your facilities, state, current systems and the work you want to improve.",
  ],
  [
    "Agree the testing scope.",
    "Review beta fit, data needs, permissions and integration requirements with the team.",
  ],
  [
    "Validate with your people.",
    "Approved partners receive onboarding access to test agreed workflows and give feedback.",
  ],
];
function BetaLink({
  placement,
  children = "Apply for beta",
}: {
  placement: "hero" | "product" | "trust" | "final";
  children?: React.ReactNode;
}) {
  return (
    <a
      className="mh-button"
      href="/beta#apply"
      onClick={() => trackMarketingEvent("homepage_primary_cta", { placement })}
    >
      {children}
      <ArrowUpRight size={18} />
    </a>
  );
}
export function MarketingHome() {
  return (
    <div className="marketing-page mh-page">
      <a className="mh-skip" href="#main-content">
        Skip to content
      </a>
      <MarketingNav />
      <main id="main-content" tabIndex={-1}>
        <section
          className="mh-hero mh-container"
          id="top"
          aria-labelledby="hero-heading"
        >
          <div className="mh-hero-topline">
            <span className="mh-eyebrow">
              Cannabis operations / ERP software
            </span>
            <span className="mh-beta-badge">
              <i /> BETA PARTNER PROGRAM
            </span>
          </div>
          <div className="mh-hero-layout">
            <div className="mh-hero-copy">
              <h1 id="hero-heading">
                Your operation.
                <br />
                <span>One clear picture.</span>
              </h1>
              <p>
                Cannabis ERP in beta for cultivation, production, retail and
                vertically integrated teams. Bring the work into view, from the
                grow room to the next buying decision.
              </p>
              <div className="mh-hero-actions">
                <BetaLink placement="hero" />
                <a
                  className="mh-text-link"
                  href="#platform"
                  onClick={() =>
                    trackMarketingEvent("homepage_secondary_cta", {
                      placement: "hero",
                    })
                  }
                >
                  See the workspace <ArrowDown size={17} />
                </a>
              </div>
              <small>
                For licensed operations. Access follows beta fit review.
              </small>
            </div>
            <div className="mh-hero-aside">
              <span className="mh-aside-line" />
              <p>
                The inventory sheet.
                <br />
                The production whiteboard.
                <br />
                The “who has the latest?”
              </p>
              <strong>
                There’s a better way
                <br />
                to see the work.
              </strong>
            </div>
          </div>
          <div id="platform" className="mh-hero-product">
            <ProductShowcase />
            <div className="mh-product-foot">
              <span>
                <ShieldCheck size={16} /> Beta workflows. Real product
                interfaces.
              </span>
              <a
                href="/beta#apply"
                className="mh-text-link"
                onClick={() =>
                  trackMarketingEvent("homepage_primary_cta", {
                    placement: "product",
                  })
                }
              >
                Put your workflow in the picture <ArrowRight size={16} />
              </a>
            </div>
          </div>
        </section>
        <section className="mh-proof-strip" aria-label="Operations served">
          <div className="mh-container">
            <span>
              FOUR OPERATIONS.
              <br />
              <strong>ONE DIRECTION.</strong>
            </span>
            <a href="#solution-cultivation">Cultivation</a>
            <a href="#solution-production">Production / Manufacturing</a>
            <a href="#solution-retail">Retail Operations</a>
            <a href="#solution-vertical">Vertically Integrated</a>
          </div>
        </section>
        <section
          className="mh-section mh-container mh-problem"
          aria-labelledby="problem-heading"
        >
          <div>
            <span className="mh-eyebrow">01 / Less chasing. More context.</span>
            <h2 id="problem-heading">
              The work is connected.
              <br />
              <span className="mh-muted">Your tools should be, too.</span>
            </h2>
            <p>
              When the count lives in one place and the production record in
              another, your team becomes the integration.
            </p>
          </div>
          <div className="mh-fragmentation">
            <div className="mh-fragments">
              <span>POS export</span>
              <span>Inventory sheet</span>
              <span>Run notebook</span>
              <span>Label file</span>
              <span>Email thread</span>
            </div>
            <div className="mh-connection">
              <ArrowDown size={23} />
            </div>
            <div className="mh-unified">
              <Layers3 size={24} />
              <div>
                <strong>A shared operational view</strong>
                <p>
                  The DoobieLogic beta brings workspaces together. Existing
                  systems and each data connection still need their own
                  validation.
                </p>
              </div>
            </div>
          </div>
        </section>
        <Solutions />
        <section className="mh-lifecycle" aria-labelledby="lifecycle-heading">
          <div className="mh-container mh-section">
            <div className="mh-section-top">
              <div>
                <span className="mh-eyebrow">03 / The vertical view</span>
                <h2 id="lifecycle-heading">
                  The handoff is
                  <br />
                  part of the operation.
                </h2>
              </div>
              <p>
                Follow the journey you need to manage. Evaluate the records and
                handoffs between teams, with facility context at every stage.
              </p>
            </div>
            <ol className="mh-flow">
              {lifecycle.map(([title, body], index) => (
                <li key={title}>
                  <span className="mh-flow-number">0{index + 1}</span>
                  <h3>{title}</h3>
                  <p>{body}</p>
                  {index < lifecycle.length - 1 && <ArrowRight size={20} />}
                </li>
              ))}
            </ol>
            <div className="mh-lifecycle-note">
              <span>
                <i /> Connected lifecycle / beta evaluation
              </span>
              <p>
                A workflow map, not a promise of automatic cross-license
                transfers. Validate each handoff for your operation.
              </p>
            </div>
          </div>
        </section>
        <section
          className="mh-section mh-container"
          id="compliance"
          aria-labelledby="trust-heading"
        >
          <div className="mh-section-top">
            <div>
              <span className="mh-eyebrow">
                04 / Context. Controls. Accountability.
              </span>
              <h2 id="trust-heading">
                Keep the receipts.
                <br />
                Keep people in control.
              </h2>
            </div>
            <p>
              Regulated work deserves more than a green checkmark. Start with
              facility context, clear responsibilities and records your team can
              review.
            </p>
          </div>
          <div className="mh-control-grid">
            {controls.map(({ icon: Icon, title, body }) => (
              <article key={title}>
                <Icon size={25} />
                <h3>{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
          <div className="mh-trust-note">
            <FileCheck2 size={22} />
            <p>
              Compliance tools support review; they do not certify your
              operation or replace your team’s regulatory responsibilities.
              State and license fit are part of the beta evaluation.
            </p>
            <BetaLink placement="trust">Discuss your operation</BetaLink>
          </div>
        </section>
        <section
          className="mh-container mh-ai"
          id="intelligence"
          aria-labelledby="ai-heading"
        >
          <div>
            <span className="mh-eyebrow">Doobie Agent / Beta</span>
            <h2 id="ai-heading">
              Intelligence with
              <br />
              an operation underneath.
            </h2>
            <p>
              Ask questions about available operational data. Get explanations
              and recommendations with context, then make the call with your
              team.
            </p>
            <div className="mh-ai-boundary">
              <LockKeyhole size={17} />
              <span>
                Read-only AI runtime tools. Separate controls for governed
                actions.
              </span>
            </div>
          </div>
          <div className="mh-ai-example">
            <div>
              <Bot size={24} />
              <span>DOOBIE AGENT</span>
              <small>Illustrative question</small>
            </div>
            <blockquote>
              “What should purchasing
              <br />
              look at first?”
            </blockquote>
            <p>
              Explore inventory pressure and buying context in the beta. Answers
              depend on the data and tools available to your workspace.
            </p>
            <span className="mh-ai-process">
              ASK <ArrowRight size={14} /> UNDERSTAND <ArrowRight size={14} />{" "}
              REVIEW
            </span>
          </div>
        </section>
        <section
          className="mh-section mh-container"
          id="integrations"
          aria-labelledby="integrations-heading"
        >
          <div className="mh-section-top">
            <div>
              <span className="mh-eyebrow">
                05 / Your existing systems matter
              </span>
              <h2 id="integrations-heading">
                Let’s talk about
                <br />
                what needs to connect.
              </h2>
            </div>
            <p>
              Bring your stack to the conversation. Readiness depends on
              provider access, configuration and validation in your operation.
            </p>
          </div>
          <div className="mh-integration-grid">
            <article>
              <span className="mh-label">TRACEABILITY</span>
              <h3>Metrc</h3>
              <span className="mh-status">In validation</span>
              <p>
                Metrc-aware workflows are under evaluation. No certification or
                production-ready connection is claimed.
              </p>
            </article>
            <article>
              <span className="mh-label">OPERATIONAL DATA</span>
              <h3>Imports & exports</h3>
              <span className="mh-status">Beta workflows</span>
              <p>
                Review your inventory and sales files with the team. Confirm
                mappings and data quality before relying on them.
              </p>
            </article>
            <article>
              <span className="mh-label">YOUR STACK</span>
              <h3>POS, accounting & more</h3>
              <span className="mh-status neutral">Fit review required</span>
              <p>
                Tell us which connections are essential. A vendor name in your
                stack is not a promise of a live integration.
              </p>
            </article>
          </div>
          <a
            className="mh-text-link"
            href="/beta#apply"
            onClick={() =>
              trackMarketingEvent("integration_view", {
                placement: "integrations",
              })
            }
          >
            Bring your integration requirements <ArrowRight size={17} />
          </a>
        </section>
        <section
          className="mh-adoption"
          id="workflow"
          aria-labelledby="adoption-heading"
        >
          <div className="mh-section mh-container">
            <div className="mh-section-top">
              <div>
                <span className="mh-eyebrow">06 / Start with the work</span>
                <h2 id="adoption-heading">
                  A useful beta starts
                  <br />
                  with your actual operation.
                </h2>
              </div>
              <p>
                No promised rollout clock. First, agree what needs to work:
                data, team access, integrations and the workflows that matter.
              </p>
            </div>
            <div className="mh-onboarding">
              {onboarding.map(([title, body], index) => (
                <article key={title}>
                  <span>0{index + 1}</span>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
        <section
          className="mh-section mh-container mh-faq"
          id="resources"
          aria-labelledby="faq-heading"
        >
          <div>
            <span className="mh-eyebrow">07 / Before you apply</span>
            <h2 id="faq-heading">
              Fair questions.
              <br />
              Straight answers.
            </h2>
            <p>Clear expectations make better partners.</p>
            <a className="mh-text-link" href="/beta#program">
              Read about the beta program <ArrowRight size={17} />
            </a>
            <a className="mh-text-link" href="/beta#data">
              Participation & data use <ArrowRight size={17} />
            </a>
          </div>
          <div>
            {marketingFaqs.map(({ question, answer }, index) => (
              <details
                key={question}
                onToggle={(event) => {
                  if (event.currentTarget.open)
                    trackMarketingEvent("faq_expand", {
                      placement: "faq",
                      item: `question-${index + 1}`,
                    });
                }}
              >
                <summary>
                  {question}
                  <span aria-hidden="true">+</span>
                </summary>
                <p>{answer}</p>
              </details>
            ))}
          </div>
        </section>
        <MarketingContactChannels />
        <section
          className="mh-final mh-container"
          aria-labelledby="final-heading"
        >
          <span className="mh-eyebrow">
            Good weed deserves better operations.
          </span>
          <h2 id="final-heading">
            Bring us the workflow
            <br />
            that needs to work better.
          </h2>
          <p>Show us where the friction is. Help shape what comes next.</p>
          <BetaLink placement="final">Apply for beta access</BetaLink>
          <span className="mh-final-note">
            <Check size={15} /> Applications reviewed for current beta fit
          </span>
        </section>
      </main>
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
            <a href="#platform">Product preview</a>
            <a href="#solutions">Operations & solutions</a>
            <a href="#intelligence">Doobie Agent</a>
          </div>
          <div>
            <h2>Evaluate</h2>
            <a href="#integrations">Integration readiness</a>
            <a href="#compliance">Controls & compliance</a>
            <a href="#workflow">Beta onboarding</a>
          </div>
          <div>
            <h2>Get to know us</h2>
            <a href="#resources">Questions & answers</a>
            <a href="/beta#program">Beta Partner Program</a>
            <a href="/beta#data">Participation & data use</a>
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
        <div className="mh-footer-bottom">
          <span>© {new Date().getFullYear()} DoobieLogic</span>
          <span>
            Semper Paratus <i /> Powered by Good Weed and Data
          </span>
          <a href="#top">Back to top ↑</a>
        </div>
      </footer>
    </div>
  );
}
