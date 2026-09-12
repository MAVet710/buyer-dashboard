# Homepage rebuild control

Baseline: `1de2d511b8dd9df1b41336e51a507211bd95950f`. Review date: 2026-09-11. Scope: public React marketing homepage only. Existing AI runtime changes and untracked worktrees/artifacts are unrelated and preserved.

## Direction

Retain charcoal, warm copper, serif wordmark and operator voice. Replace the capability-heavy opening with an outcome-led hero and four explicit operation pathways. Show genuine sanitized product evidence when available. Identify all product availability as beta and integration readiness separately. No fabricated customer evidence.

## Hero concepts reviewed

1. Outcome: **Your operation. One clear picture.** Selected: short, legible, gives product imagery room, pairs with explicit cannabis ERP description.
2. Control: **See the handoff before it becomes a hold-up.** More specific to manufacturing; retained as a lifecycle theme.
3. Fragmentation: **The spreadsheet circus has had its run.** Distinctive but overemphasizes the problem and risks implying every external system is replaced.

| Section | Current state / problem | Proposed solution | Owner | Claims / evidence | Implementation | Mobile | Accessibility | Performance |
|---|---|---|---|---|---|---|---|---|
| Navigation | Desktop links disappear on mobile | Keyboard-operable mobile menu, operation links, beta CTA | Lead | Existing /beta and APP_URL | Implemented | Chrome/Edge seven widths pass | Axe zero violations; keyboard pass | No menu library |
| Hero | Long feature H1; fabricated score/live sync mock | Outcome H1, beta label, authentic product proof | Lead + evidence agent | Proof ledger; product evidence | Implemented | Chrome/Edge seven widths pass | Axe zero violations; keyboard pass | Local optimized assets |
| Solutions | Module cards; cultivation and vertical buried | Four operation pathways with useful outcomes | Lead | Code-reviewed beta workspaces | Implemented | Chrome/Edge seven widths pass | Axe zero violations; keyboard pass | Native controls |
| Lifecycle / fragmentation | Generic workflow claims | Specific handoffs, explicit beta validation | Lead | Proof ledger | Implemented | Chrome/Edge seven widths pass | Axe zero violations; keyboard pass | CSS only |
| Trust / AI / integrations | Overbroad audit/compliance claims | Qualified beta controls, integration readiness | Research + lead | MARKETING_PROOF_LEDGER.md | Implemented | Chrome/Edge seven widths pass | Axe zero violations; keyboard pass | No external scripts |
| Adoption / FAQ / footer | Missing evaluation guidance | Application process, real links, visible FAQs | Lead + SEO | BetaPartnerPage.tsx; shared FAQ content | Implemented | Chrome/Edge seven widths pass | Axe zero violations; keyboard pass | Native details |
| Customer proof | None verified | Approval-gated reusable components, no invented content | SEO/proof agent | Approved content required | Implemented | Not rendered: no approved data | Unit-tested gating; visual QA deferred | Empty defaults |
| SEO / analytics | Basic schema; no event abstraction | Accurate social metadata, schema, opt-in event adapter | SEO agent | Visible beta content, real routes | Implemented | Chrome/Edge seven widths pass | Axe zero violations; keyboard pass | Swappable no-op default |

Final measured results and acceptance details are recorded in HOMEPAGE_ACCEPTANCE_REPORT.md. Mobile Lighthouse performance 99; desktop 100; accessibility and SEO 100. Best Practices 78 is limited by local HTTP. Firefox cannot launch on this Windows host. No deployment or production configuration changes are part of this working-tree implementation.
