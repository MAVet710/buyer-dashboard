import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  CircleCheck,
  ClipboardCheck,
  Layers3,
  MessageSquare,
  ShieldCheck,
} from "lucide-react";
import { ApiError, apiPublicPost } from "../lib/api";
import { APP_URL } from "../lib/brand";
import { trackMarketingEvent } from "../lib/marketingAnalytics";
import "../beta-partner.css";

const workflows = [
  [
    "01",
    "Buying & inventory",
    "Purchasing, receiving, counts and stock intelligence. Put everyday retail decisions through their paces.",
  ],
  [
    "02",
    "Cultivation & production",
    "Plant and facility context, production inventory, work queues and manufacturing handoffs.",
  ],
  [
    "03",
    "Extraction & material flow",
    "Source material, runs, yields, recovery, potency and the handoff to finished output.",
  ],
  [
    "04",
    "Wholesale & Customer Portal",
    "Branded storefronts, customer requests, order approval, allocation, fulfillment and manifest readiness.",
  ],
  [
    "05",
    "Compliance & reporting",
    "Labels, records, review controls and useful reports. Validate the workflow against your actual requirements.",
  ],
  [
    "06",
    "Doobie Agent",
    "Surface exceptions, explain operational context and prepare governed actions for employee review.",
  ],
] as const;
const steps = [
  [
    "01",
    "Tell us about the operation.",
    "Your facilities, current tools and the work that needs attention.",
  ],
  [
    "02",
    "Agree on the beta fit.",
    "We review your application against the current phase, then define the workflows and data to test.",
  ],
  [
    "03",
    "Put the workflow to work.",
    "Approved partners receive onboarding access and help shape the next iteration through structured feedback.",
  ],
] as const;

function BetaBrand() {
  return (
    <a className="bp-brand" href="/" aria-label="DoobieLogic home">
      <img src="/marketing/brand.webp" width="44" height="44" alt="" />
      <span>
        Doobie<em>Logic</em>
      </span>
    </a>
  );
}

