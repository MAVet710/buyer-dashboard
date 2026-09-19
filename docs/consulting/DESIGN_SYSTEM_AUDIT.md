# Consulting system — design audit gate

Status: **AUDIT COMPLETE — no consulting UI implemented.**

Audited 2026-09-19 in `C:/Users/ndasi/.codex/worktrees/ceec/integration`, HEAD `b3f7f62bff71391271c5c678c103c163461bc5e7`. Working-tree source is the evidence, including any uncommitted updates. Line references below are one-based at audit time. This is a source audit; it does not claim new live-site or accessibility measurements.

## Gate conclusion

The current public homepage is a **charcoal, warm off-white, copper** design, with a warm stone section for visual relief. Green is a secondary contextual/status color, not the primary brand accent. Consulting should extend that homepage family without introducing a different visual identity, separate operator shell, or global theme replacement.

Current beta source is the older `.beta-page` / `.beta-*` surface. The previously discussed `.bp-page` redesign is **not in this audited tree**. Do not treat conversation history or screenshots from earlier branches as current production source. The newer `.mh-page` homepage is the visual baseline; beta supplies existing form/workflow conventions, not the preferred new spacing and CTA treatment.

## Source inventory and hierarchy

| Source | Role / relevant entry points |
| --- | --- |
| `AGENTS.md:1` | Preserve approved UX/workflows; additive scoped changes; no unsupported compliance/traceability assertions. |
| `frontend/src/pages/MarketingHome.tsx:125` | Current homepage composition; wrapper uses both `marketing-page` and `mh-page`. Main includes skip-link target. |
| `frontend/src/components/marketing/MarketingNav.tsx:6` | Exported `MarketingBrand`; existing logo/wordmark/home destination. |
| `frontend/src/components/marketing/MarketingNav.tsx:20` | Exported sticky responsive `MarketingNav`; keyboard Escape/focus behavior and analytics. |
| `frontend/src/marketing-home.css:1086` | Homepage v2 overrides; primary design tokens and reusable public classes. Earlier rules in this same file are legacy `.marketing-*` surfaces and still support other pages. |
| `frontend/src/marketing-home.css:2561` | Later homepage refinement: reveal motion, split product proof, extraction workflow panel, responsive overrides. Later cascade matters. |
| `frontend/src/beta-partner.css:1` | Existing legacy beta styling, forms, success/error states; breakpoints 900/640. |
| `frontend/src/styles.css:1` | Global base font/body, `nav`, `main`, forms and operator styles. |
| `frontend/src/streamlit-exact.css:3` | Operator token layer; important global rules at lines 38, 44, 76–77 and 104 can leak into public pages. |
| `frontend/src/main.tsx:10` | Global CSS import order: base/operator layers precede marketing and beta, followed by contact/storefront/offline layers. Do not assume public pages run in a clean CSS environment. |
| `frontend/src/components/ContactChannels.tsx:25` | Shared `MarketingContactChannels`; public mail contact cards. |

## Palette and surfaces

| Category | Exact current value | Source |
| --- | --- | --- |
| Main public canvas | `#0c0e0f`; radial warmth `#33201455` at 78% 3% | `marketing-home.css:1087` |
| Primary copper | `--mh-copper: #f69a5b` | `marketing-home.css:1088` |
| Main text | `--mh-text: #f2eee8` | `marketing-home.css:1089` |
| Muted body copy | `--mh-muted: #b0ada8` | `marketing-home.css:1090` |
| Neutral divider | `--mh-line: #32312f` | `marketing-home.css:1091` |
| Hero emphasis | `#f6a46d` | `marketing-home.css:1292` |
| CTA fill / border / text | `#f69a5b` / `#f6a066` / `#1c120b` | `marketing-home.css:1222` |
| Hover and focus | `#ffb67d` | `marketing-home.css:1118`, `1237` |
| Editorial text link | `#efb181` | `marketing-home.css:1305` |
| Product/card surfaces | `#121516`, `#141617`, darker nested `#101213` | `marketing-home.css:1347`, `1550`, `1772` |
| Active selector | Fill `#302219`, border `#cd8d5e`, text `#ffc397` | `marketing-home.css:1573` |
| Warm-light section | Background `#e8e0d3`, heading `#262622`, copy `#56554e`, eyebrow `#804b25` | `marketing-home.css:1644` |
| Muted green contextual panel | `#171b18`, icon `#b5bf9b` | `marketing-home.css:1723` |
| Legacy beta | Orange `#ef7427`; canvas gradient `#080b0d` → `#090a0b` → `#07090a`; status green `#79c58d` | `beta-partner.css:1`, `45`, `115` |

