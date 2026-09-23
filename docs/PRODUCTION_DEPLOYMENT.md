# DoobieLogic PC-hosted production delivery

## Required finish line

Owner instruction recorded September 23, 2026: **make the PC-hosted release part of every authorized application delivery.** Do not stop at a commit, pull request, merge, green CI, or handoff file and call the application delivered.

Read `AGENTS.md` and `docs/PROJECT_INVARIANTS.md` first. This guide replaces the retired Cloud Run/Cloudflare Pages deployment instructions, preserved unchanged at `docs/archive/PRODUCTION_DEPLOYMENT_CLOUD_RUN_LEGACY.md` for historical reference only. The archive is not an executable deployment plan.

## Architecture to preserve

- Application compute: Nelson's Windows PC.
- Operator entry: `https://ops.doobielogic.io` through Cloudflare HTTPS/Tunnel.
- Local edge: Caddy on `127.0.0.1:8080`, serving the built React assets and proxying same-origin `/api/*` to FastAPI on `127.0.0.1:8010`.
- Production authentication and durable data: the existing hosted Supabase project `fovxtygwcxubjzjgovva`. Backend and browser must retain their matching project configuration and existing user identities.
- Preserve existing `doobielogic.io` marketing/advisory and `api.doobielogic.io` routing where configured. Do not move DNS or reintroduce retired hosting to complete a release.
- Keep production secrets on the authorized host/secret store. Never put passwords, API keys, connection strings, tokens or private exports in release evidence.

## Current automation boundary

At baseline `bef92f57e2a064b98535240d73d09f04908a3cbe`, `.github/workflows/deploy.yml` is named "Deploy to DoobieLogic", but runs validation on hosted Ubuntu runners only. Its final summary explicitly says that no external application deployment is performed. Its success means candidate validation, not installation or restart on Nelson's PC.

No PC execution channel is established by that workflow. Verify the currently available owner-authorized machine connection and actual host configuration before any release. Local-only launcher paths in historical logs are discovery hints, not proof of the current served checkout. A GitHub connection does not by itself give terminal access to the PC.

If an authorized machine connection is unavailable or offline, the release is `RELEASE_BLOCKED` until that access is established. Record that blocker, not an imaginary deployment. Do not create an unprotected self-hosted runner, execute untrusted PR code on the production PC, or install persistent remote access without authorization. Installing a chat connector alone does not establish unattended deployments or an always-on updater.

## Mandatory delivery sequence

1. **Resolve the exact candidate.** Re-read branch/PR state, preserve concurrent work, integrate dependencies in order, and record an immutable release SHA. Pass the applicable tests, security/performance checks and isolated PostgreSQL acceptance on the integrated candidate. Older branch results are not final-candidate evidence. Respect repository review/protection requirements; no force pushes or validation bypasses.
2. **Inspect and safeguard the actual host.** Confirm the live checkout, Caddy asset root, API process/service command, local-only launcher, environment source, current frontend/API identities and uncommitted changes through the authorized connection. Record rollback locations privately. Do not use `git reset --hard`, overwrite local-only files, kill unrelated processes or print environment values.
3. **Prepare a matching release.** Use the verified host procedure to build the frontend and prepare the compatible API at the recorded candidate. Keep runtime configuration and hosted Supabase continuity. Run required migrations once only after backup/restore and compatibility gates; derive the expected Alembic head from the candidate rather than a hardcoded historical revision. Do not rerun the passed Metrc evaluation or trigger provider mutations on deployment.
4. **Release on the Windows PC.** Promote the prepared frontend/API using the existing host-managed release/start/restart mechanism, within any applicable maintenance window. Preserve the previous working artifacts and configuration. Avoid serving a mixed old/new frontend and backend; where atomic promotion is unavailable, use a controlled, recoverable switch. GitHub validation does not perform this step.
5. **Verify the local and public release.** Check the API's actual `/health` and `/health/ready` routes on loopback, readiness/schema compatibility, and `release_sha` against the recorded release. Verify Caddy serves the intended assets. Check `https://ops.doobielogic.io` through the public tunnel, including login/session, facility/role context and the changed workflow using an authorized test identity. Match the served frontend `/release.json` when present; otherwise record equivalent served-asset hash evidence. An absent release marker, `development` SHA or HTTP 200 alone is not sufficient identity proof. Use the real configured public readiness mapping; do not invent one or expose a diagnostic endpoint just to get a green check. Recheck the homepage/advisory routes when affected.
6. **Record success or recover.** Only observed host deployment plus successful public acceptance earns `RELEASED_VERIFIED`. On failure, restore the known-good application release using the verified rollback plan and confirm public recovery. Do not blindly reverse schema migrations, delete business records or replay ambiguous provider actions. Record `ROLLED_BACK` or `RELEASE_BLOCKED` with the precise cause and remaining gate.

These steps are a required release contract, not a claim that a generic executable PC deployment script or authorized remote channel currently exists. Discover the actual host procedure rather than fabricating commands from outdated paths.

## Evidence and status

Use the following states consistently:

| State | Meaning |
| --- | --- |
| `CODE_READY` | Implementation/tests reached the stated source milestone; no live delivery claim. |
| `RELEASE_PENDING_PC` | Candidate is ready for the authorized host release, but deployment/public verification is outstanding. |
| `RELEASE_BLOCKED` | An access, review, test, backup, compatibility, host or acceptance gate prevents safe delivery. |
| `RELEASED_VERIFIED` | Exact release observed on the PC and through the public operator app; affected workflow accepted. |
| `ROLLED_BACK` | Candidate was not accepted; the prior compatible application release was restored and recovery checked. |
| `DOCUMENTATION_UPDATED` | Instructions/documentation changed only; not an application deployment. |

Keep a sanitized release receipt containing the intended SHA, observed frontend/API identities, timestamp with timezone, tested candidate/run references, local/public check results, affected-workflow acceptance, schema compatibility, backup/rollback reference and final state. Keep workstation paths/access details and private test evidence in an authorized private location where needed. Never include credentials or customer data in public artifacts.

When release is blocked, name the exact missing permission, connection or failed check and the smallest action required to unblock it. Do not silently substitute a manual handoff for the requested release, promise background completion, or start unrelated feature work while treating the unshipped application work as finished.

Explicit user instructions for review-only or no-deploy work still apply. Documentation-only changes do not require restarting production. This standing requirement is not authorization for destructive database changes, identity replacement, unrestricted remote control or new hosting charges.
