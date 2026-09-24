import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  CircleGauge,
  Fingerprint,
  Layers3,
  LockKeyhole,
  PackageSearch,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { services } from "../lib/consultingServices";
import { trackMarketingEvent } from "../lib/marketingAnalytics";
import { MarketingNav } from "../components/marketing/MarketingNav";
import { MarketingFooter } from "../components/marketing/MarketingPage";
import { ProductShowcase } from "../components/marketing/ProductShowcase";
import { Solutions } from "../components/marketing/Solutions";
import { MarketingContactChannels } from "../components/ContactChannels";
import { marketingFaqs } from "../components/marketing/content";

const lifecycle = [
  ["Cultivation", "Plant and room context"],
  ["Harvest", "Material handoff"],
  ["Extraction", "Run stages and yield"],
  ["Production", "Inputs, outputs and packaging"],
  ["Commercial", "Inventory and buying context"],
  ["Retail", "The next decision"],
];

const controls = [
  {
    icon: Layers3,
    title: "Facility and license context",
    body: "Keep the operating boundary visible as teams move between the parts of the business they own.",
  },
  {
    icon: LockKeyhole,
    title: "People stay in control",
    body: "DoobieLogic can surface context and guide a workflow. Regulated changes remain governed by your team.",
  },
  {
    icon: Fingerprint,
    title: "Records worth reviewing",
    body: "Supported workflows retain operational context so the next person is not reconstructing what happened from memory.",
  },
];

const extractionProof = [
  ["Source", "Released material + package context"],
  ["Run", "Inputs, stages, outputs and losses"],
  ["Review", "Yield, variance, QA and release context"],
  ["Handoff", "Bulk output, packaging and downstream inventory"],
];

const agentQuestions = [
  "What needs attention first?",
  "What inventory is sitting too long?",
  "What should purchasing look at next?",
  "Which production runs need attention?",
];

const onboarding = [
  [
    "Start with the friction.",
    "Show us the handoff, count, run or buying decision your team is carrying today.",
  ],
  [
    "Map the operating context.",
    "Review facilities, systems, permissions and the workflow that needs to connect.",
  ],
  [
    "See it with your team.",
    "Approved beta partners evaluate the agreed workspace with the people who do the work.",
  ],
];