Operator `--dl-green:#58D68D` exists alongside blue/yellow/red semantic colors (`streamlit-exact.css:21`); it is not the public primary CTA. Avoid adding green primary buttons merely because the product concerns cannabis.

## Typography and hierarchy

- Global stack is `Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` with tabular numbers (`streamlit-exact.css:38`); base `styles.css:1` also declares Inter/system fallbacks. A declaration is not evidence that a bundled Inter webfont is installed. Do not add a new external font dependency without need.
- Brand wordmark is Georgia/serif, 26px, weight 700, tracking `-.045em`; “Logic” copper `#ef8b48` (`marketing-home.css:1186`). It becomes 23px on mobile (`:2208`). Reuse the wordmark component rather than setting a new logo in a generic sans-serif face.
- Homepage H1: `clamp(50px,6.1vw,86px)`, line-height `1.04`, tracking `-.065em`, weight 560 (`:1284`). Mobile: `clamp(39px,10.5vw,61px)` (`:2234`). Strong editorial statements, short deliberate line breaks and one copper phrase.
- H2: `clamp(32px,3.4vw,48px)`, line-height `1.14`, tracking `-.045em`, weight 550 (`:1107`). H3 weight 600, tracking `-.025em` (`:1113`), usually 19–23px by component.
- Hero body: 17px, max 650px, 24px top margin; body line-height 1.7 (`:1295`). Mobile hero body 15px (`:2237`). Section explanations 15px / 450px max (`:1486`), card body 12–14px.
- Eyebrow: 11px, weight 650, uppercase, tracking `.13em`, copper (`:1133`); mobile 10px and `.09em` (`:2224`). Labels 10px `.12em` (`:1141`). These are hierarchy accents, not a replacement for readable primary copy.
- Content tone: concrete operational problem → scope/context → next action. Current homepage H1 is “Your team shouldn't be the integration.” (`MarketingHome.tsx:139`). New consulting copy should stay specific about deliverables, suitability and next steps, avoiding invented quantified results or credentials.

## Layout, spacing and responsive behavior

| Breakpoint | Container and behavior | Source |
| --- | --- | --- |
| Default desktop | `min(1240px,100% - 80px)`; 40px nominal side gutters; centered | `marketing-home.css:1129` |
| At least 1500px | `min(1360px,100% - 120px)` | `:2036` |
| At most 1100px | Navigation/gap reductions; hero aside 220px; section gap 45px | `:2044` |
| At most 900px | Container `100% - 48px`; header 74px; collapsed menu; hero aside hidden; main split sections collapse; selectors two columns; footer three columns with brand row | `:2075` |
| At most 600px | Container `100% - 36px`; smaller logo/type; primary hero CTA full width; footer two columns and stacked bottom line | `:2204` |
| Product/extraction overrides | Split layouts collapse at 900px; 72px section padding there and 56px at 600px | `:2607` |
| Legacy beta | 1180px max and 34px total gutters; collapses at 900px; 24px total gutters/single-column form at 640px | `beta-partner.css:25`, `203`, `212` |

Default homepage section padding is 96px vertically (`marketing-home.css:1472`), reduced to 72px at 900px. Section heading grid uses 1.2fr/.8fr, gap 95px, bottom margin 40px (`:1475`). Newer split product proof uses `.55fr/1.45fr`, 54px gap and 100px padding (`:2564`). Avoid dense feature-card walls; alternate editorial sections, evidence and a restrained warm-light band.

