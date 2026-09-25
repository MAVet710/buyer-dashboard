import { useMemo, useState } from "react";
import {
  ArrowRight, BarChart3, Bot, Boxes, Factory, Home, Search, Settings,
  ShieldCheck, ShoppingCart, Sprout, Store, Workflow,
} from "lucide-react";
import { APP_URL } from "../lib/brand";
import {
  helpArticleByPath, helpCategories, helpCategoryById, helpSearch,
  type HelpArticle,
} from "../lib/helpContent";
import { MarketingPage } from "../components/marketing/MarketingPage";
import "../help-center.css";

const icons = {
  "getting-started": Workflow, home: Home, buying: ShoppingCart, inventory: Boxes,
  cultivation: Sprout, production: Factory, wholesale: Store, compliance: ShieldCheck,
  reports: BarChart3, settings: Settings, intelligence: Bot,
} as const;

function normalizedPath() {
  const raw = window.location.pathname || "/help";
  return raw === "/" ? raw : raw.replace(/\/+$/, "");
}

function articleTitle(path: string) {
  return helpArticleByPath.get(path)?.title ?? path.split("/").filter(Boolean).at(-1)?.replaceAll("-", " ") ?? "Guide";
}

function HelpSearch({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <label className="help-search">
      <Search size={20} aria-hidden="true" />
      <span className="sr-only">Search the DoobieLogic Help Center</span>
      <input type="search" value={value} onChange={event => onChange(event.target.value)}
        placeholder="Search receiving, Metrc, audits, extraction, labels..." />
    </label>
  );
}

