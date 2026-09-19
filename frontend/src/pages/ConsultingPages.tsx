import { useEffect } from "react";
import { ArrowRight, Check, ArrowUpRight } from "lucide-react";
import {
  MarketingPage,
  ConsultationCTA,
} from "../components/marketing/MarketingPage";
import { ConsultingLeadForm } from "../components/marketing/ConsultingLeadForm";
import {
  services,
  operationalDiagnostic,
  resources,
  getConsultingService,
  getConsultingResource,
} from "../lib/consultingContent";
import { trackMarketingEvent } from "../lib/marketingAnalytics";
import "../advisory.css";

function Breadcrumbs({
  section,
  title,
}: {
  section: "Consulting" | "Resources";
  title?: string;
}) {
  return (
    <nav className="advisory-breadcrumbs mh-container" aria-label="Breadcrumb">
      <a href="/">Home</a>
      <span aria-hidden="true">/</span>
      {title ? (
        <>
          <a href={section === "Consulting" ? "/consulting" : "/resources"}>
            {section}
          </a>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{title}</span>
        </>
      ) : (
        <span aria-current="page">{section}</span>
      )}
    </nav>
  );
}

function Consultation({ service }: { service?: string }) {
  return <ConsultingLeadForm service={service} />;
}

function ResourceCards({ slugs }: { slugs?: string[] }) {
  const selected = slugs
    ? resources.filter((item) => slugs.includes(item.slug))
    : resources;
  return (
    <div className="mh-integration-grid">
      {selected.map((item) => (
        <article key={item.slug}>
          <span className="mh-label">Operator resource</span>
          <h3>
            <a href={`/resources/${item.slug}`}>{item.title}</a>
          </h3>
          <p>{item.summary}</p>
          <a className="mh-text-link" href={`/resources/${item.slug}`}>
            Read the guide <ArrowRight size={17} aria-hidden="true" />
          </a>
        </article>
      ))}
    </div>
  );
}