## Header, navigation and routing reuse

`MarketingNav` already owns sticky header, brand, mobile toggle, `aria-expanded`, `aria-controls`, close-on-anchor, Escape handling and returned toggle focus (`MarketingNav.tsx:20`). Desktop header is 84px with translucent charcoal and fine bottom border (`marketing-home.css:1161`); nav links have 44px hit areas (`:1209`).

Current items are Platform, Extraction, Solutions, Intelligence and Resources, followed by operator login and Apply for beta (`MarketingNav.tsx:47`). They use local `#...` anchors. **Unmodified reuse on a consulting subpage would point at nonexistent consulting anchors.** A later minimal extension must preserve homepage behavior and use `/#...` links on subpages, or accept an explicit navigation configuration. Do not duplicate the header or rewrite operator navigation.

`MarketingBrand` home link is already `/#top` (`MarketingNav.tsx:6`). Keep APP_URL as the source of the operator destination. Consulting routes must be explicit public routes; current `main.tsx` host/storefront/portal routing must not be replaced by a broad marketing catch-all.

## CTA and interaction patterns

- `.mh-button`: 50px minimum height, 15px×22px padding, 24px gap, 5px radius, 14px/750 text, copper fill; small variant 42px and 12px text (`marketing-home.css:1222`). Icons are Lucide ArrowRight/ArrowUpRight/ArrowDown rather than a separate icon set.
- `.mh-text-link`: subdued copper, inline icon, minimum 44px height, underline on hover (`:1305`). Use a clear primary action with quieter contextual links.
- `BetaLink` is a local function, not exported; it hardcodes `/beta#apply` and homepage analytics (`MarketingHome.tsx:78`). Consulting must not silently reuse that destination for a different intent. A later shared CTA can preserve this default while accepting explicit service action/destination.
- Products and solutions use real buttons with `aria-pressed` inside labelled groups, not fake interactive divs (`ProductShowcase.tsx:39`, `Solutions.tsx:49`). Solutions synchronize hash-based selection (`Solutions.tsx:16`).
- FAQ uses native details/summary (`MarketingHome.tsx:263`; `marketing-home.css:1898`), so keyboard semantics are built in.

## Cards, borders, radii, shadows and visual proof

| Pattern | Treatment | Reuse guidance |
| --- | --- | --- |
| Product window | 10px radius, 1px `#65503e`, `#121516`, shadow `0 30px 100px #0006` (`marketing-home.css:1347`) | Reuse real evidence component only when relevant to the consulting story. |
| Selector cards | 6px radius, 1px `#3b3935`, `#141617`, copper active border (`:1550`) | Fits consulting service selection if semantics remain real buttons and selection has a purpose. |
| Open editorial cards | Top border only, 27px vertical padding, three-column grid (`:1704`) | Good for deliverables/process; avoids over-boxing every paragraph. |
| Unified/AI panels | 6–8px radius, warm dark gradient, thin brown border (`:1526`, `:1747`) | Use sparingly for a featured assessment or context panel. |
| Integration matrix | Shared outline, 6px radius, subtle column rules, 30px padding (`:1819`) | Appropriate for comparable scope, inputs and outputs. |
| Final CTA | 8px radius, `#705038` border, subtle copper radial light on `#171717`, centered 64px padding (`:1930`) | Reuse closing conversion hierarchy with accurate service copy. |

No photo/illustration stock system is established. Real WebP product captures use 480/960/1440 widths, explicit dimensions, responsive sizes, synthetic-demo caption and full-size link (`ProductShowcase.tsx:60`). Do not relabel them as customer proof. `approvedCustomerProof` is empty (`customerProofData.ts:20`); do not invent logos, consulting clients, testimonials, case studies, savings or partnerships.

## Footer and contact reuse

Footer remains inline in `MarketingHome.tsx:277`, not an exported component. It includes MarketingBrand, contact mail, platform/solution/company link columns, year, “Semper Paratus / Powered by Good Weed and Data”, and back-to-top. Desktop grid is `1.4fr repeat(3,1fr)` with 55px gaps (`marketing-home.css:1963`); tablet and mobile adjustments are defined at `:2194`, `:2505`.