export function BetaPartnerPage() {
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  const feedback = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error || submitted) feedback.current?.focus();
  }, [error, submitted]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true;
    setSubmitting(true);
    setSubmitted(false);
    setError("");
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const result = await apiPublicPost<{ accepted: boolean }>(
        "/api/v1/beta/apply",
        {
          name: String(data.get("name") ?? "").trim(),
          email: String(data.get("email") ?? "").trim(),
          company: String(data.get("company") ?? "").trim(),
          role: String(data.get("role") ?? "").trim(),
          operation: String(data.get("operation") ?? "").trim(),
          facilities: String(data.get("facilities") ?? "").trim(),
          stack: String(data.get("stack") ?? "").trim(),
          state: String(data.get("state") ?? "").trim(),
          pain: String(data.get("pain") ?? "").trim(),
          must_have: String(data.get("must_have") ?? "").trim(),
          consent: data.get("consent") === "on",
          website: String(data.get("website") ?? "").trim(),
        },
      );
      if (result.accepted !== true)
        throw new Error(
          "Your application was not accepted by the service. Your answers are still here. Please try again.",
        );
      form.reset();
      setSubmitted(true);
      trackMarketingEvent("beta_apply", { placement: "beta" });
    } catch (submissionError) {
      setError(
        submissionError instanceof ApiError && submissionError.status === 408
          ? "The beta application request timed out. We could not confirm receipt. Your answers are still here; you can retry or contact the team."
          : submissionError instanceof Error
            ? submissionError.message
            : "We could not confirm receipt of your application. Your answers are still here. Please try again.",
      );
    } finally {
      pending.current = false;
      setSubmitting(false);
    }
  }

  return (
    <div className="bp-page">
      <a className="bp-skip" href="#beta-main">
        Skip to content
      </a>
      <header className="bp-header">
        <nav
          className="bp-nav bp-container"
          aria-label="Beta program navigation"
        >
          <BetaBrand />
          <div className="bp-nav-links">
            <a href="#program">The program</a>
            <a href="#platform">What you'll test</a>
            <a href="#data">Your data</a>
          </div>
          <a
            className="bp-button bp-button-small"
            href="#apply"
            aria-label="Apply for beta"
          >
            <span>
              Apply<span className="bp-nav-long"> for beta</span>
            </span>{" "}
            <ArrowUpRight size={16} />
          </a>
        </nav>
      </header>
      <main id="beta-main">
        <section className="bp-hero bp-container">
          <div className="bp-hero-top">
            <span className="bp-eyebrow">
              DOOBIELOGIC / BETA PARTNER PROGRAM
            </span>
            <span className="bp-status">
              <i /> APPLICATIONS OPEN
            </span>
          </div>
          <div className="bp-hero-grid">
            <div>
              <h1>
                Bring the real work.
                <br />
                <span>Help shape what's next.</span>
              </h1>
              <p className="bp-lead">
                A beta for the people running cannabis operations. Bring us the
                buying decisions, production handoffs and inventory headaches
                that software ought to handle better.
              </p>
              <div className="bp-hero-actions">
                <a className="bp-button" href="#apply">
                  Apply for beta access <ArrowUpRight size={18} />
                </a>
                <a className="bp-text-link" href="#program">
                  How the program works <ArrowDown size={16} />
                </a>
              </div>
              <p className="bp-fine">
                Free during your approved beta period. Access follows a fit
                review.
              </p>
            </div>
            <aside className="bp-hero-note">
              <span className="bp-eyebrow">A WORKING PARTNERSHIP</span>
              <p>
                Your workflows. Your feedback.
                <br />
                A better next iteration.
              </p>
              <span>
                Test agreed workflows. Share the friction.
                <br />
                Help make the next version better.
              </span>
            </aside>
          </div>
          <div className="bp-proof-window">
            <div className="bp-window-bar">
              <span>
                <i /> INSIDE DOOBIELOGIC
              </span>
              <span>BUYER WORKSPACE / BETA</span>
            </div>
            <a
              href="/marketing/buyer-workspace.webp"
              target="_blank"
              rel="noreferrer"
              aria-label="View full-size Buyer workspace screenshot"
            >
              <img
                src="/marketing/buyer-workspace.webp"
                srcSet="/marketing/buyer-workspace-480.webp 480w, /marketing/buyer-workspace-960.webp 960w, /marketing/buyer-workspace.webp 1440w"
                sizes="(max-width: 600px) calc(100vw - 36px), (max-width: 900px) calc(100vw - 48px), (max-width: 1320px) calc(100vw - 80px), 1240px"
                width="1440"
                height="1000"
                alt="Actual DoobieLogic Buyer workspace showing sales trends and category mix using synthetic demo data"
                fetchPriority="high"
              />
            </a>
            <div className="bp-image-caption">
              <span>Actual product interface · Synthetic demo data · Beta</span>
              <a
                href="/marketing/buyer-workspace.webp"
                target="_blank"
                rel="noreferrer"
              >
                View full size <ArrowUpRight size={14} />
              </a>
            </div>
          </div>
          <div className="bp-operation-line">
            <span>BUILT AROUND YOUR OPERATION</span>
            <p>
              Cultivation <b> / </b> Production <b> / </b> Retail <b> / </b>{" "}
              Wholesale <b> / </b> Vertically integrated
            </p>
          </div>
        </section>

        <section
          className="bp-section bp-container"
          id="program"
          aria-labelledby="program-title"
        >
          <div className="bp-section-head">
            <div>
              <span className="bp-eyebrow">01 / THE EXCHANGE</span>
              <h2 id="program-title">
                You know the work.
                <br />
                We want the feedback.
              </h2>
            </div>
            <p>
              The beta pairs approved access with practical testing. We agree on
              the scope, then learn from what happens when your team uses it.
            </p>
          </div>
          <div className="bp-exchange">
            <article>
              <Layers3 size={27} />
              <h3>Room to work.</h3>
              <p>
                Free access during your approved beta period, agreed workflows
                to evaluate and a direct feedback channel with development.
              </p>
              <span>YOU RECEIVE / ACCESS + A VOICE</span>
            </article>
            <article>
              <MessageSquare size={27} />
              <h3>Tell us where it breaks down.</h3>
              <p>
                Use the agreed workflows. Report bugs, awkward steps and missing
                context. Share approved test data and join structured feedback.
              </p>
              <span>YOU BRING / EXPERIENCE + FEEDBACK</span>
            </article>
          </div>
        </section>

        <section className="bp-fit" aria-labelledby="fit-title">
          <div className="bp-container bp-fit-grid">
            <div>
              <span className="bp-eyebrow">THE RIGHT KIND OF EARLY</span>
              <h2 id="fit-title">
                A real operation.
                <br />A defined place to start.
              </h2>
            </div>
            <div>
              <p>
                This is for licensed cannabis teams willing to test
                thoughtfully, name the gaps and help us improve. Start with a
                workflow your people know well.
              </p>
              <ul>
                <li>
                  <Check size={18} /> An operator who can own the feedback
                </li>
                <li>
                  <Check size={18} /> A specific workflow to evaluate
                </li>
                <li>
                  <Check size={18} /> Approved data and agreed testing
                  boundaries
                </li>
              </ul>
              <p className="bp-fit-note">
                Beta access is selective. Features, integrations and coverage
                vary by workflow and facility. Confirm the fit before relying on
                the platform in your operation.
              </p>
            </div>
          </div>
        </section>

        <section
          className="bp-section bp-container"
          id="platform"
          aria-labelledby="platform-title"
        >
          <div className="bp-section-head">
            <div>
              <span className="bp-eyebrow">02 / THE TESTING GROUND</span>
              <h2 id="platform-title">
                Pick the workflow.
                <br />
                Follow it through.
              </h2>
            </div>
            <p>
              These are areas to explore together, not a promise that every
              workflow is ready for every business. Your approved scope comes
              first.
            </p>
          </div>
          <div className="bp-workflows">
            {workflows.map(([number, title, body]) => (
              <article key={number}>
                <span>{number}</span>
                <div>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section
          className="bp-data bp-container"
          id="data"
          aria-labelledby="data-title"
        >
          <ShieldCheck size={30} />
          <div>
            <span className="bp-eyebrow">
              CLEAR BOUNDARIES, BEFORE YOU START
            </span>
            <h2 id="data-title">
              Agree on the data.
              <br />
              Keep people in control.
            </h2>
            <p>
              Participation includes sharing approved usage, diagnostic or
              operational test data under the Beta Participation &amp; Data Use
              Agreement. Confirm what will be shared and the testing scope
              before onboarding.
            </p>
            <p>
              AI assistance supports review. Employees remain responsible for
              governed actions, and beta participation does not replace your
              compliance obligations.
            </p>
          </div>
          <a className="bp-text-link" href="mailto:info@doobielogic.io">
            Request the beta agreement <ArrowUpRight size={17} />
          </a>
        </section>

        <section
          className="bp-section bp-container"
          aria-labelledby="steps-title"
        >
          <div className="bp-section-head">
            <div>
              <span className="bp-eyebrow">
                03 / FROM APPLICATION TO FEEDBACK
              </span>
              <h2 id="steps-title">
                Start small.
                <br />
                Learn something useful.
              </h2>
            </div>
          </div>
          <ol className="bp-steps">
            {steps.map(([number, title, body]) => (
              <li key={number}>
                <span>{number}</span>
                <h3>{title}</h3>
                <p>{body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="bp-apply" id="apply" aria-labelledby="apply-title">
          <div className="bp-container bp-apply-grid">
            <aside className="bp-apply-intro">
              <span className="bp-eyebrow">YOUR TURN</span>
              <h2 id="apply-title">
                Show us where
                <br />
                the work gets hard.
              </h2>
              <p>
                Tell us about your operation and one problem you want to solve.
                We review applications against the current beta phase.
              </p>
              <div className="bp-apply-note">
                <ClipboardCheck size={24} />
                <strong>Application first. Access after review.</strong>
                <p>
                  Submitting this form does not create an account or guarantee
                  acceptance.
                </p>
              </div>
              <a className="bp-text-link" href="mailto:info@doobielogic.io">
                Have a question first? <ArrowUpRight size={16} />
              </a>
            </aside>
            <form
              className="bp-form"
              onSubmit={handleSubmit}
              aria-labelledby="form-title"
              aria-busy={submitting}
            >
              <div className="bp-form-heading">
                <div>
                  <span className="bp-eyebrow">BETA PARTNER APPLICATION</span>
                  <h3 id="form-title">Tell us about your operation.</h3>
                </div>
                <span>FREE TO APPLY</span>
              </div>
              <p className="bp-form-help">
                Fields are required unless marked optional.
              </p>
              <fieldset disabled={submitting}>
                <legend>Your details and operation</legend>
                <div className="bp-fields">
                  <label>
                    Full name
                    <input
                      name="name"
                      autoComplete="name"
                      minLength={2}
                      maxLength={120}
                      required
                      placeholder="Your name"
                    />
                  </label>
                  <label>
                    Work email
                    <input
                      name="email"
                      type="email"
                      autoComplete="email"
                      minLength={5}
                      maxLength={254}
                      required
                      placeholder="you@company.com"
                    />
                  </label>
                  <label>
                    Company
                    <input
                      name="company"
                      autoComplete="organization"
                      minLength={2}
                      maxLength={160}
                      required
                      placeholder="Cannabis business"
                    />
                  </label>
                  <label>
                    Your role
                    <input
                      name="role"
                      autoComplete="organization-title"
                      minLength={2}
                      maxLength={120}
                      required
                      placeholder="Buyer, GM, Compliance…"
                    />
                  </label>
                  <label>
                    Operation type
                    <select name="operation" required defaultValue="">
                      <option value="" disabled>
                        Select one
                      </option>
                      <option>Retail</option>
                      <option>Cultivation</option>
                      <option>Manufacturing / Production</option>
                      <option>Extraction</option>
                      <option>Wholesale / Distribution</option>
                      <option>Vertically Integrated</option>
                      <option>Other</option>
                    </select>
                  </label>
                  <label>
                    Facilities / licenses
                    <select name="facilities" required defaultValue="">
                      <option value="" disabled>
                        Select range
                      </option>
                      <option>1</option>
                      <option>2–3</option>
                      <option>4–10</option>
                      <option>11+</option>
                    </select>
                  </label>
                  <label>
                    Primary POS / ERP <small>Optional</small>
                    <input
                      name="stack"
                      maxLength={240}
                      placeholder="Your current systems"
                    />
                  </label>
                  <label>
                    State
                    <input
                      name="state"
                      minLength={2}
                      maxLength={80}
                      required
                      placeholder="MA"
                    />
                  </label>
                  <label className="bp-field-wide">
                    What's the biggest operational problem you want DoobieLogic
                    to solve?
                    <textarea
                      name="pain"
                      required
                      minLength={10}
                      maxLength={4000}
                      rows={4}
                      placeholder="Where does your team lose time, context or visibility?"
                    />
                  </label>
                  <label className="bp-field-wide">
                    What would make DoobieLogic indispensable to your operation?{" "}
                    <small>Optional</small>
                    <textarea
                      name="must_have"
                      maxLength={4000}
                      rows={3}
                      placeholder="The workflow or outcome that matters most"
                    />
                  </label>
                  <label className="bp-honeypot" aria-hidden="true">
                    Website
                    <input
                      name="website"
                      maxLength={200}
                      tabIndex={-1}
                      autoComplete="off"
                    />
                  </label>
                </div>
                <label className="bp-consent">
                  <input name="consent" type="checkbox" required />
                  <span>
                    I understand beta participation includes structured feedback
                    and the sharing of approved usage, diagnostic, or
                    operational test data under the Beta Participation &amp;
                    Data Use Agreement.
                  </span>
                </label>
                <button
                  className="bp-button bp-submit"
                  type="submit"
                  disabled={submitting}
                >
                  {submitting ? (
                    "Submitting…"
                  ) : (
                    <>
                      Submit Beta Application <ArrowRight size={18} />
                    </>
                  )}
                </button>
              </fieldset>
              <p className="bp-submit-note">
                We use the details you provide to review your application and
                follow up.
              </p>
              {(error || submitted) && (
                <div
                  ref={feedback}
                  tabIndex={-1}
                  className={`bp-feedback ${error ? "bp-error" : "bp-success"}`}
                  role={error ? "alert" : "status"}
                >
                  {error ? (
                    <>
                      <strong>We could not confirm submission.</strong>
                      <span>{error}</span>
                    </>
                  ) : (
                    <>
                      <CircleCheck size={22} />
                      <strong>Application received.</strong>
                      <span>
                        The DoobieLogic team will review your application and
                        follow up using the email you provided.
                      </span>
                    </>
                  )}
                </div>
              )}
            </form>
          </div>
        </section>
      </main>
      <footer className="bp-footer bp-container">
        <div>
          <BetaBrand />
          <p>Cannabis operations. Built around the work.</p>
        </div>
        <nav aria-label="Beta footer">
          <a href="/">
            Explore DoobieLogic <ArrowUpRight size={14} />
          </a>
          <a href="mailto:info@doobielogic.io">Contact the team</a>
          <a href={APP_URL}>
            Operator log in <ArrowUpRight size={14} />
          </a>
        </nav>
        <span>BETA PARTNER PROGRAM</span>
      </footer>
    </div>
  );
}