function ConsultingHub() {
  const requestedService =
    new URLSearchParams(window.location.search).get("service") || undefined;
  const selectedService =
    requestedService && getConsultingService(requestedService)
      ? requestedService
      : undefined;
  return (
    <>
      <Breadcrumbs section="Consulting" />
      <section
        className="mh-hero mh-container"
        aria-labelledby="consulting-title"
      >
        <span className="mh-eyebrow">DoobieLogic Advisory</span>
        <div className="mh-hero-layout">
          <div className="mh-hero-copy">
            <h1 id="consulting-title">
              Your cannabis operation
              <br />
              <span>shouldn’t need guesswork.</span>
            </h1>
            <p>
              Hands-on consulting for cannabis retailers, cultivators,
              manufacturers and technology teams. Work through inventory and
              purchasing decisions, broken process handoffs, production
              visibility, and the gaps between Metrc and your ERP—with a
              practical plan your team can use.
            </p>
            <div className="mh-hero-actions">
              <ConsultationCTA />
              <a className="mh-text-link" href="#services">
                Explore the services <ArrowRight size={17} />
              </a>
            </div>
            <small>
              Consulting scope and fees are agreed before work begins.
            </small>
          </div>
          <div className="mh-hero-aside">
            <span className="mh-label">A PRACTICAL STARTING POINT</span>
            <p>
              The records you have. The systems you use. The work your team
              needs to move forward.
            </p>
            <strong>
              Understand the friction.
              <br />
              Agree on the next move.
            </strong>
          </div>
        </div>
      </section>
      <section
        className="mh-section mh-container"
        id="services"
        aria-labelledby="services-heading"
      >
        <div className="mh-section-top">
          <div>
            <span className="mh-eyebrow">Focused support</span>
            <h2 id="services-heading">
              Start where the
              <br />
              operation needs you.
            </h2>
          </div>
          <p>
            Choose a specific review or start with an operational diagnostic to
            identify the right scope.
          </p>
        </div>
        <div className="mh-integration-grid">
          {services.map((item, index) => (
            <article key={item.slug}>
              <span className="mh-label">0{index + 1} / Consulting</span>
              <h3>
                <a href={`/consulting/${item.slug}`}>{item.title}</a>
              </h3>
              <p>{item.summary}</p>
              <p>
                <strong>{item.price}</strong>
              </p>
              <a
                className="mh-text-link"
                href={`/consulting/${item.slug}`}
                onClick={() =>
                  trackMarketingEvent("service_internal_link_clicked", {
                    placement: "consulting",
                    item: item.slug,
                  })
                }
              >
                Explore the scope <ArrowRight size={17} />
              </a>
            </article>
          ))}
        </div>
      </section>
      <section
        className="mh-container mh-ai"
        aria-labelledby="diagnostic-heading"
      >
        <div>
          <span className="mh-eyebrow">When the starting point is unclear</span>
          <h2 id="diagnostic-heading">{operationalDiagnostic.title}</h2>
          <p>{operationalDiagnostic.summary}</p>
          <a
            className="mh-button"
            href={`/consulting/${operationalDiagnostic.slug}`}
            onClick={() =>
              trackMarketingEvent("audit_cta_clicked", {
                placement: "consulting",
                item: operationalDiagnostic.slug,
              })
            }
          >
            Explore the diagnostic <ArrowUpRight size={18} />
          </a>
        </div>
        <div>
          <span className="mh-label">A defined first engagement</span>
          <p>{operationalDiagnostic.intro}</p>
          <strong>{operationalDiagnostic.price}</strong>
        </div>
      </section>
      <section className="mh-section mh-container">
        <div className="mh-section-top">
          <div>
            <span className="mh-eyebrow">Prepare for the conversation</span>
            <h2>
              Start with your
              <br />
              own operating picture.
            </h2>
          </div>
          <p>
            Use a self-assessment or review an inventory CSV to organize your
            questions. These tools provide discussion context for a closer
            operational review.
          </p>
        </div>
        <div className="mh-control-grid">
          <article>
            <h3>Operations health check</h3>
            <p>Review the habits and handoffs supporting your team.</p>
            <a className="mh-text-link" href="/tools/operations-score">
              Take the assessment <ArrowRight size={17} />
            </a>
          </article>
          <article>
            <h3>Inventory health check</h3>
            <p>
              Open an inventory CSV, map its columns and review the health
              checks in your browser. Raw CSV rows stay in your browser and are
              not attached to a consulting inquiry.
            </p>
            <a className="mh-text-link" href="/tools/inventory-health-check">
              Explore your inventory <ArrowRight size={17} />
            </a>
          </article>
          <article>
            <h3>Operator resources</h3>
            <p>Practical reading for inventory reviews and system readiness.</p>
            <a className="mh-text-link" href="/resources">
              Read the guides <ArrowRight size={17} />
            </a>
          </article>
        </div>
      </section>
      <section
        className="mh-section mh-container"
        aria-labelledby="experience-heading"
      >
        <div className="mh-section-top">
          <div>
            <span className="mh-eyebrow">Experience close to the work</span>
            <h2 id="experience-heading">
              I’ve worked inside the problems I’m consulting on.
            </h2>
          </div>
          <p>
            The work starts with what your team is carrying: inventory that
            needs explaining, a purchasing decision with incomplete context, or
            a handoff between people and systems. We review the records, talk
            through the process and agree on what to improve first.
          </p>
        </div>
      </section>
      <section
        className="mh-section mh-container"
        aria-labelledby="software-heading"
      >
        <div className="mh-section-top">
          <div>
            <span className="mh-eyebrow">Consulting and software</span>
            <h2 id="software-heading">
              Sometimes you need software. Sometimes you need a better process.
            </h2>
          </div>
          <div>
            <p>
              Sometimes you need someone who understands both. Consulting starts
              with your operation and the systems you use today. Where software
              could help, we can also discuss whether the DoobieLogic beta is a
              fit for the agreed workflow.
            </p>
            <a className="mh-text-link" href="/#platform">
              Explore the DoobieLogic platform{" "}
              <ArrowRight size={17} aria-hidden="true" />
            </a>
          </div>
        </div>
      </section>
      <Consultation service={selectedService} />
    </>
  );
}

