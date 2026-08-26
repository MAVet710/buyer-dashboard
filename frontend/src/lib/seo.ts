const MARKETING_ORIGIN = "https://doobielogic.io";
const MARKETING_TITLE = "DoobieLogic | Cannabis Operations Intelligence";
const MARKETING_DESCRIPTION =
  "Cannabis operations software for purchasing, inventory, receiving, METRC-aware audits, production, extraction, compliance, reporting, and facility management.";
const PRIVATE_ROBOTS = "noindex, nofollow, noarchive, nosnippet";
const PUBLIC_ROBOTS = "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1";

function upsertMeta(name: string, content: string): void {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[name="${name}"]`);
  if (!element) {
    element = document.createElement("meta");
    element.name = name;
    document.head.appendChild(element);
  }
  element.content = content;
}

function upsertCanonical(href: string): void {
  let element = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!element) {
    element = document.createElement("link");
    element.rel = "canonical";
    document.head.appendChild(element);
  }
  element.href = href;
}

function removeCanonical(): void {
  document.head.querySelector('link[rel="canonical"]')?.remove();
}

function setStructuredData(enabled: boolean): void {
  const id = "doobielogic-software-schema";
  document.getElementById(id)?.remove();
  if (!enabled) return;

  const script = document.createElement("script");
  script.id = id;
  script.type = "application/ld+json";
  script.textContent = JSON.stringify({
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "DoobieLogic",
    url: `${MARKETING_ORIGIN}/`,
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    description: MARKETING_DESCRIPTION,
    featureList: [
      "Cannabis purchasing and buying workflows",
      "Inventory and receiving operations",
      "METRC-aware inventory auditing",
      "Production and extraction operations",
      "Cannabis compliance workflows",
      "Operational reporting and analytics",
      "Organization and facility management",
    ],
    publisher: {
      "@type": "Organization",
      name: "DoobieLogic",
      url: `${MARKETING_ORIGIN}/`,
    },
  });
  document.head.appendChild(script);
}

export function configureSeo(marketing: boolean): void {
  if (!marketing) {
    document.title = "DoobieLogic Ops";
    upsertMeta("robots", PRIVATE_ROBOTS);
    upsertMeta("googlebot", PRIVATE_ROBOTS);
    removeCanonical();
    setStructuredData(false);
    return;
  }

  document.title = MARKETING_TITLE;
  upsertMeta("description", MARKETING_DESCRIPTION);
  upsertMeta("robots", PUBLIC_ROBOTS);
  upsertMeta("googlebot", PUBLIC_ROBOTS);
  upsertCanonical(`${MARKETING_ORIGIN}/`);
  setStructuredData(true);
}
