import { advisoryRoutes } from "./advisorySeo";
import { marketingFaqs } from "../components/marketing/content";

export const MARKETING_ORIGIN = "https://doobielogic.io";
export const MARKETING_TITLE = advisoryRoutes["/"].title;
export const MARKETING_DESCRIPTION = advisoryRoutes["/"].description;
const PRIVATE_ROBOTS = "noindex, nofollow, noarchive, nosnippet";
const PUBLIC_ROBOTS = "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1";
const SOCIAL_IMAGE = `${MARKETING_ORIGIN}/doobielogic-logo.webp`;
const normalizedPath = (pathname: string) => pathname === "/" ? "/" : pathname.replace(/\/$/, "");

export function seoPage(marketing: boolean, pathname: string) {
  const path = normalizedPath(pathname);
  const metadata = Object.hasOwn(advisoryRoutes, path) ? advisoryRoutes[path] : undefined;
  const publicPage = marketing && Boolean(metadata);
  return {
    publicPage,
    title: publicPage ? metadata!.title : "DoobieLogic Ops",
    description: publicPage ? metadata!.description : "Private DoobieLogic operations workspace.",
    canonical: publicPage ? `${MARKETING_ORIGIN}${path}` : null,
    robots: publicPage ? PUBLIC_ROBOTS : PRIVATE_ROBOTS,
    homepage: publicPage && path === "/",
    kind: metadata?.kind,
  };
}

export function marketingStructuredData(pathname = "/") {
  const page = seoPage(true, pathname);
  const graph: Record<string, unknown>[] = [
    { "@type": "Organization", "@id": `${MARKETING_ORIGIN}/#organization`, name: "DoobieLogic", url: `${MARKETING_ORIGIN}/`, logo: SOCIAL_IMAGE },
  ];
  if (page.homepage) {
    graph.push({ "@type": "SoftwareApplication", "@id": `${MARKETING_ORIGIN}/#software`, name: "DoobieLogic", url: `${MARKETING_ORIGIN}/`, applicationCategory: "BusinessApplication", operatingSystem: "Web", description: MARKETING_DESCRIPTION, publisher: { "@id": `${MARKETING_ORIGIN}/#organization` } });
    graph.push({ "@type": "FAQPage", "@id": `${MARKETING_ORIGIN}/#faq`, mainEntity: marketingFaqs.map(({ question, answer }) => ({ "@type": "Question", name: question, acceptedAnswer: { "@type": "Answer", text: answer } })) });
    return { "@context": "https://schema.org", "@graph": graph };
  }
  if (page.publicPage) graph.push({
    "@type": page.kind === "service" ? "Service" : page.kind === "article" ? "Article" : "WebPage",
    "@id": `${page.canonical}#page`, url: page.canonical, name: page.title,
    ...(page.kind === "article" ? { headline: page.title } : {}),
    description: page.description,
    ...(page.kind === "service" ? { provider: { "@id": `${MARKETING_ORIGIN}/#organization` } } : { publisher: { "@id": `${MARKETING_ORIGIN}/#organization` } }),
  });
  if (page.publicPage && pathname !== "/beta") {
    const parts = normalizedPath(pathname).split("/").filter(Boolean);
    graph.push({ "@type": "BreadcrumbList", itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: `${MARKETING_ORIGIN}/` },
      ...parts.map((part, i) => ({ "@type": "ListItem", position: i + 2,
        name: i === parts.length - 1 ? page.title.split(" | ")[0] : part[0].toUpperCase() + part.slice(1),
        item: `${MARKETING_ORIGIN}/${parts.slice(0, i + 1).join("/")}` })),
    ] });
  }
  return { "@context": "https://schema.org", "@graph": graph };
}

function upsertMeta(name: string, content: string, attribute: "name" | "property" = "name"): void {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[${attribute}="${name}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.setAttribute(attribute, name);
    document.head.appendChild(element);
  }
  element.content = content;
}

export function configureSeo(marketing: boolean): void {
  const page = seoPage(marketing, window.location.pathname);
  document.title = page.title;
  upsertMeta("description", page.description);
  upsertMeta("robots", page.robots);
  upsertMeta("googlebot", page.robots);
  document.head.querySelector('link[rel="canonical"]')?.remove();
  document.getElementById("doobielogic-software-schema")?.remove();
  document.head.querySelectorAll('meta[property^="og:"], meta[name^="twitter:"]').forEach((element) => element.remove());
  if (!page.publicPage || !page.canonical) return;

  const canonical = document.createElement("link");
  canonical.rel = "canonical";
  canonical.href = page.canonical;
  document.head.appendChild(canonical);
  for (const [name, content] of Object.entries({
    "og:type": page.kind === "article" ? "article" : "website", "og:site_name": "DoobieLogic", "og:title": page.title,
    "og:description": page.description, "og:url": page.canonical, "og:image": SOCIAL_IMAGE,
    "og:image:type": "image/webp", "og:image:width": "256", "og:image:height": "256", "og:image:alt": "DoobieLogic brand mark",
  })) upsertMeta(name, content, "property");
  for (const [name, content] of Object.entries({
    "twitter:card": "summary", "twitter:title": page.title,
    "twitter:description": page.description, "twitter:image": SOCIAL_IMAGE, "twitter:image:alt": "DoobieLogic brand mark",
  })) upsertMeta(name, content);
  if (page.publicPage && normalizedPath(window.location.pathname) !== "/beta") {
    const script = document.createElement("script");
    script.id = "doobielogic-software-schema";
    script.type = "application/ld+json";
    script.textContent = JSON.stringify(marketingStructuredData(window.location.pathname));
    document.head.appendChild(script);
  }
}