function ServicePage({ slug }: { slug: string }) {
  const service = getConsultingService(slug);
  if (!service) return <NotFound />;
  return (
    <>
      <Breadcrumbs section="Consulting" title={service.title} />
      <section className="mh-hero mh-container">
        <span className="mh-eyebrow">Focused consulting / Defined scope</span>
        <div className="mh-hero-layout">
          <div className="mh-hero-copy">
            <h1>{service.title}</h1>
            <p>{service.intro}</p>
            <div className="mh-hero-actions">
              <ConsultationCTA service={service.slug} href="#consultation">
                {service.cta.label}
              </ConsultationCTA>
            </div>
            <small>{service.price}</small>
          </div>
          <div className="mh-hero-aside">
            <span className="mh-label">THE STARTING POINT</span>
            <p>{service.summary}</p>
            <strong>
              Scope first.
              <br />
              Practical next steps.
            </strong>
          </div>
        </div>
      </section>
      <section className="mh-section mh-container advisory-scope">
        <div>
          <span className="mh-eyebrow">What we review</span>
          <h2>
            A closer look
            <br />
            at the operation.
          </h2>
          <ul className="advisory-list">
            {service.areas.map((area) => (
              <li key={area}>
                <Check size={17} aria-hidden="true" />
                <span>{area}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <span className="mh-eyebrow">What you receive</span>
          <h2>
            Work your team
            <br />
            can take forward.
          </h2>
          <ul className="advisory-list">
            {service.deliverables.map((item) => (
              <li key={item}>
                <Check size={17} aria-hidden="true" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <p>
            {service.scopeNote ||
              "The engagement scope, access requirements, deliverables and fees are agreed before work begins."}
          </p>
        </div>
      </section>
      <section className="mh-section mh-container">
        <div className="mh-section-top">
          <div>
            <span className="mh-eyebrow">Useful context</span>
            <h2>
              Read before
              <br />
              we talk.
            </h2>
          </div>
          <a className="mh-text-link" href="/resources">
            All resources <ArrowRight size={17} />
          </a>
        </div>
        <ResourceCards slugs={service.relatedResources} />
      </section>
      <Consultation service={service.slug} />
    </>
  );
}

function ResourcesHub() {
  return (
    <>
      <Breadcrumbs section="Resources" />
      <section className="mh-hero mh-container">
        <div className="mh-hero-copy">
          <span className="mh-eyebrow">Operator resources</span>
          <h1>
            Useful context.
            <br />
            <span>Clearer questions.</span>
          </h1>
          <p>
            Practical guides for reviewing inventory, preparing a reconciliation
            and understanding system readiness. Use them to organize a
            conversation around your operation.
          </p>
        </div>
      </section>
      <section
        className="mh-section mh-container"
        aria-label="Resource library"
      >
        <ResourceCards />
      </section>
      <section className="mh-final mh-container">
        <span className="mh-eyebrow">Put the context to work</span>
        <h2>
          Bring your questions.
          <br />
          Start with your operation.
        </h2>
        <p>Discuss the workflow or decision that needs a closer look.</p>
        <ConsultationCTA placement="final" />
      </section>
    </>
  );
}

function ResourceArticle({ slug }: { slug: string }) {
  const resource = getConsultingResource(slug);
  if (!resource) return <NotFound />;
  return (
    <>
      <Breadcrumbs section="Resources" title={resource.title} />
      <article className="mh-container advisory-article">
        <header className="mh-hero">
          <span className="mh-eyebrow">Operator resource</span>
          <div className="mh-hero-copy">
            <h1>{resource.title}</h1>
            <p>{resource.summary}</p>
            <small>
              Reviewed{" "}
              <time dateTime={resource.reviewedOn}>{resource.reviewedOn}</time>
            </small>
          </div>
        </header>
        <div className="advisory-reading-layout">
          <aside>
            <nav aria-label="In this guide">
              <span className="mh-label">In this guide</span>
              {resource.sections.map((section) => (
                <a
                  className="mh-text-link"
                  href={`#${section.id}`}
                  key={section.id}
                >
                  {section.title}
                </a>
              ))}
            </nav>
          </aside>
          <div className="advisory-prose">
            {resource.scopeNote && (
              <p className="advisory-scope-note">{resource.scopeNote}</p>
            )}
            {resource.sections.map((section) => (
              <section id={section.id} key={section.id}>
                <h2>{section.title}</h2>
                {section.paragraphs.map((text) => (
                  <p key={text}>{text}</p>
                ))}
                {section.bullets && (
                  <ul>
                    {section.bullets.map((text) => (
                      <li key={text}>{text}</li>
                    ))}
                  </ul>
                )}
              </section>
            ))}
            {resource.sources.length > 0 && (
              <section>
                <h2>Sources &amp; further reading</h2>
                <ul>
                  {resource.sources.map((source) => (
                    <li key={source.url}>
                      <a className="mh-text-link" href={source.url}>
                        {source.title}{" "}
                        <ArrowUpRight size={15} aria-hidden="true" />
                      </a>
                      <span className="mh-muted"> — {source.publisher}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <section>
              <h2>Discuss your operating context.</h2>
              <p>
                A guide can help frame the question. A scoped review starts with
                your records, systems and team.
              </p>
              <ConsultationCTA
                service={resource.relatedServices[0]}
                placement="resources"
              />
            </section>
          </div>
        </div>
      </article>
      <section className="mh-section mh-container">
        <span className="mh-eyebrow">Related support</span>
        <div className="mh-control-grid">
          {services
            .filter((item) => resource.relatedServices.includes(item.slug))
            .map((item) => (
              <article key={item.slug}>
                <h3>{item.title}</h3>
                <p>{item.summary}</p>
                <a className="mh-text-link" href={`/consulting/${item.slug}`}>
                  Explore service <ArrowRight size={17} />
                </a>
              </article>
            ))}
        </div>
      </section>
    </>
  );
}

function NotFound() {
  return (
    <section className="mh-section mh-container">
      <span className="mh-eyebrow">Page not found</span>
      <h1>Find your next starting point.</h1>
      <p>This resource or service is not available at this address.</p>
      <a className="mh-text-link" href="/consulting">
        Explore consulting <ArrowRight size={17} />
      </a>
      <a className="mh-text-link" href="/resources">
        Explore resources <ArrowRight size={17} />
      </a>
    </section>
  );
}

export function ConsultingPages() {
  const path = window.location.pathname.replace(/\/+$/, "");
  const slug = path.split("/")[2];
  const isResources = path === "/resources" || path.startsWith("/resources/");
  useEffect(() => {
    if (isResources && (!slug || !getConsultingResource(slug))) return;
    if (!isResources && slug && !getConsultingService(slug)) return;
    trackMarketingEvent(
      isResources
        ? "resource_article_view"
        : slug
          ? "service_page_view"
          : "consulting_page_view",
      { placement: isResources ? "resources" : "consulting", item: slug },
    );
  }, [isResources, slug]);
  return (
    <MarketingPage>
      {isResources ? (
        slug ? (
          <ResourceArticle slug={slug} />
        ) : (
          <ResourcesHub />
        )
      ) : slug ? (
        <ServicePage slug={slug} />
      ) : (
        <ConsultingHub />
      )}
    </MarketingPage>
  );
}