function HelpLanding() {
  const [query, setQuery] = useState("");
  const results = useMemo(() => helpSearch(query), [query]);
  const resultPaths = useMemo(() => new Set(results.map(item => item.path)), [results]);

  return (
    <MarketingPage>
      <section className="help-hero mh-container" id="top">
        <div className="help-hero-copy">
          <span className="mh-eyebrow">DoobieLogic Help Center</span>
          <h1>How the work<br/><span>actually gets done.</span></h1>
          <p>Step-by-step guidance for the real DoobieLogic workspaces. Every product image in these guides is a screen capture from the working application, not a rendering.</p>
          <HelpSearch value={query} onChange={setQuery} />
          <div className="help-hero-links">
            <a className="mh-button" href="/help/getting-started">Start with the basics <ArrowRight size={17}/></a>
            <a className="mh-text-link" href={APP_URL}>Open DoobieLogic <ArrowRight size={16}/></a>
          </div>
        </div>
        <figure className="help-hero-shot">
          <img src="/help/screens/home-guide.webp" alt="Real DoobieLogic Operations Home captured in the DEV Sandbox" />
          <figcaption><span>REAL PRODUCT CAPTURE</span> DEV Sandbox · Operations Home</figcaption>
        </figure>
      </section>

      <section className="help-trust-strip"><div className="mh-container">
        <span>REAL WORKSPACES</span><span>STEP BY STEP</span><span>FACILITY CONTEXT</span><span>TRACEABILITY AWARE</span>
      </div></section>

      {query.trim() ? (
        <section className="help-section mh-container" aria-labelledby="help-search-results">
          <div className="help-section-heading">
            <span className="mh-eyebrow">Search results</span>
            <h2 id="help-search-results">{results.length ? results.length + " guide" + (results.length === 1 ? "" : "s") + " found" : "No guides found"}</h2>
            <p>{results.length ? "Results for “" + query.trim() + "”." : "Try a workflow name, module, or task."}</p>
          </div>
          <div className="help-results-grid">{results.map(item => <GuideLink article={item} key={item.path}/>)}</div>
        </section>
      ) : null}

      <section className="help-section mh-container" aria-labelledby="browse-help">
        <div className="help-section-heading">
          <span className="mh-eyebrow">Browse by work area</span>
          <h2 id="browse-help">The Help Center mirrors the app.</h2>
          <p>Start with the same work area you use in DoobieLogic, then drill into the task you are trying to complete.</p>
        </div>
        <div className="help-category-grid">
          {helpCategories.map(category => {
            const Icon = icons[category.id as keyof typeof icons] ?? Workflow;
            const visible = query.trim() ? category.articles.filter(path => resultPaths.has(path)) : category.articles;
            if (query.trim() && !visible.length) return null;
            return (
              <article className="help-category-card" key={category.id}>
                <div className="help-category-icon"><Icon size={23}/></div>
                <h3>{category.title}</h3><p>{category.description}</p>
                <div className="help-category-links">{visible.slice(0, 8).map(path => (
                  <a href={path} key={path}>{articleTitle(path)} <ArrowRight size={13}/></a>
                ))}</div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="help-proof mh-container">
        <div><span className="mh-eyebrow">Built from the product</span><h2>See the screen.<br/>Then do the work.</h2>
          <p>Guides use the live DEV Sandbox so navigation, labels, and controls stay grounded in the application operators actually use.</p></div>
        <div className="help-proof-shots">
          <img src="/help/screens/inventory-guide.webp" alt="Real DoobieLogic Inventory workspace" loading="lazy"/>
          <img src="/help/screens/extraction-guide.webp" alt="Real DoobieLogic Extraction workspace" loading="lazy"/>
        </div>
      </section>
    </MarketingPage>
  );
}

function GuideLink({ article }: { article: HelpArticle }) {
  return (
    <a className="help-result-card" href={article.path}>
      <span>{helpCategoryById.get(article.category)?.title ?? article.category}</span>
      <strong>{article.title}</strong><p>{article.summary}</p>
      <em>Read guide <ArrowRight size={14}/></em>
    </a>
  );
}

function HelpArticleView({ article }: { article: HelpArticle }) {
  const category = helpCategoryById.get(article.category);
  const related = (article.related ?? []).map(path => helpArticleByPath.get(path)).filter((item): item is HelpArticle => Boolean(item));

  return (
    <MarketingPage>
      <div className="help-article-shell mh-container" id="top">
        <nav className="help-breadcrumbs" aria-label="Breadcrumb">
          <a href="/help">Help Center</a><span>/</span><span>{category?.title ?? "Guide"}</span><span>/</span><strong>{article.title}</strong>
        </nav>
        <div className="help-article-layout">
          <aside className="help-article-nav">
            <a className="help-back" href="/help">← All guides</a>
            <span className="help-nav-label">{category?.title}</span>
            <nav aria-label={(category?.title ?? "Help") + " guides"}>
              {(category?.articles ?? []).map(path => (
                <a className={path === article.path ? "active" : ""} href={path} key={path}>{articleTitle(path)}</a>
              ))}
            </nav>
          </aside>
          <article className="help-article">
            <header className="help-article-header">
              <span className="mh-eyebrow">{category?.title ?? "DoobieLogic Help"}</span>
              <h1>{article.title}</h1><p>{article.summary}</p>
              {article.navPath ? <div className="help-nav-path"><strong>In DoobieLogic</strong><span>{article.navPath}</span></div> : null}
            </header>

            {article.screenshot ? <figure className="help-workspace-shot">
              <img src={article.screenshot} alt={article.screenshotAlt ?? article.title} />
              <figcaption><span>REAL PRODUCT CAPTURE</span> Captured from the live DoobieLogic DEV Sandbox. Demonstration workspace only.</figcaption>
            </figure> : null}

            {article.thingsToKnow?.length ? <section className="help-callout">
              <h2>Things to know</h2><ul>{article.thingsToKnow.map(item => <li key={item}>{item}</li>)}</ul>
            </section> : null}

            <div className="help-article-sections">
              {article.sections.map((section, index) => <section id={"step-" + (index + 1)} key={section.title}>
                <span className="help-section-number">{String(index + 1).padStart(2, "0")}</span>
                <h2>{section.title}</h2>{section.body ? <p>{section.body}</p> : null}
                {section.steps?.length ? <ol>{section.steps.map(step => <li key={step}>{step}</li>)}</ol> : null}
                {section.notes?.length ? <div className="help-note"><strong>Keep in mind</strong><ul>{section.notes.map(note => <li key={note}>{note}</li>)}</ul></div> : null}
              </section>)}
            </div>

            <section className="help-finish">
              <div><span className="mh-eyebrow">Ready to work it?</span><h2>Open the real workspace.</h2>
                <p>Use the guide beside DoobieLogic and complete the task in the facility context that owns the record.</p></div>
              <a className="mh-button" href={APP_URL}>Open DoobieLogic <ArrowRight size={17}/></a>
            </section>

            {related.length ? <section className="help-related"><span className="mh-eyebrow">Related guides</span>
              <div className="help-related-grid">{related.map(item => <GuideLink article={item} key={item.path}/>)}</div>
            </section> : null}
          </article>
        </div>
      </div>
    </MarketingPage>
  );
}

function HelpNotFound() {
  return <MarketingPage><section className="help-not-found mh-container">
    <span className="mh-eyebrow">Help Center</span><h1>That guide is not here yet.</h1>
    <p>The Help Center could not match this address to a published DoobieLogic guide.</p>
    <a className="mh-button" href="/help">Browse all guides <ArrowRight size={17}/></a>
  </section></MarketingPage>;
}

export function HelpCenterPage() {
  const path = normalizedPath();
  if (path === "/help") return <HelpLanding />;
  const article = helpArticleByPath.get(path);
  return article ? <HelpArticleView article={article}/> : <HelpNotFound/>;
}

