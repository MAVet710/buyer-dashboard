# Consulting frontend and brand validation

## Implementation

- `frontend/src/components/marketing/MarketingPage.tsx:12`: shared ConsultationCTA, including optional in-page href for preserving tool state.
- `frontend/src/components/marketing/MarketingPage.tsx:43`: original homepage footer extracted, with consulting/resources links and optional analytics consent.
- `frontend/src/components/marketing/MarketingPage.tsx:95`: public page shell, existing navigation, skip link and footer.
- `frontend/src/pages/ConsultingPages.tsx:70`: consulting hub with six service cards, operational diagnostic and tool/resource entry points.
- `frontend/src/pages/ConsultingPages.tsx:236`: seven data-driven service pages, review areas, deliverables, scope notes and contextual consultation.
- `frontend/src/pages/ConsultingPages.tsx:325`: resource library; `:364`: semantic full resource articles with contents navigation and sources.
- `frontend/src/pages/MarketingHome.tsx:655`: six consulting cards using the existing integration card grid.
- `frontend/src/advisory.css`: layout additions and scoped consent styling. Existing typography, palette, CTA, header and card primitives remain authoritative.

## Browser method

Production preview on loopback port 4197. Playwright Chromium displays the HTTPS public origin while intercepting every request: documents/assets are fetched only from loopback; APIs receive synthetic responses; other origins are blocked. No production submissions or API calls occur. HTTPS context matches production requirements such as crypto.randomUUID.

Harness: `.local/verify-consulting-layout.cjs`. Local artifacts: `.local/consulting-browser-qa/`. Tested 15 routes at 320, 390, 768, 1024, 1440 and 1920 pixels (90 combinations): homepage, consulting hub, all seven service pages, resource library, all three articles, and both tools.

Initial complete pass: no axe WCAG 2 A/AA and 2.1 AA violations, no page runtime errors, no duplicate IDs, and no header overflow in all 90 combinations. Nine 320px page combinations had form-field overflow. Cause reported to form owner: mobile grid used `1fr` with intrinsic input minimums. Other 81 combinations had no horizontal overflow. Final narrow-screen correction verification follows separately.

## Visual and interaction checks

Screenshots inspected for mobile homepage and consulting hub, 320px complete article, 768px consulting hub, 1024px homepage, 1440px consulting hub and 1920px tool. Compared with the pre-change homepage capture in `.local/consulting-baseline/home-1440.png`. The shared hierarchy, logo, copper emphasis, charcoal canvas, button shape and responsive spacing remain recognizable. Tool breadcrumb stacked vertically and was reported to its owner for a flex-layout correction.

Computed comparison at 390px (`.local/consulting-browser-qa/interactions.json`) found identical homepage/consulting values:

| Element | Verified values |
| --- | --- |
| Page | Inter/system stack; text rgb(242,238,232); background rgb(12,14,15) |
| H1 | Same font/color; 40.95px at 390px viewport |
| Primary CTA | rgb(246,154,91) fill; rgb(28,18,11) text; 5px radius; 14px type |
| Header | rgba(12,14,15,0.96); shared typography |

Mobile menu opens, Escape closes and returns focus to its toggle. Consultation CTA resolves #consultation with exactly one target and scrolls its top to approximately 105px below the sticky header. Query service is validated against the fixed service registry before form preselection. Service CTA uses the local form; shared CTA permits tool pages to do the same without losing calculated state.

TypeScript passed after integration. ESLint passed on all four changed page/navigation components. Form submission, scoring and CSV behavior are validated separately by the form/tool owner. This report does not claim Safari/Firefox testing, a Lighthouse run, or live backend delivery.

## Final correction verification

The rebuilt preview passed all 90 combinations: **zero horizontal overflow, zero header overflow, zero duplicate IDs, zero page runtime errors, and zero axe violations**. Report: `.local/consulting-browser-qa/report.json`. The 320px lead form and inventory tool now fit their containers. The tool breadcrumb uses the shared horizontal breadcrumb layout. A final visual inspection of the complete 320px diagnostic page confirms its service content, form and footer fit without clipping.

After this pass, two nonvisual analytics handlers were added as required: diagnostic hub CTA emits `audit_cta_clicked`; homepage service cards emit `service_internal_link_clicked`. Both use fixed content slugs and the existing consent-gated event function. No form values are included. Page source is now frozen for the parent agent's combined build/tests.

## Published copy verification — 2026-09-19 23:34 UTC

Read-only Playwright checks against `https://doobielogic.io/consulting` passed at **320, 390, 768 and 1440px**: the revised “Your cannabis operation shouldn’t need guesswork.” headline and supplied experience statement are present; no horizontal overflow or page runtime errors; canonical URL remains correct. Inspected the 390px hero and experience-section screenshots: text wraps cleanly, the primary button fits, and the existing charcoal/copper visual hierarchy is preserved.

Homepage and consulting navigation labels and destinations match exactly. `https://ops.doobielogic.io/home` retains the **DoobieLogic Ops** title and sign-in screen. Every non-GET/HEAD request was blocked by the browser harness; zero such requests occurred and zero leads were submitted.

Evidence: `.local/consulting-browser-qa/live-final-public.json`, `live-final-390-hero.png`, and `live-final-390-trust.png`. Harness: `.local/verify-consulting-live-final.cjs`. No production source changes were made for this verification.
