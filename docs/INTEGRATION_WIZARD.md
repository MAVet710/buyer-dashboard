# Integration Wizard

Status: CODE_READY. No push, merge, PR or deployment is authorized for this change.

The facility-scoped route `/settings/integration-wizard` is available from Implementation Readiness, Integrations and Settings navigation. It guides context confirmation, system selection, connection settings, explicit validation, mapping, evidence review and the final summary. Existing Integrations cards remain the configuration surfaces; provider deep links scroll to the relevant card and Resume Integration Wizard returns to the saved step.

The read model uses existing integration status contracts, the Metrc context resolver and accounting links. It does not call external providers on page load. Provider tests run only on an explicit operator action through the existing test endpoints. No synchronization or business-record writes are added.

Metrc is required when the facility's existing operating mode selects Metrc Sandbox. Its configured context and trusted mapping remain authoritative. DoobieLogic Sandbox leaves Metrc not applicable and disables the wizard test action. BioTrack requires a state-approved contract; the wizard does not infer jurisdiction support. QuickBooks is offered for commercial facilities and exposes customer/invoice support, manual product Item mapping, unmapped active organization products and failed/stale facility accounting links. AI runtime, Doobie and Spacemail retain existing platform scope and DEV permissions.

Connected requires a recorded successful validation, with the mapping checks shown in the guide. It is not production acceptance. The original Implementation Readiness production synchronization and manual review items remain intact; additional provider setup evidence links back to the wizard. Skips cannot override required providers or attest to validation.

Resume and optional skips use `wizard_progress` and `wizard_<provider>` entries in the existing facility readiness annotation table, with audit events. No credentials or provider configuration are copied into these annotations. No schema migration is needed. The wizard response omits configuration payloads, secret hints and raw provider error strings.

Validation:

- Focused backend suite: 37 passing tests across wizard, onboarding/reporting, native integration security/production and Metrc facility onboarding.
- Full frontend suite: 114 passing tests across 23 files.
- Frontend lint and production build pass.
- Chrome fixture acceptance passes at 1280px and 390px, including both entry points, save-and-clear of a synthetic secret, durable resume, optional skip, failed validation, summary and overflow checks. Mobile screenshot reviewed.

Follow-up acceptance: exercise the authenticated workflow against actual configured provider evidence when deployment is separately authorized. Browser acceptance uses isolated mocked provider responses and does not claim live-provider validation or public deployment.
