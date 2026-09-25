# Facility permissions and security readiness

This implementation adds permission checks to selected FastAPI endpoints. It does
not claim domain-wide enforcement. The registry descriptions and admin UI identify
the covered actions. Existing role checks, organization/facility capability checks,
regulated-provider gates and service validation remain mandatory. An explicit allow
cannot bypass those checks. Level DEV retains its existing override exemption.

The existing `app_user_permission_overrides` table is reused without a migration.
Overrides match user, organization and facility exactly. Permission administration
checks the administrator's permission in the target facility, even if a different
facility is active in their browser. Override changes retain the existing audit writer.

## Initial enforcement coverage

| Group | Covered operations |
| --- | --- |
| Inventory | Individual/batch receipts and quantity adjustment endpoint |
| Audits | Audit completion, including optional posted adjustments |
| Cultivation | Bulk plant phase/room transition |
| Production | Schedule commit |
| Extraction / QA | Production and extraction QA decision endpoints |
| Compliance / Traceability | Queue dispatch and exception retry/resolution |
| Labels | Production label run creation, tag, design, print record and status transition |
| Commercial / Finance | Commercial invoice payment recording |
| Integrations | Save/clear the user's facility-scoped Metrc connection |
| Reports | Executive PDF and report-pack endpoints |
| Admin | Facility permission override updates |
| AI | AI agent knowledge ingestion |

Wholesale permissions retain their prior defaults and enforcement. New defaults
match existing endpoint roles. Payment recording, personal Metrc credentials and
executive exports previously accepted all authenticated roles, so their defaults
preserve that behavior, including read-only roles. Tightening those defaults is a
separate product-policy decision. Other domain routes and compatibility surfaces
retain their existing authorization and are not covered by these new permissions.

## Readiness evidence

The admin-only `/api/v1/admin/security-readiness` endpoint performs no external
requests and returns no secrets or configuration values. It reports:

- Presence of Supabase Auth and JWT verification configuration, not provider health.
- App password minimum and token verification behavior, not remote password policy,
  idle timeout, session lifetime or revocation configuration.
- Availability of permission and audit storage, plus bounded existence checks for
  records in the active organization/facility. This does not certify audit coverage
  across all workflows or tamper resistance.
- Presence of the integration encryption key. It does not verify old ciphertext,
  key strength, rotation or recovery.
- MFA enforcement, enterprise SSO and SCIM as unsupported by this app. No external
  identity feature has been implemented or inferred from Supabase capabilities.

Follow-up work should extend checks to additional endpoint/service paths with
explicit coverage tests and review broad inherited role policies. Provider-backed
identity controls require separate implementation and acceptance. This worker's
delivery is local source only; integration and PC/public acceptance remain with the
coordinated release owner under the explicit no-deploy instruction.
