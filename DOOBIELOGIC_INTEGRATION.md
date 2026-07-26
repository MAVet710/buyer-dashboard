# DoobieLogic Integration

Buyer Dashboard uses DoobieLogic as its cannabis-intelligence, support, and
license authority. Buyer Dashboard remains the source of truth for uploaded
data, KPI calculations, workflows, and UI.

## Required configuration

Configure these values as environment variables or Streamlit secrets:

```toml
DOOBIE_BASE_URL = "https://your-doobielogic-api.example.com"
DOOBIE_API_KEY = "the-shared-service-key"
```

Legacy `DOOBIELOGIC_URL` and `DOOBIELOGIC_API_KEY` names remain supported.

## API contract

The canonical dashboard client is `services/doobie_client.py`. It sends both
`x-api-key` and `Authorization: Bearer` headers and calls:

- `GET /api/v1/auth/check`
- `POST /api/v1/support/buyer_brief`
- `POST /api/v1/support/inventory_check`
- `POST /api/v1/support/extraction_brief`
- `POST /api/v1/support/ops_brief`
- `POST /api/v1/support/copilot`
- `POST /api/v1/license/validate`

Every support request contains:

```json
{
  "question": "What should the buyer prioritize?",
  "state": "MA",
  "data": {},
  "mode": "buyer"
}
```

The client converts legacy `prompt` values embedded inside `data` into the
required top-level `question`. Hyphenated support routes remain server-side
aliases for older dashboard deployments.

## Existing integration points

Buyer briefs, inventory checks, extraction briefs, the general copilot,
connection diagnostics, and license validation already route through
`services.doobie_client.DoobieClient`. New features should reuse that client
instead of introducing another HTTP wrapper.

Compatibility helpers remain in `doobielogic_client.py`:

- `buyer_intelligence(question, state, inventory_payload)`
- `extraction_intelligence(question, state, run_payload)`

## Running DoobieLogic

Run the v4 FastAPI application:

```bash
uvicorn doobielogic.api_v4:app --host 0.0.0.0 --port 8000
```

Production requires persistent PostgreSQL storage and the same service key on
both applications:

```text
DoobieLogic:      DOOBIE_API_KEY, DATABASE_URL, DOOBIE_BACKEND_MODE=postgres
Buyer Dashboard: DOOBIE_BASE_URL, DOOBIE_API_KEY
```

Before releasing, confirm:

1. `GET <DOOBIE_BASE_URL>/health` reports `source_of_truth=postgres_shared`.
2. `GET /api/v1/auth/check` accepts the configured service key.
3. A generated license validates through Buyer Dashboard.
4. The support health check returns a non-fallback response.
