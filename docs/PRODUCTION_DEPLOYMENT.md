# Buyer Dash production deployment

The production targets are `https://ops.doobielogic.io` and `https://api.doobielogic.io`. DNS is managed at Spaceship. Do not switch either record until the release candidate passes `docs/WEB_CUTOVER_GATES.md` against the production database clone.

## API

1. Create a Google Artifact Registry repository named `buyer-dash` in `us-east1`.
2. Store each value referenced by `deploy/cloudbuild-api.yaml` in Google Secret Manager and grant the Cloud Run service account `roles/secretmanager.secretAccessor` only for those secrets.
3. Run every Alembic migration through `0036_supabase_data_api_hardening` as a separate, one-shot migration job before deploying the API revision. Never run schema migration concurrently in web containers. This revision enables RLS and revokes direct Data API table and sequence access from `anon` and `authenticated`; Buyer Dash operational data remains available only through FastAPI.
4. Submit `deploy/cloudbuild-api.yaml`, initially with zero production traffic.
5. Verify `/health`, `/health/ready`, authenticated tenant isolation, logs, and rollback to the previous revision.
6. Map `api.doobielogic.io` to the verified service and add the exact DNS record supplied by Google at Spaceship.

## React client

1. Configure Cloudflare Pages with root directory `frontend`, build command `pnpm build`, and output directory `dist`.
2. Set the three variables in `deploy/frontend.env.example`. Only the Supabase publishable key belongs in the browser.
3. Verify the preview deployment against the zero-traffic API revision.
4. Add `ops.doobielogic.io` as the Pages custom domain and copy the exact CNAME/verification record into Spaceship.

## Supabase

- Add `https://ops.doobielogic.io` as the Site URL and allowed redirect origin.
- Add password recovery and invitation redirect URLs under the same origin.
- Keep the service-role key only in Cloud Run Secret Manager.
- Back up the database and record the migration revision before applying migrations.

## DNS cutover

Lower TTL before the scheduled window. Confirm both provider-issued targets rather than guessing their values. After propagation, test TLS, auth recovery, facility switching, uploads, inventory write paths, and audit evidence from the public domains. Keep Streamlit available and unchanged until pilot acceptance and rollback rehearsal are complete.
