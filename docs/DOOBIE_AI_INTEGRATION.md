# Doobie AI integration

DoobieLogic uses the FastAPI service running on the workstation as the application AI/service boundary. The active production application is PC-hosted and exposed through `https://ops.doobielogic.io` by Cloudflare Tunnel and Caddy.

## Runtime routing

The authoritative production request chain is:

`browser -> https://ops.doobielogic.io -> Cloudflare Tunnel -> Caddy 127.0.0.1:8080 -> FastAPI 127.0.0.1:8010`

Code running on the same workstation should use the FastAPI loopback address directly:

```text
DOOBIE_BASE_URL=http://127.0.0.1:8010
DOOBIE_SERVICE_API_KEY=<server-side service key>
```

Remote browsers must never be configured to call `127.0.0.1`; they use `ops.doobielogic.io` and the same-origin `/api/*` path through Caddy.

The following legacy environment aliases remain accepted for compatibility:

- `DOOBIE_AI_BASE_URL` or `DOOBIELOGIC_URL`
- `DOOBIE_API_KEY` or `DOOBIELOGIC_API_KEY`

Never store raw service keys in Git, documentation, screenshots, support messages, or browser-visible diagnostics. `DOOBIE_ADMIN_API_KEY` is for explicit administrative operations only and must not be used for normal application requests.

## AI runtime policy

The FastAPI configuration is local-first:

```text
AI_PROVIDER_MODE=local_only
AI_PROVIDER_ORDER=local
AI_ALLOW_CLOUD_FALLBACK=false
LOCAL_LLM_BASE_URL=<optional local model endpoint>
LOCAL_LLM_MODEL=<optional local model name>
```

If a local model is unavailable, the application must fail or use its deterministic non-cloud behavior according to the calling feature. It must not silently switch to a paid cloud model provider.

## API coverage used by DoobieLogic clients

- `GET /health`
- `GET /api/v1/auth/check`
- `GET /api/v1/knowledge/modules`
- `GET /api/v1/knowledge/professional-domains`
- `GET /api/v1/compliance/jurisdictions`
- `POST /api/v1/support/buyer_brief`
- `POST /api/v1/support/inventory_check`
- `POST /api/v1/support/extraction_brief`
- `POST /api/v1/support/ops_brief`
- `POST /api/v1/support/copilot`
- `POST /buyer/intelligence`
- `POST /extraction/intelligence`
- `POST /learning/feedback`
- `GET /learning/summary`
- `POST /api/v1/license/validate`

Service clients send both `Authorization: Bearer <key>` and `x-api-key: <key>` where compatibility with generated service keys requires it.

## Connection verification

LEVEL DEV users can open **Data & Integrations -> AI & METRC Integrations** and select **Test Connection**. A successful test may display the API version and the capabilities exposed by the currently running workstation service.

The API key must remain masked after saving. Connection diagnostics must identify the configured endpoint without exposing credentials.

## Architecture invariant

Do not introduce a hosted application origin, hosted AI service, alternate production API host, or cloud deployment fallback merely because the workstation service is temporarily unavailable. Any intentional architecture change must first update `docs/PROJECT_INVARIANTS.md` and the regression guard in `scripts/verify_zero_cost_deployment.py`.
