# Local AI production configuration

Production deployments use an explicit repository-level declaration for Local AI. They do not infer configuration from a previous Cloud Run revision.

## Declared states

- `LOCAL_AI_RUNTIME_STATE=enabled`: deployment requires complete HTTPS endpoint and model variables, attaches Cloudflare Access credentials from Google Secret Manager, and validates the exact no-traffic candidate before promotion.
- `LOCAL_AI_RUNTIME_STATE=disabled`: deployment records an intentional disabled provider mode. This is different from a missing or incomplete configuration.
- Missing or any other value: deployment fails before a candidate is promoted.

The non-secret repository variables are:

- `LOCAL_LLM_BASE_URL`
- `LOCAL_LLM_MODEL`
- `LOCAL_LLM_TIMEOUT_SECONDS`
- `LOCAL_LLM_MAX_TOKENS`
- `LOCAL_LLM_TEMPERATURE`
- `LOCAL_EMBEDDING_BASE_URL`
- `LOCAL_EMBEDDING_MODEL`
- `LOCAL_EMBEDDING_TIMEOUT_SECONDS`

Cloudflare Access credentials remain Secret Manager references:

- `doobielogic-ai-cf-access-client-id`
- `doobielogic-ai-cf-access-client-secret`

## Safety behavior

The deploy workflow injects the declaration into the no-traffic API candidate and checks its mode, URL, model, and secret references before traffic can move. The follow-up audit compares the 100% production revision with the same declaration. It reports drift and never reconstructs settings from revision history or promotes a repair revision.

Change the repository declaration before changing the runtime. A deployment with incomplete, missing, or mismatched enabled configuration is expected to fail closed.
