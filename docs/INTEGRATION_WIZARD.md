# Integration Wizard

Status: CODE_READY. No push, merge, PR or deployment is authorized for this change.

The facility-scoped route `/settings/integration-wizard` is available from Implementation Readiness, Integrations and Settings navigation. It guides context confirmation, system selection, connection settings, explicit validation, mapping, evidence review and the final summary. Existing Integrations cards remain the configuration surfaces; provider deep links scroll to the relevant card and Resume Integration Wizard returns to the saved step.

The read model uses existing integration status contracts, the Metrc context resolver and accounting links. It does not call external providers on page load. Provider tests run only on an explicit operator action through the existing test endpoints. No synchronization or business-record writes are added.

Metrc is required when the facility's existing operating mode selects Metrc Sandbox. Its configured context and trusted mapping remain authoritative. DoobieLogic Sandbox leaves Metrc not applicable and disables the wizard test action. BioTrack requires a state-approved contract; the wizard does not infer jurisdiction support. QuickBooks is offered for commercial facilities and exposes customer/invoice support, manual product Item mapping, unmapped active organization products and failed/stale facility accounting links. AI runtime, Doobie and Spacemail retain existing platform scope and DEV permissions.

Connected requires a recorded successful validation, with the mapping checks shown in the guide. It is not production acceptance. The original Implementation Readiness production synchronization and manual review items remain intact; additional provider setup evidence links back to the wizard. Skips cannot override required providers or attest to validation.

The integrated White Label candidate uses the single migration head
`0083_onboarding_reporting` after `0082_white_label_execution`. Optional platform
services may visibly need attention, but do not count in the required-blocker summary
or become required facility go-live blockers for administrators. Required providers
come from the explicit facility operating mode; capability gates remain authoritative.

Resume and optional skips use `wizard_progress` and `wizard_<provider>` entries in the existing facility readiness annotation table, with audit events. No credentials or provider configuration are copied into these annotations. No schema migration is needed. The wizard response omits configuration payloads, secret hints and raw provider error strings.

Validation:

- Integrated candidate: 248 backend checks passed across readiness, wizard, reports,
  Work, White Label, CRM, integration/security, migration and source contracts.
- Full frontend suite: 135 passing tests across 28 files.
- Frontend lint and production build pass.
- Four Edge fixture acceptance checks pass at 1280px and 390px, including both entry points, save-and-clear of a synthetic secret, durable resume, optional skip, failed validation, summary, readiness owner/Work actions, scheduled reports and overflow checks. Mobile screenshots reviewed.

Follow-up acceptance: exercise the authenticated workflow against actual configured provider evidence when deployment is separately authorized. Browser acceptance uses isolated mocked provider responses and does not claim live-provider validation or public deployment.
