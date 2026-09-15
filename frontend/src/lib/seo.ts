import { marketingFaqs } from "../components/marketing/content";

export const MARKETING_ORIGIN = "https://doobielogic.io";
export const MARKETING_TITLE = "DoobieLogic | Cannabis ERP & Operations Software";
export const MARKETING_DESCRIPTION = "Cannabis ERP in beta for cultivation, production, retail, and vertically integrated teams. Explore the DoobieLogic operational workspaces and apply for beta access.";
const PRIVATE_ROBOTS = "noindex, nofollow, noarchive, nosnippet";
const PUBLIC_ROBOTS = "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1";
const SOCIAL_IMAGE = `${MARKETING_ORIGIN}/marketing/doobielogic-brand.png`;

export function seoPage(marketing: boolean, pathname: string) {
  const publicPage = marketing && !/^\/(?:portal|store)(?:\/|$)/i.test(pathname);
  const beta = /^\/beta\/?$/.test(pathname);
  return {
    publicPage,
    title: publicPage ? (beta ? "Apply for the DoobieLogic Beta | Cannabis Operations Software" : MARKETING_TITLE) : "DoobieLogic Ops",
    description: publicPage ? (beta ? "Apply to the DoobieLogic beta partner program. Evaluate cannabis operations workflows, share feedback, and help shape the product during your approved beta period." : MARKETING_DESCRIPTION) : "Private DoobieLogic operations workspace.",
    canonical: publicPage ? `${MARKETING_ORIGIN}/${beta ? "beta" : ""}` : null,
    robots: publicPage ? PUBLIC_ROBOTS : PRIVATE_ROBOTS,
    homepage: publicPage && !beta,
  };
}

export function marketingStructuredData() {
  return {
    "@context": "https://schema.org",
    "@graph": [
      { "@type": "Organization", "@id": `${MARKETING_ORIGIN}/#organization`, name: "DoobieLogic", url: `${MARKETING_ORIGIN}/`, logo: SOCIAL_IMAGE },
      {
        "@type": "SoftwareApplication", "@id": `${MARKETING_ORIGIN}/#software`, name: "DoobieLogic",
        url: `${MARKETING_ORIGIN}/`, applicationCategory: "BusinessApplication", operatingSystem: "Web",
        description: MARKETING_DESCRIPTION, publisher: { "@id": `${MARKETING_ORIGIN}/#organization` },
      },
      {
        "@type": "FAQPage", "@id": `${MARKETING_ORIGIN}/#faq`,
        mainEntity: marketingFaqs.map(({ question, answer }) => ({
          "@type": "Question", name: question, acceptedAnswer: { "@type": "Answer", text: answer },
        })),
      },
    ],
  };
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
    "og:type": "website", "og:site_name": "DoobieLogic", "og:title": page.title,
    "og:description": page.description, "og:url": page.canonical, "og:image": SOCIAL_IMAGE,
    "og:image:type": "image/png", "og:image:width": "500", "og:image:height": "500", "og:image:alt": "DoobieLogic brand mark",
  })) upsertMeta(name, content, "property");
  for (const [name, content] of Object.entries({
    "twitter:card": "summary", "twitter:title": page.title,
    "twitter:description": page.description, "twitter:image": SOCIAL_IMAGE, "twitter:image:alt": "DoobieLogic brand mark",
  })) upsertMeta(name, content);
  if (page.homepage) {
    const script = document.createElement("script");
    script.id = "doobielogic-software-schema";
    script.type = "application/ld+json";
    script.textContent = JSON.stringify(marketingStructuredData());
    document.head.appendChild(script);
  }
}
