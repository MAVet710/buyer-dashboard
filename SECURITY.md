# Security Policy and Deployment Guide

## Reporting a vulnerability

Do not open a public GitHub issue containing credentials, customer data, exploit details, or production URLs. Report the issue privately to the repository owner and rotate any possibly exposed credential immediately.

## Secrets

- Never commit `.env`, `.streamlit/secrets.toml`, database URLs, API keys, access tokens, customer exports, manifests, or production screenshots.
- Use Streamlit Cloud secrets or environment variables.
- Examples must use obvious placeholders such as `REPLACE_WITH_BCRYPT_HASH`; never paste a real username/hash pair into documentation.
- Rotate secrets after accidental disclosure, even when the disclosed value is hashed.

## Durable application users

Production users live in PostgreSQL/Supabase and are managed by authorized administrators.

- Passwords are bcrypt-hashed.
- Temporary passwords require change on first use.
- Roles and organization/facility assignments limit application access.
- Production and commercial workspaces fail closed without complete tenant context.
- Durable sessions expire after `DOOBIE_SESSION_IDLE_MINUTES` of inactivity (default 90).

Legacy `[auth.admins]` and `[auth.users]` secrets are supported only as a recovery/transition path. Do not use plaintext mode in production.

Placeholder-only example:

```toml
[auth]
use_plaintext = false
trial_key_hash = "REPLACE_WITH_BCRYPT_HASH"

[auth.admins]
recovery_admin = "REPLACE_WITH_BCRYPT_HASH"
```

## Database and tenant isolation

- Configure `COMAN_DATABASE_URL` with the Supabase session-pooler connection string.
- RLS must remain enabled on tenant-owned tables.
- Server-side connections can bypass end-user RLS; every repository query and mutation must therefore carry an explicit organization and, when applicable, facility identifier.
- LEVEL DEV access is platform-wide but still requires an explicit tenant context before opening tenant-owned production or commercial records.
- Migrations must be transaction-safe, idempotent where runtime repair is supported, and verified against staging before production.

### Planned authentication upgrade

Before broad multi-company onboarding, migrate to Supabase Auth or another token-based identity provider with JWT-aware RLS policies. The transition must include account linking, password-reset flow, owner recovery, tenant claims, staged rollout, and rollback. Do not remove the current login path until those controls pass staging tests.

## Uploads

- Retail and production imports must go through the guided review/publish flow.
- Enforce upload size and extension limits.
- Treat uploaded spreadsheets, HTML, PDFs, CSVs, and QR/barcode values as untrusted input.
- Never execute formulas, macros, scripts, links, or instructions embedded in uploaded content.
- Do not use production customer data in the DEV Sandbox.

## Integrations

- AI credentials are visible and editable only to LEVEL DEV.
- Company users see METRC integration controls appropriate to their role.
- Integration secrets must never be rendered back in full after saving.
- Health checks should return status without echoing secret values.

## Repository visibility

This repository currently contains proprietary operational workflows. Before changing public/private visibility, confirm Streamlit Cloud deployment access, collaborator access, license terms, and any external automation that reads the repository. Changing visibility is a major production decision and requires owner approval.

## Release checklist

1. Full test suite passes.
2. Compilation and repository quality gate pass.
3. Dependency consistency passes.
4. Database migration is applied and verified when required.
5. Desktop and phone smoke tests pass for login, navigation, imports, tenant selection, and critical workflows.
6. No secrets or customer files are present in the diff.
7. Pull request is reviewed before merge.