A future extraction of this exact footer into a reusable component is preferable to creating a visually different consulting footer. Preserve destinations and convert homepage anchors appropriately on subpages. The audited footer does not establish legal-document routes; do not fabricate privacy/terms/security destinations.

`MarketingContactChannels` is reusable, and homepage-specific overrides keep it within the same container/typography (`ContactChannels.tsx:25`, `marketing-home.css:2537`). Keep one clear page ending rather than adding multiple competing contact/footer sections.

## Forms, errors and CSS isolation

Existing beta application demonstrates labelled inputs, native required/email validation, checkbox consent, hidden honeypot, submission disable state and status/alert feedback. It is a beta intake workflow, not a consulting form to repurpose silently. Existing styling is 16px inputs with minimum 46px height, 2-column fields and full-width textareas, collapsing at 640px (`beta-partner.css:174`, `212`). Use equivalent accessibility and comfortable controls with consulting-specific content and its own API contract when implementation is authorized.

Critical inherited behavior:

1. `styles.css:14` sets every nav to grid; public nav must explicitly set its own layout.
2. `styles.css:25` sets main padding; `streamlit-exact.css:44` and `:104` override all main padding with `!important`. `.mh-page main` currently resets padding with a scoped important rule (`marketing-home.css:1097`). Preserve this isolation.
3. `streamlit-exact.css:77` applies important background/border/radius/color and removes focus outlines on all inputs/selects/textareas. New public forms need scoped winning overrides and visible focus; do not edit operator globals to make consulting look right.
4. `.primary`, `.secondary`, `.link-button`, `.brand`, `.page`, `.modal`, `.eyebrow` are operator/legacy shared classes. Avoid them for new public components. Prefer existing `.mh-*` primitives plus a dedicated consulting root/namespace.
5. Keep root style changes out of the consulting mission. Validate the actual cascade, including light-mode data attributes, rather than inferring final colors from one CSS file.

## Motion, accessibility and performance requirements to carry forward

Current reveal is a 0.65s opacity/16px rise with optional 0.12s delay (`marketing-home.css:2561`). Hover transitions are around 0.18s. There is no reason to add heavy motion libraries, counters, autoplay video or WebGL. `prefers-reduced-motion` disables animations/transitions/smooth scroll within `.mh-page` (`:2528`). Content must remain available with reduced motion.

Existing focus ring is 3px `#ffb67d`, 5px offset; anchors use 105px scroll margin under the sticky header; skip link is keyboard-visible (`:1118`, `:1122`, `:1152`). Keep a single H1, logical headings, labelled input groups, native controls, visible status/error text, and 44px target patterns. Source style values do not establish WCAG conformance: run axe and actual keyboard/contrast checks after implementation.

Reuse local logo assets and Lucide icons. Keep marketing imports/routes separated from operator workspaces and scanners. Use fixed image dimensions, responsive sources, and below-fold lazy loading where suitable. Do not fetch external integration/AI data merely to render a public consulting page.

## Implementation gate rules

1. Use the audited homepage copper/charcoal/stone system; green stays contextual.
2. Reuse MarketingBrand and extend MarketingNav minimally for real subpage links; preserve mobile menu behavior and operator login.
3. Extract the existing footer and CTA only where reuse requires it; no unnecessary redesign or breaking destination changes.
4. Use `.mh-page` public token/context plus a scoped consulting namespace. Do not modify operator styles or global tokens.
5. Preserve beta routes, its actual form workflow and scope. Consulting is a separate surface and conversion path.
6. Use current source, not earlier `.bp-page` artifacts, as the implementation baseline.
7. Build only factual service content and evidence. An empty proof collection stays empty.
8. Test 320/375/390/430/768/1024/1440 widths, keyboard, menu, form failure/success, reduced motion, route isolation and image loading before release.

No UI code, component, stylesheet, route, application workflow or live-site content was changed during this gate. Only this audit document was created.