function BetaLink({
  placement,
  children = "See the product",
}: {
  placement:
    "hero" | "product" | "trust" | "final" | "extraction" | "intelligence";
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

function ExtractionWorkflowProof() {
  return (
    <div
      className="mh-extraction-proof"
      aria-label="Extraction workflow context"
    >
      <div className="mh-extraction-proof-topline">
        <span>
          <i /> EXTRACTION RUN CONTEXT
        </span>
        <span>WORKFLOW VIEW</span>
      </div>
      <div
        className="mh-extraction-metrics"
        aria-label="Extraction run metrics"
      >
        <div>
          <span>Reserved input</span>
          <strong>Source-aware</strong>
        </div>
        <div>
          <span>Stage yield</span>
          <strong>Measured</strong>
        </div>
        <div>
          <span>Variance</span>
          <strong>Visible</strong>
        </div>
      </div>
      <ol className="mh-extraction-flow">
        {extractionProof.map(([label, detail], index) => (
          <li key={label}>
            <span>0{index + 1}</span>
            <div>
              <strong>{label}</strong>
              <small>{detail}</small>
            </div>
            {index < extractionProof.length - 1 && (
              <ArrowRight size={15} aria-hidden="true" />
            )}
          </li>
        ))}
      </ol>
      <div className="mh-extraction-proof-foot">
        <PackageSearch size={18} />
        <span>
          Keep source-to-output history close to the run, without pretending
          every process follows the same path.
        </span>
      </div>
    </div>
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
            <span className="mh-eyebrow">Cannabis operations software</span>
            <span className="mh-beta-badge">
              <i /> BETA PARTNER PROGRAM
            </span>
          </div>
          <div className="mh-hero-layout">
            <div className="mh-hero-copy mh-reveal">
              <h1 id="hero-heading">
                Your team shouldn&apos;t
                <br />
                be <span>the integration.</span>
              </h1>
              <p>
                DoobieLogic is veteran-built cannabis ERP and operations
                software for teams who are done stitching together cultivation,
                extraction, production, inventory and buying with spreadsheets,
                whiteboards and tribal knowledge.
              </p>
              <div className="mh-hero-actions">
                <BetaLink placement="hero">
                  See your operation in one picture
                </BetaLink>
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
                Built for licensed operators. Beta access is scoped around the
                workflows that matter to your team.
              </small>
            </div>
            <div
              className="mh-hero-aside mh-reveal mh-reveal-delay"
              aria-label="Fragmented operations example"
            >
              <span className="mh-aside-line" />
              <span className="mh-label">THE DAILY HANDOFF</span>
              <p>
                The count in one place. The run on another screen. The answer
                living with the person who was there.
              </p>
              <strong>
                One shared picture.
                <br />
                Clearer next moves.
              </strong>
            </div>
          </div>
        </section>

        <section className="mh-proof-strip" aria-label="Operations served">
          <div className="mh-container">
            <span>
              FROM THE GROW ROOM
              <br />
              <strong>TO THE NEXT BUY.</strong>
            </span>
            <a href="#solution-cultivation">Cultivation</a>
            <a href="#extraction">Extraction</a>
            <a href="#solution-production">Production</a>
            <a href="#solution-retail">Retail &amp; purchasing</a>
          </div>
        </section>

        <section
          className="mh-section mh-container mh-problem"
          aria-labelledby="problem-heading"
        >
          <div>
            <span className="mh-eyebrow">
              01 / The system behind the system
            </span>
            <h2 id="problem-heading">
              The work is connected.
              <br />
              <span className="mh-muted">Your records should be, too.</span>
            </h2>
            <p>
              When the count lives in one place and the production record in
              another, your team becomes the integration. That is where the
              handoffs, hunting and second-guessing start.
            </p>
          </div>
          <div
            className="mh-fragmentation"
            aria-label="Fragmented systems becoming a shared operational view"
          >
            <div className="mh-fragments">
              <span>POS export</span>
              <span>Inventory sheet</span>
              <span>Run notebook</span>
              <span>Label file</span>
              <span>Text thread</span>
            </div>
            <div className="mh-connection">
              <ArrowDown size={23} />
            </div>
            <div className="mh-unified">
              <Layers3 size={24} />
              <div>
                <strong>A shared operational picture</strong>
                <p>
                  DoobieLogic brings the day&apos;s operational context into
                  view while respecting the facilities, licenses and workflows
                  behind it.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section
          className="mh-platform-proof mh-container"
          id="platform"
          aria-labelledby="platform-heading"
        >
          <div className="mh-platform-proof-copy">
            <span className="mh-eyebrow">02 / Product proof</span>
            <h2 id="platform-heading">
              See the work before
              <br />
              you ask for the report.
            </h2>
            <p>
              These are working DoobieLogic product surfaces, not a concept
              mockup. Synthetic demonstration data keeps private operator data
              out while the buying, inventory and workflow experience stays real.
            </p>
            <div className="mh-platform-proof-points">
              <span>
                <Check size={15} /> Real DoobieLogic product surfaces
              </span>
              <span>
                <Check size={15} /> Synthetic demonstration data
              </span>
              <span>
                <Check size={15} /> Verified Metrc integration
              </span>
            </div>
          </div>
          <div className="mh-platform-proof-product mh-reveal mh-reveal-delay">
            <ProductShowcase />
          </div>
        </section>

        <section
          className="mh-extraction"
          id="extraction"
          aria-labelledby="extraction-heading"
        >
          <div className="mh-container mh-section mh-extraction-layout">
            <div>
              <span className="mh-eyebrow">
                03 / Extraction is not a black box
              </span>
              <h2 id="extraction-heading">
                Extraction without the
                <br />
                <span>spreadsheet archaeology.</span>
              </h2>
              <p>
                Extraction is where source material, process knowledge, yield
                and downstream inventory meet. DoobieLogic keeps the operational
                story close: compatible source material, run stages, measured
                inputs and outputs, loss and variance, QA/release context, and
                source-to-output history.
              </p>
              <div className="mh-extraction-list">
                <span>
                  <Workflow size={17} /> Plan a run around compatible, released
                  source material.
                </span>
                <span>
                  <CircleGauge size={17} /> Compare input, output, yield and
                  recorded loss as the run moves.
                </span>
                <span>
                  <ShieldCheck size={17} /> Keep QA, COA, release and
                  traceability context available for deeper review.
                </span>
              </div>
              <div className="mh-extraction-actions">
                <BetaLink placement="extraction">
                  Walk us through an extraction run
                </BetaLink>
                <a
                  className="mh-text-link"
                  href="#solutions"
                  onClick={() =>
                    trackMarketingEvent("extraction_section_engagement", {
                      placement: "extraction",
                      item: "workflow-context",
                    })
                  }
                >
                  Explore every operation <ArrowRight size={17} />
                </a>
              </div>
            </div>
            <ExtractionWorkflowProof />
          </div>
        </section>

        <Solutions />

        <section className="mh-lifecycle" aria-labelledby="lifecycle-heading">
          <div className="mh-container mh-section">
            <div className="mh-section-top">
              <div>
                <span className="mh-eyebrow">
                  05 / The whole operation has handoffs
                </span>
                <h2 id="lifecycle-heading">
                  The handoff is
                  <br />
                  part of the operation.
                </h2>
              </div>
              <p>
                Material, context and responsibility all move. See the journey
                your team needs to manage without flattening distinct facilities
                and workflows into one generic process.
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
                <i /> Shared context, real operating boundaries
              </span>
              <p>
                Facility and license context stay visible as teams evaluate the
                workflows that matter to their operation.
              </p>
            </div>
          </div>
        </section>

        <section
          className="mh-container mh-ai"
          id="intelligence"
          aria-labelledby="ai-heading"
        >
          <div>
            <span className="mh-eyebrow">06 / Doobie Agent</span>
            <h2 id="ai-heading">
              Ask your operation
              <br />
              <span>what needs attention.</span>
            </h2>
            <p>
              Doobie Agent is an intelligence layer over the operational context
              available to your workspace. It is not a generic chatbot bolted
              onto an ERP. Ask a practical question, understand the evidence,
              then let your team make the call.
            </p>
            <div className="mh-ai-boundary">
              <LockKeyhole size={17} />
              <span>
                Read-oriented AI tools surface context, explanations and
                recommendations. Governed actions remain separate and
                human-controlled.
              </span>
            </div>
            <BetaLink placement="intelligence">
              See Doobie Agent in context
            </BetaLink>
          </div>
          <div className="mh-ai-example">
            <div>
              <Bot size={24} />
              <span>DOOBIE AGENT</span>
              <small>Operational questions</small>
            </div>
            <blockquote>
              “What should
              <br />I look at first?”
            </blockquote>
            <div className="mh-agent-questions">
              {agentQuestions.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() =>
                    trackMarketingEvent("doobie_agent_engagement", {
                      placement: "intelligence",
                      item:
                        question === agentQuestions[0]
                          ? "triage"
                          : "operational-question",
                    })
                  }
                >
                  {question}
                  <ArrowRight size={14} />
                </button>
              ))}
            </div>
            <span className="mh-ai-process">
              ASK <ArrowRight size={14} /> UNDERSTAND <ArrowRight size={14} />{" "}
              REVIEW
            </span>
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
                07 / Context. Controls. Accountability.
              </span>
              <h2 id="trust-heading">
                Keep the receipts.
                <br />
                Keep people in control.
              </h2>
            </div>
            <p>
              Regulated work deserves more than a green checkmark. The strongest
              operation is the one where the next person can understand the
              context, the boundary and what happened.
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
        </section>

        <section
          className="mh-section mh-container"
          id="why-doobielogic"
          aria-labelledby="why-doobielogic-heading"
        >
          <div className="mh-section-top">
            <div>
              <span className="mh-eyebrow">Why DoobieLogic</span>
              <h2 id="why-doobielogic-heading">
                Built around the operation.
                <br />
                Not a generic ERP template.
              </h2>
            </div>
            <p>
              Different teams need different workspaces. DoobieLogic connects
              the context between them without pretending cultivation,
              extraction, production and purchasing are the same job.
            </p>
          </div>
          <div className="mh-integration-grid">
            <article>
              <span className="mh-label">EXTRACTION</span>
              <h3>Extraction is a first-class workflow</h3>
              <p>
                Run stages, measured inputs and outputs, yield, loss, QA and
                source-to-output history stay close to the people doing the work.
              </p>
            </article>
            <article>
              <span className="mh-label">HANDOFFS</span>
              <h3>Context moves with the operation</h3>
              <p>
                Cultivation, production, inventory and purchasing can keep their
                own operating views while sharing the records behind the next
                decision.
              </p>
            </article>
            <article>
              <span className="mh-label">INTELLIGENCE</span>
              <h3>AI starts with operational context</h3>
              <p>
                Doobie Agent works from the context available to the workspace.
                Recommendations stay reviewable and governed actions remain
                human-controlled.
              </p>
            </article>
          </div>
        </section>

        <section
          className="mh-integrations-section"
          id="integrations"
          aria-labelledby="integrations-heading"
        >
          <div className="mh-container mh-section">
            <div className="mh-section-top">
              <div>
                <span className="mh-eyebrow">
                  08 / Build around the systems you have
                </span>
                <h2 id="integrations-heading">
                  Bring the stack.
                  <br />
                  Start with the handoff.
                </h2>
              </div>
              <p>
                DoobieLogic is designed for a real operating environment, not a
                clean demo. We begin with the systems, data and handoffs your
                team needs to see more clearly.
              </p>
            </div>
            <div className="mh-integration-grid">
              <article>
                <span className="mh-label">TRACEABILITY</span>
                <h3>Verified Metrc integration</h3>
                <p>
                  DoobieLogic has completed Metrc integration verification.
                  Connection scope still depends on state, license, facility
                  permissions, credentials and the supported workflow.
                </p>
              </article>
              <article>
                <span className="mh-label">OPERATIONAL DATA</span>
                <h3>Inventory, buying and production context</h3>
                <p>
                  Bring the sources your team relies on today. Data mapping and
                  workflow fit are reviewed before a beta scope is agreed.
                </p>
              </article>
              <article>
                <span className="mh-label">YOUR OPERATION</span>
                <h3>One useful starting point</h3>
                <p>
                  Start with the record, handoff or decision that creates the
                  most friction. Expand only after the workflow earns your
                  trust.
                </p>
              </article>
            </div>
          </div>
        </section>

        <section
          className="mh-section mh-container"
          id="operator-built"
          aria-labelledby="operator-built-heading"
        >
          <div className="mh-section-top">
            <div>
              <span className="mh-eyebrow">Veteran-built / operator-informed</span>
              <h2 id="operator-built-heading">
                Built by someone who has
                <br />
                actually worked the operation.
              </h2>
            </div>
            <p>
              DoobieLogic is veteran-built by a U.S. Army veteran with hands-on
              cannabis purchasing, inventory, production and retail operations
              experience. The product starts with the friction operators
              actually carry, then builds the software around it.
            </p>
          </div>
          <div className="mh-control-grid">
            <article>
              <ShieldCheck size={25} />
              <h3>Veteran-built discipline</h3>
              <p>
                Clear ownership, reviewable evidence and reliable handoffs matter
                more than feature-count theater.
              </p>
            </article>
            <article>
              <PackageSearch size={25} />
              <h3>Operator-side experience</h3>
              <p>
                Purchasing, inventory, production and retail decisions informed
                the workflows instead of being added after the fact.
              </p>
            </article>
            <article>
              <Workflow size={25} />
              <h3>Fix the workflow before automating it</h3>
              <p>
                Consulting and software live together so a broken process does
                not become a faster broken process.
              </p>
            </article>
          </div>
        </section>

        <section
          className="mh-adoption"
          id="workflow"
          aria-labelledby="adoption-heading"
        >
          <div className="mh-section mh-container">
            <div className="mh-section-top">
              <div>
                <span className="mh-eyebrow">
                  09 / A beta with a point of view
                </span>
                <h2 id="adoption-heading">
                  Start with the work
                  <br />
                  that is costing you time.
                </h2>
              </div>
              <p>
                This is a focused beta, not a promise that every workflow fits
                every facility on day one. We define the useful starting point
                together.
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
            <span className="mh-eyebrow">10 / Before you apply</span>
            <h2 id="faq-heading">
              Fair questions.
              <br />
              Straight answers.
            </h2>
            <p>Clear expectations make better operating partners.</p>
            <a className="mh-text-link" href="/beta#program">
              Read about the beta program <ArrowRight size={17} />
            </a>
            <a className="mh-text-link" href="/beta#data">
              Participation &amp; data use <ArrowRight size={17} />
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

        <section
          className="mh-section mh-container"
          id="cost-of-disconnected-ops"
          aria-labelledby="cost-heading"
        >
          <div className="mh-section-top">
            <div>
              <span className="mh-eyebrow">The cost of disconnected operations</span>
              <h2 id="cost-heading">
                The gap shows up
                <br />
                before it hits the P&amp;L.
              </h2>
            </div>
            <p>
              No invented ROI percentages. Just the recurring work operators
              recognize when systems, records and handoffs do not line up.
            </p>
          </div>
          <div className="mh-integration-grid">
            <article>
              <h3>Reconciliation time</h3>
              <p>
                People spend hours comparing exports, counts and production
                records before they can answer a basic operational question.
              </p>
            </article>
            <article>
              <h3>Buying without enough context</h3>
              <p>
                Stock pressure, aging inventory and the next purchase decision
                live in different places, so the buyer becomes the integration.
              </p>
            </article>
            <article>
              <h3>Production history rebuilt later</h3>
              <p>
                Yield, loss, QA and process knowledge become spreadsheet
                archaeology when the run record is not connected end to end.
              </p>
            </article>
          </div>
          <a className="mh-text-link" href="#consulting">
            Start with the operating problem <ArrowRight size={17} aria-hidden="true" />
          </a>
        </section>

        <section
          className="mh-section mh-container"
          id="consulting"
          aria-labelledby="consulting-heading"
        >
          <div className="mh-section-top">
            <div>
              <span className="mh-eyebrow">Not ready for new software?</span>
              <h2 id="consulting-heading">
                Start with
                <br />
                the operation.
              </h2>
            </div>
            <p>
              You do not need to become a software customer to work with us.
              Start with inventory, purchasing, systems, SOPs, Metrc workflows,
              production or extraction, then agree on a useful scope.
            </p>
          </div>
          <div className="mh-integration-grid">
            {services.map((service) => (
              <article key={service.slug}>
                <h3>{service.title}</h3>
                <p>{service.summary}</p>
                <a
                  className="mh-text-link"
                  href={`/consulting/${service.slug}`}
                  onClick={() =>
                    trackMarketingEvent("service_internal_link_clicked", {
                      placement: "product",
                      item: service.slug,
                    })
                  }
                >
                  Explore service <ArrowRight size={17} aria-hidden="true" />
                </a>
              </article>
            ))}
          </div>
          <div className="mh-hero-actions">
            <a className="mh-button" href="/consulting#consultation">
              Book a free 20-minute consultation <ArrowUpRight size={17} />
            </a>
            <a className="mh-text-link" href="/consulting">
              Explore consulting <ArrowRight size={17} aria-hidden="true" />
            </a>
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
          <p>
            Show us where your people are holding disconnected systems together.
            We&apos;ll show you the operational picture we can build with them.
          </p>
          <BetaLink placement="final">See if DoobieLogic fits</BetaLink>
          <span className="mh-final-note">
            <Check size={15} /> Beta applications are reviewed around operation
            and workflow fit
          </span>
        </section>
      </main>
      <MarketingFooter />
    </div>
  );
}
